#!/usr/bin/env python3
"""
Multi-respondent voting & validation fusion system v1.0 (multi-strategy compatible)
- Supports both "resonance_analysis" and "regression_analysis"
- Loads JSONs from responses/ subfolder specified via command line
- Automatically decompresses v1.4 compact format (using local KEY_MAP)
- Validates price level logic
- Outputs timestamped archive + latest fusion_result.json
- Extracts contract_info and source_symbols for tracking

Usage:
    python fusion.py AO2609/multi_period_v1.1
    python fusion.py AO2609/bb_regression_v2.0
    python fusion.py LC2609/multi_period_v1.1
    python fusion.py               # loads responses/ (root)
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

# ---------- Decompression (v1.4 compact cv3) ----------
KEY_MAP = {
    "pd": "period", "pl": "price_latest", "bo": "bollinger",
    "os": "opening_state", "pz": "price_zone", "mc": "macd",
    "st": "state", "zp": "zero_position", "mm": "momentum",
    "td": "trend", "pt": "pattern", "vl": "volume",
    "kl": "key_levels", "rs": "resistance", "sp": "support",
    "ko": "key_observation", "rb": "recent_bars",
    "op": "open", "hi": "high", "lo": "low", "cl": "close", "vo": "volume",
    "cx": "contract_info", "sy": "symbol", "pr": "periods",
    "bc": "bar_counts", "at": "analysis_time", "ev": "extraction_version",
    "si": "strategy_info", "sn": "strategy",
    "ra": "resonance_analysis", "fa": "four_periods_aligned",
    "ad": "alignment_direction", "ds": "description",
    "cn": "contradiction", "dp": "dominant_period_state",
    "sa": "scenario_analysis", "pk": "probability_rank",
    "sc": "scenario", "pj": "probability_judgment",
    "tc": "trigger_conditions", "cs": "confidence_score",
    "cr": "confidence_reason", "co": "core_observation",
    "sm": "summary", "rw": "risk_warning",
    "ai": "analyst_id",
}

def decompress(data: dict) -> dict:
    if not isinstance(data, dict):
        return data
    payload = data.get("d", data)
    def decode(obj):
        if isinstance(obj, dict):
            new_obj = {}
            for k, v in obj.items():
                full_key = KEY_MAP.get(k, k)
                new_obj[full_key] = decode(v)
            return new_obj
        elif isinstance(obj, list):
            return [decode(item) for item in obj]
        else:
            return obj
    return decode(payload)

def is_compressed(data: dict) -> bool:
    return isinstance(data, dict) and "d" in data and "k" not in data

# ---------- File Loading ----------
def load_responses_from_dir(directory: str = "responses", pattern: str = None) -> List[Dict[str, Any]]:
    if not os.path.isdir(directory):
        print(f"[Fusion] Directory {directory} not found")
        return []
    files = glob.glob(os.path.join(directory, "*.json"))
    if pattern:
        files = [f for f in files if pattern in os.path.basename(f)]
    print(f"[Fusion] Found {len(files)} JSON files:")
    for f in files:
        print(f"  - {os.path.basename(f)}")
    responses = []
    for fpath in sorted(files):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if is_compressed(data):
                    print(f"[Fusion] Decompressing {os.path.basename(fpath)}...")
                    data = decompress(data)
                responses.append(data)
                print(f"[Fusion] Loaded: {os.path.basename(fpath)}")
        except Exception as e:
            print(f"[Fusion] Failed to load {fpath}: {e}")
    return responses

# ---------- Validation ----------
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
    final_sup = select_three(unique_sup, False)
    final_res = select_three(unique_res, True)
    print(f"[Fusion] Final supports: {final_sup}, resistances: {final_res}")
    return {"resistance": final_res, "support": final_sup}

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
        print("[Fusion] No data.")
        return
    valid = []
    for i, r in enumerate(responses, 1):
        if validate_response(r, CURRENT_PRICE, f"Respondent{i}"):
            valid.append(r)
    if not valid:
        print("[Fusion] No valid responses.")
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
        s["probability_rank"] = i+1

    final_levels = fuse_levels(valid, CURRENT_PRICE)
    confidences = [r["confidence_score"] for r in valid]
    final_conf = statistics.median(confidences)
    best = max(valid, key=lambda x: x.get("confidence_score", 0))

    contract_info = {}
    source_symbols = []
    for r in valid:
        ci = r.get("contract_info", {})
        if not contract_info and ci:
            contract_info = ci
        sym = ci.get("symbol", ci.get("sy", "unknown"))
        source_symbols.append(sym)

    best_analysis = best.get("resonance_analysis") or best.get("regression_analysis", {})

    final_output = {
        "contract_info": contract_info,
        "resonance_analysis": {
            "three_periods_aligned": best_analysis.get("three_periods_aligned",
                                      best_analysis.get("four_periods_aligned", "No")),
            "alignment_direction": final_align,
            "description": best_analysis.get("description", ""),
            "contradiction": best_analysis.get("contradiction", ""),
            "dominant_period_state": best_analysis.get("dominant_period_state",
                                       best_analysis.get("overbought_oversold_detail", ""))
        },
        "scenario_analysis": final_scenarios,
        "key_levels": final_levels,
        "confidence_score": final_conf,
        "confidence_reason": best.get("confidence_reason", ""),
        "core_observation": best.get("core_observation", ""),
        "summary": best.get("summary", ""),
        "risk_warning": best.get("risk_warning", ""),
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