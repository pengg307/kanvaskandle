#!/usr/bin/env python3
"""
Multi-respondent voting & validation fusion system v1.0
- Loads resonance analysis JSONs from responses/ folder
- Validates price level logic
- Outputs timestamped archive + latest fusion_result.json
- Extracts contract_info for symbol tracking
"""

import json
import statistics
import os
import glob
from typing import List, Dict, Any, Tuple
from datetime import datetime

CURRENT_PRICE = 2898  # adjust to the latest price of the analyzed symbol

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
                responses.append(data)
                print(f"[Fusion] Loaded: {os.path.basename(fpath)}")
        except Exception as e:
            print(f"[Fusion] Failed to load {fpath}: {e}")
    return responses

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
            return False
        if not all(k in response for k in ["resonance_analysis", "scenario_analysis", "confidence_score"]):
            return False
    except Exception:
        return False
    return validate_levels(levels, price, source)

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

def main():
    print("=== Fusion Start ===")
    responses = load_responses_from_dir("responses")
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

    align_votes = [r["resonance_analysis"]["alignment_direction"] for r in valid]
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
    for r in valid:
        if "contract_info" in r:
            contract_info = r["contract_info"]
            break
    if not contract_info and "contract_meta" in best:
        contract_info = best["contract_meta"]
    symbol = contract_info.get("symbol", "unknown")

    final_output = {
        "contract_info": contract_info,
        "resonance_analysis": {
            "three_periods_aligned": best["resonance_analysis"].get("three_periods_aligned", "No"),
            "alignment_direction": final_align,
            "description": best["resonance_analysis"].get("description", ""),
            "contradiction": best["resonance_analysis"].get("contradiction", ""),
            "dominant_period_state": best["resonance_analysis"].get("dominant_period_state", "")
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
            "scenario_vote": vote_desc,
            "levels_method": "Intersection+Median",
            "confidence_method": "Median"
        }
    }

    print(json.dumps(final_output, ensure_ascii=False, indent=2))
    os.makedirs("output", exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive = f"output/fusion_{symbol}_{ts}.json"
    with open(archive, "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    with open("output/fusion_result.json", "w", encoding="utf-8") as f:
        json.dump(final_output, f, ensure_ascii=False, indent=2)
    print(f"[Fusion] Saved: {archive} and fusion_result.json")

if __name__ == "__main__":
    main()