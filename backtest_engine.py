import pandas as pd
from pathlib import Path
from typing import Dict, Optional
import yaml

class BacktestEngine:
    def __init__(self, data: Dict[str, pd.DataFrame], signal_extractor, risk_filter, position_sizer, config_path: str = "config.yaml"):
        self.data = data
        self.signal_extractor = signal_extractor
        self.risk_filter = risk_filter
        self.position_sizer = position_sizer

        self.config = self._load_config(config_path)
        backtest_cfg = self.config.get("backtest", {})
        self.initial_equity = backtest_cfg.get("initial_equity", 1000000.0)
        self.commission_rate = backtest_cfg.get("commission", 0.0001)
        self.slippage = backtest_cfg.get("slippage", 1.0)

        self.account = {
            "equity": self.initial_equity,
            "available": self.initial_equity,
            "positions": [],
            "daily_stats": {"date": "", "trade_count": 0, "consecutive_losses": 0},
        }
        self.trades = []
        self.equity_curve = []

        self.primary_period = min(data.keys(), key=lambda p: self._period_to_minutes(p))
        self.timeline = data[self.primary_period]["datetime"].tolist()
        self.next_position_id = 1

    @staticmethod
    def _period_to_minutes(period_str: str) -> int:
        mapping = {"1min":1,"5min":5,"15min":15,"30min":30,"60min":60,"1h":60,"day":1440}
        return mapping.get(period_str, 1440)

    @staticmethod
    def _load_config(path: str) -> dict:
        cfg_path = Path(path)
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def get_bar(self, period: str, timestamp: str) -> Optional[Dict]:
        df = self.data.get(period)
        if df is None:
            return None
        row = df[df["datetime"] == timestamp]
        if row.empty:
            return None
        return row.iloc[0].to_dict()

    def run(self, fusion_json_generator=None) -> dict:
        if fusion_json_generator is None:
            fusion_json_iter = iter([])
        else:
            fusion_json_iter = iter(fusion_json_generator)

        for idx, current_time in enumerate(self.timeline):
            bar = self.get_bar(self.primary_period, current_time)
            if bar is None:
                continue

            trade_date = current_time.split(" ")[0]
            if self.account["daily_stats"]["date"] != trade_date:
                self.account["daily_stats"] = {"date": trade_date, "trade_count": 0, "consecutive_losses": 0}

            self._update_positions(bar)
            self._check_exits(bar, current_time)

            try:
                fusion_json = next(fusion_json_iter)
            except StopIteration:
                fusion_json = None

            if fusion_json:
                signals = self.signal_extractor.extract(fusion_json, bar)
            else:
                signals = []

            if signals:
                signals = self.risk_filter.filter(signals, self.account)

            for sig in signals:
                if sig.get("filtered", False):
                    continue
                symbol = fusion_json.get("contract_info", {}).get("symbol", "default") if fusion_json else "default"
                sig = self.position_sizer.size(sig, self.account["equity"], symbol)
                if sig.get("size", 0) <= 0:
                    continue
                self._execute_entry(sig, bar, current_time)

            equity = self._calculate_equity(bar)
            self.equity_curve.append({"datetime": current_time, "equity": equity})

        last_bar = self.get_bar(self.primary_period, self.timeline[-1])
        if last_bar and self.account["positions"]:
            for pos in list(self.account["positions"]):
                self._close_position(pos, last_bar, self.timeline[-1], "Force Close (End of Backtest)")

        return self.generate_report()

    def _update_positions(self, bar: dict):
        pass

    def _check_exits(self, bar: dict, current_time: str):
        for pos in list(self.account["positions"]):
            if pos["direction"] == "LONG":
                if bar["low"] <= pos["stop_loss"]:
                    exit_price = pos["stop_loss"] - self.slippage
                    self._close_position(pos, {"close": exit_price}, current_time, "Stop Loss")
                elif bar["high"] >= pos["take_profit"][0]:
                    exit_price = pos["take_profit"][0] - self.slippage
                    self._close_position(pos, {"close": exit_price}, current_time, "Take Profit")
            else:
                if bar["high"] >= pos["stop_loss"]:
                    exit_price = pos["stop_loss"] + self.slippage
                    self._close_position(pos, {"close": exit_price}, current_time, "Stop Loss")
                elif bar["low"] <= pos["take_profit"][0]:
                    exit_price = pos["take_profit"][0] + self.slippage
                    self._close_position(pos, {"close": exit_price}, current_time, "Take Profit")

    def _execute_entry(self, signal: dict, bar: dict, current_time: str):
        entry_price = bar["close"] + (self.slippage if signal["direction"] == "LONG" else -self.slippage)
        pos = {
            "id": self.next_position_id,
            "direction": signal["direction"],
            "entry_price": entry_price,
            "size": signal["size"],
            "stop_loss": signal["stop_loss"],
            "take_profit": signal["take_profit"],
            "entry_time": current_time,
            "symbol": signal.get("source_json", {}).get("contract_info", {}).get("symbol", "default"),
        }
        self.account["positions"].append(pos)
        self.next_position_id += 1
        self.risk_filter.update_account_on_fill(self.account, signal)
        self.trades.append({
            "entry_time": current_time,
            "direction": signal["direction"],
            "entry_price": entry_price,
            "size": signal["size"],
            "exit_time": None,
            "exit_price": None,
            "pnl": 0.0,
            "exit_reason": "",
        })

    def _close_position(self, pos: dict, bar: dict, current_time: str, reason: str):
        if pos["direction"] == "LONG":
            pnl = (bar["close"] - pos["entry_price"]) * pos["size"] * self._get_point_value(pos["symbol"])
        else:
            pnl = (pos["entry_price"] - bar["close"]) * pos["size"] * self._get_point_value(pos["symbol"])
        commission = (pos["entry_price"] + bar["close"]) * pos["size"] * self._get_point_value(pos["symbol"]) * self.commission_rate
        pnl -= commission
        self.account["equity"] += pnl
        self.risk_filter.update_account_on_exit(self.account, pnl)
        self.account["positions"].remove(pos)
        for trade in self.trades:
            if trade["exit_time"] is None and trade["entry_time"] == pos["entry_time"] and trade["direction"] == pos["direction"]:
                trade["exit_time"] = current_time
                trade["exit_price"] = bar["close"]
                trade["pnl"] = pnl
                trade["exit_reason"] = reason
                break

    def _calculate_equity(self, bar: dict) -> float:
        equity = self.account["equity"]
        for pos in self.account["positions"]:
            if pos["direction"] == "LONG":
                pnl = (bar["close"] - pos["entry_price"]) * pos["size"] * self._get_point_value(pos["symbol"])
            else:
                pnl = (pos["entry_price"] - bar["close"]) * pos["size"] * self._get_point_value(pos["symbol"])
            equity += pnl
        return equity

    def _get_point_value(self, symbol: str) -> float:
        return self.position_sizer.get_point_value(symbol)

    def generate_report(self) -> dict:
        if not self.equity_curve:
            return {"error": "No data"}
        df_eq = pd.DataFrame(self.equity_curve)
        df_trades = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

        total_return = (self.account["equity"] - self.initial_equity) / self.initial_equity
        days = (pd.to_datetime(self.timeline[-1]) - pd.to_datetime(self.timeline[0])).days
        annual_return = (1 + total_return) ** (365 / days) - 1 if days > 0 else 0.0

        cummax = df_eq["equity"].cummax()
        drawdown = (df_eq["equity"] - cummax) / cummax
        max_drawdown = drawdown.min()

        if not df_trades.empty:
            win_rate = (df_trades["pnl"] > 0).mean()
            avg_win = df_trades[df_trades["pnl"] > 0]["pnl"].mean() if not df_trades[df_trades["pnl"] > 0].empty else 0
            avg_loss = df_trades[df_trades["pnl"] < 0]["pnl"].mean() if not df_trades[df_trades["pnl"] < 0].empty else 0
            profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
        else:
            win_rate = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            profit_factor = 0.0

        return {
            "initial_equity": self.initial_equity,
            "final_equity": self.account["equity"],
            "total_return": total_return,
            "annual_return": annual_return,
            "max_drawdown": max_drawdown,
            "total_trades": len(self.trades),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "trades": self.trades,
            "equity_curve": self.equity_curve,
        }