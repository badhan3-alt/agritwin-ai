"""Sensitivity comparisons based on one stored climate baseline."""
from copy import deepcopy

from climate.services import apply_scenario
from rotations.services import evaluate_rotations


def simulate(farm_info, baseline_climate, rainfall_delta_pct=0, temp_delta_c=0, irrigation=None, priority=None):
    baseline = evaluate_rotations(farm_info, baseline_climate)
    altered_climate = apply_scenario(baseline_climate, rainfall_delta_pct, temp_delta_c)
    altered_farm = deepcopy(farm_info)
    if irrigation:
        altered_farm["irrigation_availability"] = irrigation
    if priority:
        altered_farm["farming_priority"] = priority
    scenarios = evaluate_rotations(altered_farm, altered_climate)
    baseline_by_id = {strategy["id"]: strategy for strategy in baseline}
    for strategy in scenarios:
        previous = baseline_by_id[strategy["id"]]
        delta = round(strategy["composite_score"] - previous["composite_score"], 1)
        changes = {key: round(strategy["components"][key] - previous["components"][key], 1) for key in strategy["components"]}
        factors = [f"{key} {value:+.1f}" for key, value in changes.items() if abs(value) >= .1]
        changed_priority = altered_farm.get("farming_priority") != farm_info.get("farming_priority")
        explanation = "; ".join(factors) if factors else "component scores unchanged"
        if changed_priority:
            explanation += "; priority weights changed"
        strategy.update({"baseline_score": previous["composite_score"], "scenario_score": strategy["composite_score"],
            "score_change_delta": delta, "component_changes": changes,
            "sensitivity_impact_summary": f"{delta:+.1f} score points: {explanation}."})
    eligible = [strategy for strategy in scenarios if strategy["is_eligible"]]
    return {"strategies_comparison": scenarios, "climate": altered_climate,
        "baseline_climate": baseline_climate["annual_summary"],
        "simulated_climate": altered_climate["annual_summary"],
        "parameters": {"rainfall_delta_pct": float(rainfall_delta_pct), "temp_delta_c": float(temp_delta_c),
            "irrigation": altered_farm.get("irrigation_availability"), "priority": altered_farm.get("farming_priority")},
        "disclaimer": "A sensitivity test of a simplified rule-based model, not a validated future climate, yield, profit or soil-moisture forecast. Regional wetness is held at baseline.",
        "top_strategy": eligible[0]["name"] if eligible else None,
        "key_takeaway": f"{eligible[0]['name']} has the highest eligible relative score under these assumptions." if eligible else "No candidate passes the supplied field and calendar constraints. Review local conditions before choosing a rotation.",
    }
