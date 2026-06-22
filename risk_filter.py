import yaml
from pathlib import Path
from copy import deepcopy

class RiskFilter:
    def __init__(self, config_path: str = "config.yaml", **overrides):
        full_config = self._load_config(config_path)
        risk_config = full_config.get("risk_filter", {})
        self.max_daily_trades = overrides.get("max_daily_trades", risk_config.get("max_daily_trades", 3))
        self.min_confidence = overrides.get("min_confidence", risk_config.get("min_confidence", 4))
        self.max_consecutive_losses = overrides.get("max_consecutive_losses", risk_config.get("max_consecutive_losses", 2))
        self.max_total_risk_percent = overrides.get("max_total_risk_percent", risk_config.get("max_total_risk_percent", 0.06))

    @staticmethod
    def _load_config(path: str) -> dict:
        cfg_path = Path(path)
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def filter(self, signals: list, account: dict) -> list:
        passed = []
        for sig in signals:
            sig = deepcopy(sig)
            sig.setdefault("filtered", False)
            sig.setdefault("filter_reason", "")

            if sig.get("confidence", 0) < self.min_confidence:
                sig["filtered"] = True
                sig["filter_reason"] = f"Confidence {sig['confidence']} < {self.min_confidence}"
                print(f"[Risk] REJECTED: {sig['filter_reason']}")
                continue

            daily_count = account.get("daily_stats", {}).get("trade_count", 0)
            if daily_count >= self.max_daily_trades:
                sig["filtered"] = True
                sig["filter_reason"] = f"Daily trades {daily_count} >= limit {self.max_daily_trades}"
                print(f"[Risk] REJECTED: {sig['filter_reason']}")
                continue

            consec_losses = account.get("daily_stats", {}).get("consecutive_losses", 0)
            if consec_losses >= self.max_consecutive_losses:
                sig["filtered"] = True
                sig["filter_reason"] = f"Consecutive losses {consec_losses} >= limit {self.max_consecutive_losses}"
                print(f"[Risk] REJECTED: {sig['filter_reason']}")
                continue

            positions = account.get("positions", [])
            if any(p.get("direction") == sig.get("direction") for p in positions):
                sig["filtered"] = True
                sig["filter_reason"] = "Duplicate direction"
                # silent skip

            if not sig["filtered"]:
                passed.append(sig)
        return passed

    def update_account_on_fill(self, account: dict, signal: dict):
        if "daily_stats" not in account:
            account["daily_stats"] = {}
        stats = account["daily_stats"]
        stats["trade_count"] = stats.get("trade_count", 0) + 1
        print(f"[Risk] Order filled. Today's trades: {stats['trade_count']}")

    def update_account_on_exit(self, account: dict, pnl: float):
        if "daily_stats" not in account:
            account["daily_stats"] = {}
        stats = account["daily_stats"]
        if pnl < 0:
            stats["consecutive_losses"] = stats.get("consecutive_losses", 0) + 1
            print(f"[Risk] Loss {pnl:.2f}, consecutive losses: {stats['consecutive_losses']}")
        else:
            stats["consecutive_losses"] = 0