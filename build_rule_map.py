#!/usr/bin/env python3
"""
Extract trigger conditions from existing respondent reports and generate rule_map.yaml entries.
All patterns are in English to match the current English-only response format.
"""

import json
import os
import glob
import re
import yaml
from pathlib import Path

# Natural language condition → code logic mapping templates
PATTERN_TEMPLATES = [
    {
        "name": "Price breaks below a support level",
        "patterns": [
            r"(?:price\s+)?breaks?\s+below\s+(\d+)",
            r"(?:price\s+)?falls?\s+below\s+(\d+)",
            r"close\s+below\s+(\d+)",
            r"drops?\s+below\s+(\d+)",
        ],
        "code": "row['close'] < {level}",
        "params": ["level"],
    },
    {
        "name": "Price breaks above a resistance level",
        "patterns": [
            r"(?:price\s+)?breaks?\s+above\s+(\d+)",
            r"(?:price\s+)?rises?\s+above\s+(\d+)",
            r"close\s+above\s+(\d+)",
            r"holds?\s+above\s+(\d+)",
        ],
        "code": "row['close'] > {level}",
        "params": ["level"],
    },
    {
        "name": "MACD golden cross",
        "patterns": [
            r"MACD\s+golden\s+cross",
            r"MACD\s+forms?\s+golden\s+cross",
        ],
        "code": "macd_diff[-1] > macd_dea[-1] and macd_diff[-2] <= macd_dea[-2]",
        "params": [],
    },
    {
        "name": "MACD dead cross",
        "patterns": [
            r"MACD\s+dead\s+cross",
            r"MACD\s+forms?\s+dead\s+cross",
            r"MACD\s+turns?\s+dead\s+cross",
        ],
        "code": "macd_diff[-1] < macd_dea[-1] and macd_diff[-2] >= macd_dea[-2]",
        "params": [],
    },
    {
        "name": "MACD histogram continues to rise",
        "patterns": [
            r"MACD\s+histogram\s+continues?\s+to\s+rise",
            r"MACD\s+histogram\s+continues?\s+to\s+expand",
        ],
        "code": "macd_hist[-1] > macd_hist[-2]",
        "params": [],
    },
    {
        "name": "MACD histogram shortening / turning negative",
        "patterns": [
            r"MACD\s+histogram\s+deepens?\s+negative",
            r"MACD\s+histogram\s+shortening",
            r"green\s+bar\s+shortening",
        ],
        "code": "macd_hist[-1] < macd_hist[-2]",
        "params": [],
    },
    {
        "name": "Volume expansion / surge",
        "patterns": [
            r"volume\s+expansion",
            r"volume\s+surge",
            r"volume\s+increase",
            r"with\s+volume",
        ],
        "code": "row['volume'] > prev_vol * 1.5",
        "params": [],
    },
    {
        "name": "Volume shrinks / decreases",
        "patterns": [
            r"volume\s+shrinks",
            r"volume\s+decreases",
            r"volume\s+drops",
        ],
        "code": "row['volume'] < prev_vol * 0.5",
        "params": [],
    },
    {
        "name": "RSI breaks above 50",
        "patterns": [
            r"RSI\s+breaks?\s+above\s+50",
            r"Weekly\s+RSI\s+breaks?\s+above\s+50",
        ],
        "code": "rsi > 50",
        "params": [],
    },
    {
        "name": "DEA stops declining",
        "patterns": [
            r"DEA\s+stops?\s+declining",
            r"Hourly\s+DEA\s+stops?\s+declining",
        ],
        "code": "macd_dea[-1] >= macd_dea[-2]",
        "params": [],
    },
    {
        "name": "DIFF turns upward / crosses above zero",
        "patterns": [
            r"DIFF\s+crosses?\s+above\s+zero",
            r"DIFF\s+turns?\s+upward",
        ],
        "code": "macd_diff[-1] > 0 and macd_diff[-2] <= 0",
        "params": [],
    },
    {
        "name": "Bearish reversal pattern formed",
        "patterns": [
            r"forms?\s+bearish\s+reversal\s+pattern",
            r"bearish\s+reversal",
            r"shooting\s+star",
        ],
        "code": "is_bearish_reversal(row)",
        "params": [],
    },
    {
        "name": "Price oscillates between range without breakout",
        "patterns": [
            r"oscillates?\s+between\s+(\d+)\s+and\s+(\d+)",
            r"range[-\s]?bound",
        ],
        "code": "row['close'] >= {level1} and row['close'] <= {level2}",
        "params": ["level1", "level2"],
    },
    {
        "name": "No bearish divergence on shorter timeframes",
        "patterns": [
            r"No\s+bearish\s+divergence",
            r"no\s+bearish\s+divergence",
        ],
        "code": "not has_bearish_divergence()",
        "params": [],
    },
]


def extract_rules_from_text(text: str) -> list:
    """Extract all matching rules from a piece of text"""
    rules = []
    for template in PATTERN_TEMPLATES:
        for pattern in template["patterns"]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                params = {}
                for i, param_name in enumerate(template.get("params", []), start=1):
                    try:
                        params[param_name] = float(match.group(i))
                    except (ValueError, IndexError, TypeError):
                        params[param_name] = match.group(i) if match.lastindex and match.lastindex >= i else None
                # Build code with params filled in
                code = template["code"]
                for key, val in params.items():
                    if val is not None:
                        code = code.replace("{" + key + "}", str(val))
                rule = {
                    "phrase": match.group(0),
                    "code": code,
                    "params": template.get("params", []),
                    "source": template["name"],
                }
                rules.append(rule)
                break  # One condition matches only one pattern
    return rules


def main():
    all_rules = []
    data_dir = "responses"

    # Traverse all subfolders
    for sub_dir in os.listdir(data_dir):
        sub_path = os.path.join(data_dir, sub_dir)
        if not os.path.isdir(sub_path):
            continue
        for json_file in glob.glob(os.path.join(sub_path, "*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            # Handle both compressed (cv3) and decompressed formats
            if "d" in data and "sa" in data["d"]:
                scenarios = data["d"]["sa"]
            elif "scenario_analysis" in data:
                scenarios = data["scenario_analysis"]
            else:
                continue

            for s in scenarios:
                conditions = s.get("trigger_conditions", []) or s.get("tc", [])
                for cond in conditions:
                    rules = extract_rules_from_text(cond)
                    all_rules.extend(rules)

    # Deduplicate
    seen = set()
    unique_rules = []
    for r in all_rules:
        key = (r["phrase"], r["code"])
        if key not in seen:
            seen.add(key)
            unique_rules.append(r)

    # Save
    output = {"rules": unique_rules}
    with open("rule_map.yaml", "w", encoding="utf-8") as f:
        yaml.dump(output, f, allow_unicode=True, default_flow_style=False)
    print(f"Generated {len(unique_rules)} rules → rule_map.yaml")


if __name__ == "__main__":
    main()