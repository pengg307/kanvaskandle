"""
信号提取器 v2.1 - 支持 Neutral 方向 + 从 config.yaml 读取品种级止损止盈参数
"""

import yaml
from pathlib import Path

class SignalExtractor:
    def __init__(self, rule_map=None, config_path="config.yaml"):
        self.rule_map = rule_map or {}
        self._debug_printed = False
        self._signal_count = 0
        
        self.config = self._load_config(config_path)
        ps_config = self.config.get("position_sizer", {})
        self.stop_percent_map = ps_config.get("stop_percent", {})
        self.target_percent_map = ps_config.get("take_profit_percent", {})

    @staticmethod
    def _load_config(path: str) -> dict:
        cfg_path = Path(path)
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def extract(self, fusion_json, current_bar):
        # ===== 新增：检查 Neutral 方向 =====
        analysis = fusion_json.get("resonance_analysis") or fusion_json.get("regression_analysis", {})
        alignment = analysis.get("alignment_direction", "")
        if alignment == "Neutral":
            if not self._debug_printed:
                self._debug_printed = True
                print(f"[Signal] Fusion direction is Neutral, no signal generated.")
            return []
        # =================================

        scenario_list = fusion_json.get("scenario_analysis", [])
        if not scenario_list:
            return []
        rank1 = scenario_list[0]
        scenario_name = rank1.get("scenario", "")
        confidence = fusion_json.get("confidence_score", 5)

        short_kw = [
            "Bearish continuation", "bearish", "downtrend", "down trend",
            "trend reversal", "reverse drop", "turn weak", "breakdown", "deep breakdown",
            "long kill", "crash", "plunge", "deep fall", "break weekly",
            "three-period sync correction", "deep correction", "trend reversal plunge",
            "top divergence confirmed drop",
            "correction", "consolidation", "pullback", "range-bound",
            "Bearish Continuation", "Bearish", "BEARISH"
        ]

        direction = "LONG"
        matched_kw = ""
        for kw in short_kw:
            if kw.lower() in scenario_name.lower():
                direction = "SHORT"
                matched_kw = kw
                break

        symbol = fusion_json.get("contract_info", {}).get("symbol", "")
        base_symbol = ''.join(filter(str.isalpha, symbol)).upper() if symbol else "DEFAULT"

        stop_pct = self.stop_percent_map.get(base_symbol, self.stop_percent_map.get("default", 0.02))
        target_pct = self.target_percent_map.get(base_symbol, self.target_percent_map.get("default", 0.03))

        if not self._debug_printed:
            self._debug_printed = True
            print(f"[Signal] Scenario: '{scenario_name}' -> Direction: {direction}")
            if matched_kw:
                print(f"[Signal] Matched keyword: '{matched_kw}'")
            print(f"[Signal] Symbol: {symbol} -> Stop:{stop_pct:.2%} Target:{target_pct:.2%}")

        entry = current_bar["close"]
        if direction == "LONG":
            sl = entry * (1 - stop_pct)
            tp = [entry * (1 + target_pct)]
        else:
            sl = entry * (1 + stop_pct)
            tp = [entry * (1 - target_pct)]

        if abs(entry - sl) < 0.01:
            return []

        self._signal_count += 1
        if self._signal_count <= 3:
            print(f"[Signal] #{self._signal_count}: {direction} Entry:{entry:.2f} SL:{sl:.2f} TP:{tp[0]:.2f}")

        return [{
            "timestamp": current_bar["datetime"],
            "direction": direction,
            "entry_price": entry,
            "stop_loss": round(sl, 2),
            "take_profit": [round(tp[0], 2)],
            "confidence": confidence,
            "source_json": fusion_json,
            "entry_rule": {"rule_id": "scenario_seed", "scenario": scenario_name}
        }]

    def _extract_by_rules(self, fusion_json, current_bar):
        return []