class SignalExtractor:
    def __init__(self, rule_map=None):
        self.rule_map = rule_map or {}
        self._debug_printed = False
        self._signal_count = 0

    def extract(self, fusion_json, current_bar):
        scenario_list = fusion_json.get("scenario_analysis", [])
        if not scenario_list:
            return []
        rank1 = scenario_list[0]
        scenario_name = rank1.get("scenario", "")
        confidence = fusion_json.get("confidence_score", 5)

        short_kw = [
            "trend reversal", "reverse drop", "turn weak", "breakdown", "deep breakdown",
            "long kill", "crash", "plunge", "deep fall", "break weekly",
            "three-period sync correction", "deep correction", "trend reversal plunge",
            "top divergence confirmed drop"
        ]
        direction = "LONG"
        for kw in short_kw:
            if kw in scenario_name:
                direction = "SHORT"
                break

        if not self._debug_printed:
            self._debug_printed = True
            print(f"[Signal] Scenario: '{scenario_name}' -> Direction: {direction}")

        entry = current_bar["close"]
        stop_pct = 0.02
        target_pct = 0.03
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