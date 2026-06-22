import yaml
import math
from pathlib import Path

class PositionSizer:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        ps_config = self.config.get("position_sizer", {})
        self.point_values = ps_config.get("point_values", {})
        self.max_risk_percent = ps_config.get("max_risk_percent", 0.02)
        self.min_size = ps_config.get("min_size", 1)
        self.size_step = ps_config.get("size_step", 1)
        self._first_log = True

    @staticmethod
    def _load_config(path: str) -> dict:
        cfg_path = Path(path)
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def get_point_value(self, symbol: str) -> float:
        if symbol in self.point_values:
            return self.point_values[symbol]
        base = ''.join(filter(str.isalpha, symbol))
        return self.point_values.get(base, self.point_values.get("default", 10.0))

    def size(self, signal: dict, equity: float, symbol: str = "default") -> dict:
        confidence = signal.get("confidence", 5)
        if confidence >= 7:
            risk_pct = self.max_risk_percent
        elif confidence >= 5:
            risk_pct = self.max_risk_percent * 0.5
        else:
            risk_pct = self.max_risk_percent * 0.2

        risk_amount = equity * risk_pct
        stop_distance = abs(signal["entry_price"] - signal["stop_loss"])

        if self._first_log:
            self._first_log = False
            print(f"[Sizer] Equity={equity:.0f} RiskPct={risk_pct:.2%} StopDist={stop_distance:.2f}")

        if stop_distance <= 0:
            signal["size"] = 0.0
            signal["risk_percent"] = risk_pct
            return signal

        point_val = self.get_point_value(symbol)
        raw_size = risk_amount / (stop_distance * point_val)
        size = math.floor(raw_size / self.size_step) * self.size_step

        if size == 0:
            print(f"[Sizer] WARNING: Size 0 (raw={raw_size:.2f} dist={stop_distance} pv={point_val})")

        if size < self.min_size:
            size = 0.0

        signal["size"] = size
        signal["risk_percent"] = risk_pct
        return signal