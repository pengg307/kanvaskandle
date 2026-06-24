#!/usr/bin/env python3
"""
Multi-respondent voting & validation fusion system (v5.2 compatible)
- Loads JSONs from responses/ subfolder
- Decompresses v1.4 compact format
- Strict validation: rb count, rb volume (-1/0), si.ai, price levels
- Detailed error logging for pinpointing problematic model outputs
- Auto-completes fixed fields locally
"""

import json
import statistics
import os
import sys
import glob
from typing import List, Dict, Any, Tuple
from datetime import datetime
import yaml
from pathlib import Path

# ---------- Configuration ----------
def load_current_price(config_path="config.yaml"):
    cfg = {}
    if Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    return cfg.get("current_price", 2898)

CURRENT_PRICE = load_current_price()

# ---------- Decompression & Validation Constants ----------
KEY_MAP = {
    "pd": "period", "pl": "price_latest", "bo": "bollinger",
    "os": "opening_state", "pz": "price_zone", "mc": "macd",
    "st": "state", "zp": "zero_position", "mm": "momentum",
    "td": "trend", "pt": "pattern", "vl": "volume",
    "kl": "key_levels", "rs": "resistance", "sp": "support",
    "ko": "key_observation", "rb": "recent_bars",
    "cx": "contract_info", "sy": "symbol",
    "si": "strategy_info", "ai": "analyst_id",
    "ra": "resonance_analysis", "fa": "four_periods_aligned",
    "ad": "alignment_direction", "ds": "description",
    "cn": "contradiction", "dp": "dominant_period_state",
    "sa": "scenario_analysis", "pk": "probability_rank",
    "sc": "scenario", "pj": "probability_judgment",
    "tc": "trigger_conditions", "cs": "confidence_score",
    "cr": "confidence_reason", "co": "core_observation",
    "sm": "summary",
}

EXPECTED_BARS = {"weekly": 2, "daily": 5, "hourly": 6, "15min": 8}

INVALID_AI_NAMES = [
    "multi-period-resonance", "strategy", "Multi-Period Resonance",
    "futures_analysis", "model-name", "model name"
]

def strict_validate_and_transform(data: dict, file_name: str) -> dict:
    """严格校验模型输出，任何格式或数值错误都返回None，并打印详细错误日志。"""
    if not isinstance(data, dict) or "d" not in data:
        print(f"[ERROR] {file_name}: Missing top-level 'd' key.")
        return None

    payload = data["d"]
    if not isinstance(payload, dict):
        print(f"[ERROR] {file_name}: 'd' is not a dictionary.")
        return None

    # 1. 还原缩写键名
    def decode(obj):
        if isinstance(obj, dict):
            return {KEY_MAP.get(k, k): decode(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [decode(item) for item in obj]
        return obj
    
    try:
        decoded = decode(payload)
    except Exception as e:
        print(f"[ERROR] {file_name}: Failed during key decoding. {e}")
        return None

    # 2. 检查顶层必需字段
    required_top = ["weekly", "daily", "hourly", "15min", "ra", "sa", "cs", "cr", "co", "sm"]
    for field in required_top:
        if field not in decoded:
            print(f"[ERROR] {file_name}: Missing top-level field '{field}'.")
            return None

    # 3. 校验 si.ai
    strategy_info = decoded.get("strategy_info", {})
    ai_value = strategy_info.get("analyst_id", "")
    if not ai_value:
        print(f"[WARNING] {file_name}: si.ai is empty.")
    elif any(invalid.lower() in ai_value.lower() for invalid in INVALID_AI_NAMES):
        print(f"[WARNING] {file_name}: si.ai '{ai_value}' appears to be a strategy name, not a model name.")

    # 4. 校验四个周期数据及 K 线
    for period, expected_count in EXPECTED_BARS.items():
        period_data = decoded.get(period)
        if not isinstance(period_data, dict):
            print(f"[ERROR] {file_name}: Period '{period}' is not a valid dictionary.")
            return None

        period_data["period"] = period

        raw_rb = period_data.get("recent_bars")
        if not isinstance(raw_rb, list):
            print(f"[ERROR] {file_name}: '{period}.recent_bars' is not a list.")
            return None
            
        if len(raw_rb) != expected_count:
            print(f"[ERROR] {file_name}: '{period}.recent_bars' count mismatch. Expected {expected_count}, got {len(raw_rb)}.")
            return None

        converted = []
        rb_has_volume_issue = False
        for i, bar in enumerate(raw_rb):
            if not isinstance(bar, list) or len(bar) != 5:
                print(f"[ERROR] {file_name}: '{period}.recent_bars[{i}]' is not an array of 5 elements. Got: {bar}")
                return None
            
            try:
                o, h, l, c, v = float(bar[0]), float(bar[1]), float(bar[2]), float(bar[3]), float(bar[4])
            except (ValueError, TypeError):
                print(f"[ERROR] {file_name}: '{period}.recent_bars[{i}]' contains non-numeric data. Got: {bar}")
                return None
                
            if v <= 0:
                rb_has_volume_issue = True

            converted.append({
                "open": o, "high": h, "low": l, "close": c, "volume": v
            })
        
        if rb_has_volume_issue:
            print(f"[WARNING] {file_name}: '{period}.recent_bars' contains -1 or 0 volume values.")

        period_data["recent_bars"] = converted

    # 5. 补全固定字段
    decoded.setdefault("contract_info", {})
    decoded["contract_info"]["periods"] = ["weekly", "daily", "hourly", "15min"]
    decoded["contract_info"]["extraction_version"] = "data_v1.4_cv5"
    decoded.setdefault("strategy_info", {})
    decoded["strategy_info"]["strategy_name"] = "Multi-Period Resonance v1.1"
    decoded["strategy_info"]["strategy_version"] = "v1.1"
    decoded["risk_warning"] = "The above is for technical analysis only. Futures trading involves high risk."

    return decoded

# ---------- File Loading ----------
def load_responses_from_dir(directory: str) -> List[Dict[str, Any]]:
    if not os.path.isdir(directory):
        print(f"[Fusion] Directory {directory} not found")
        return []
    files = glob.glob(os.path.join(directory, "*.json"))
    print(f"[Fusion] Found {len(files)} JSON files:")
    responses = []
    for fpath in sorted(files):
        file_name = os.path.basename(fpath)
        print(f"  - {file_name}")
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                raw = json.load(f)
            data = strict_validate_and_transform(raw, file_name)
            if data is not None:
                responses.append(data)
                print(f"[Fusion] Loaded & validated: {file_name}")
            else:
                print(f"[Fusion] Discarded: {file_name} (see errors above)")
        except json.JSONDecodeError as e:
            print(f"[ERROR] {file_name}: Invalid JSON format. {e}")
        except Exception as e:
            print(f"[ERROR] {file_name}: Unexpected error during loading. {e}")
    return responses

# ---------- Validation (价位) ----------
def validate_levels(levels: Dict[str, List[float]], price: float, source: str = "") -> bool:
    supports = levels.get("support", [])
    resistances = levels.get("resistance", [])
    if not supports or not resistances:
        print(f"[Validation] {source} empty supports/resistances")
        return False
    if any(s >= price for s in supports):
        print(f"[Validation] {source} supports >= price {price}: {supports}")
        return False
    if any(r <= price for r in resistances):
        print(f"[Validation] {source} resistances <= price {price}: {resistances}")
        return False
    if supports != sorted(supports, reverse=True):
        print(f"[Validation] {source} supports order wrong")
        return False
    if resistances != sorted(resistances, reverse=False):
        print(f"[Validation] {source} resistances order wrong")
        return False
    print(f"[Validation] {source} passed")
    return True

def validate_response(response: Dict[str, Any], price: float, source: str = "") -> bool:
    try:
        levels = response.get("key_levels")
        if not levels:
            print(f"[Validation] {source} missing key_levels")
            return False
        has_analysis = ("resonance_analysis" in response) or ("regression_analysis" in response)
        if not has_analysis:
            print(f"[Validation] {source} missing analysis fields")
            return False
        if "scenario_analysis" not in response:
            print(f"[Validation] {source} missing scenario_analysis")
            return False
        if "confidence_score" not in response:
            print(f"[Validation] {source} missing confidence_score")
            return False
    except Exception as e:
        print(f"[Validation] {source} error: {e}")
        return False
    return validate_levels(levels, price, source)

# ---------- Voting & Fusion ----------
def extract_scenario_signatures(response: Dict[str, Any]) -> List[str]:
    scenarios = response.get("scenario_analysis", [])
    return [s.get("scenario", "").strip() for s in sorted(scenarios, key=lambda x: x.get("probability_rank", 99))]

def vote_scenarios(valid_responses: List[Dict[str, Any]]) -> Tuple[List[str], str]:
    if len(valid_responses) == 1:
        return extract_scenario_signatures(valid_responses[0]), "1/1"
    all_sigs = [tuple(extract_scenario_signatures(r)) for r in valid_responses]
    sig_counts = {}
    for sig in all_sigs:
        sig_counts[sig] = sig_counts.get(sig, 0) + 1
    max_count = max(sig_counts.values())
    candidates = [sig for sig, cnt in sig_counts.items() if cnt == max_count]
    if len(candidates) == 1:
        best = candidates[0]
        desc = f"{max_count}/{len(valid_responses)}"
        return list(best), desc
    else:
        best_resp = max(valid_responses, key=lambda x: x.get("confidence_score", 0))
        best = extract_scenario_signatures(best_resp)
        return best, f"Tie, used highest confidence"

def fuse_levels(valid_responses: List[Dict[str, Any]], price: float) -> Dict[str, List[float]]:
    all_sup = []
    all_res = []
    for r in valid_responses:
        all_sup.extend(r["key_levels"]["support"])
        all_res.extend(r["key_levels"]["resistance"])
    unique_sup = sorted(set(all_sup), reverse=True)
    unique_res = sorted(set(all_res), reverse=False)
    def select_three(vals, ascending=True):
        if len(vals) <= 3:
            return vals
        dist = sorted(vals, key=lambda x: abs(x-price), reverse=not ascending)
        return [dist[0], dist[len(dist)//2], dist[-1]][:3]
    return {"resistance": select_three(unique_res, True), "support": select_three(unique_sup, False)}

def get_alignment(r):
    if "resonance_analysis" in r:
        return r["resonance_analysis"]["alignment_direction"]
    elif "regression_analysis" in r:
        return r["regression_analysis"].get("direction", "Neutral")
    return "Unknown"

# ---------- Main ----------
def main():
    print("=== Fusion Start ===")
    if len(sys.argv) > 1:
        sub_dir = sys.argv[1]
        data_dir = os.path.join("responses", sub_dir)
        if not os.path.isdir(data_dir):
            print(f"[Fusion] Directory {data_dir} not found, fallback to responses/")
            data_dir = "responses"
    else:
        data_dir = "responses"

    print(f"[Fusion] Loading from: {data_dir}")
    responses = load_responses_from_dir(data_dir)
    if not responses:
        print("[Fusion] No valid data after strict validation.")
        return

    valid = []
    for i, r in enumerate(responses, 1):
        if validate_response(r, CURRENT_PRICE, f"Respondent{i}"):
            valid.append(r)

    if not valid:
        print("[Fusion] No valid responses after price-level validation.")
        return

    align_votes = [get_alignment(r) for r in valid]
    final_align = statistics.mode(align_votes)

    scenario_order, vote_desc = vote_scenarios(valid)
    scenario_map = {}
    for r in valid:
        for s in r["scenario_analysis"]:
            scenario_map[s["scenario"].strip()] = s
    final_scenarios = [scenario_map[n] for n in scenario_order if n in scenario_map][:3]
    for i, s in enumerate(final_scenarios):
        s["probability_rank"] = i + 1

    final_levels = fuse_levels(valid, CURRENT_PRICE)
    confidences = [r["confidence_score"] for r in valid]
    final_conf = statistics.median(confidences)
    best = max(valid, key=lambda x: x.get("confidence_score", 0))

    contract_info = best.get("contract_info", {})
    source_symbols = []
    for r in valid:
        sym = r.get("contract_info", {}).get("symbol", "unknown")
        source_symbols.append(sym)

    best_analysis = best.get("resonance_analysis") or best.get("regression_analysis", {})

    final_output = {
        "contract_info": contract_info,
        "resonance_analysis": {
            "three_periods_aligned": best_analysis.get("three_periods_aligned", best_analysis.get("four_periods_aligned", "No")),
            "alignment_direction": final_align,
            "description": best_analysis.get("description", ""),
            "contradiction": best_analysis.get("contradiction", ""),
            "dominant_period_state": best_analysis.get("dominant_period_state", best_analysis.get("overbought_oversold_detail", ""))
        },
        "scenario_analysis": final_scenarios,
        "key_levels": final_levels,
        "confidence_score": final_conf,
        "confidence_reason": best.get("confidence_reason", ""),
        "core_observation": best.get("core_observation", ""),
        "summary": best.get("summary", ""),
        "risk_warning": best.get("risk_warning", "The above is for technical analysis only. Futures trading involves high risk."),
        "vote_meta": {
            "valid_outputs": len(valid),
            "source_symbols": source_symbols,
            "scenario_vote": vote_desc,
            "levels_method": "Intersection+Median",
            "confidence_method": "Median"
        }
    }

    print(json.dumps(final_output, ensure_ascii=False, indent=2))
    os.makedirs("output", exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    symbol = contract_info.get("symbol", "unknown")
    archive = f"output/fusion_{symbol}_{ts}.json"
    with open(archive, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    with open("output/fusion_result.json", "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    print(f"[Fusion] Saved: {archive} and fusion_result.json")

if __name__ == "__main__":
    main()