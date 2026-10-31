"""Transparent, deliberately simple Bangladesh crop-rotation screening.

Profile numbers are prototype assumptions, not measured crop requirements or
yield/profit predictions. All ranking calculations remain on the server.
"""
from calendar import month_name
from datetime import date, timedelta
from functools import lru_cache
import json
import math
from pathlib import Path
from climate.provenance import is_nasa_climate

PRIORITY_WEIGHTS = {
    "water_conservation": {"water": .45, "climate": .25, "soil": .15, "economic": .15},
    "soil_health": {"water": .20, "climate": .20, "soil": .40, "economic": .20},
    "economic_return": {"water": .20, "climate": .20, "soil": .15, "economic": .45},
    "climate_resilience": {"water": .30, "climate": .35, "soil": .20, "economic": .15},
}
THERMAL_UPPER_MEAN = {"aman_rice": 32, "boro_rice": 30, "lentil": 25, "mustard": 27, "mung_bean": 32, "maize": 30, "wheat": 25}
TURNAROUND_DAYS = 7


@lru_cache(maxsize=1)
def get_crop_database():
    with (Path(__file__).parent / "data" / "crop_profiles.json").open(encoding="utf-8") as stream:
        return json.load(stream)


def get_crops():
    return list(get_crop_database()["crops"].values())


def get_regions():
    from farms.regions import REGIONS
    return [dict(region) for region in REGIONS]


def _clamp(value):
    return round(max(0, min(100, value)), 1)


def validate_calendar(sequence_ids):
    """Find sequential planting dates that satisfy windows and annual repetition.

    A seven-day field turnaround is required after each crop, including the last
    harvest before the next annual cycle. A duration-only sum cannot pass this
    check. It is still a generic window check, not a variety-specific calendar.
    """
    profiles = get_crop_database()["crops"]
    unknown = [key for key in sequence_ids if key not in profiles]
    crops = [profiles[key] for key in sequence_ids if key in profiles]
    total = sum(crop["duration_days"] for crop in crops)
    result = {"is_feasible": False, "total_cropping_days": total,
        "fallow_turnaround_days": 365 - total, "schedule": [],
        "description": "No sequential schedule fits the prototype planting/harvest windows with seven-day turnarounds within a repeating year."}
    if unknown or not crops:
        result["description"] = "Missing or unsupported crops prevent calendar verification."
        return result
    if total + len(crops) * TURNAROUND_DAYS > 365:
        return result
    start_of_year = date(2025, 1, 1)
    horizon = start_of_year + timedelta(days=365 * 2)
    starts_by_crop = {}
    for crop in crops:
        if crop["id"] in starts_by_crop:
            continue
        starts = []
        cursor = start_of_year
        while cursor < horizon:
            finish = cursor + timedelta(days=crop["duration_days"] - 1)
            if cursor.month in crop["planting_months"] and finish.month in crop["harvest_months"]:
                starts.append((cursor, finish))
            cursor += timedelta(days=1)
        starts_by_crop[crop["id"]] = starts
    first_crop = crops[0]
    for first_start, first_end in starts_by_crop[first_crop["id"]]:
        if first_start.year != 2025:
            break
        cycle_end = first_start + timedelta(days=365 - TURNAROUND_DAYS)
        path = [(first_crop, first_start, first_end)]
        previous_end = first_end
        for crop in crops[1:]:
            earliest = previous_end + timedelta(days=TURNAROUND_DAYS + 1)
            candidate = next(((start, end) for start, end in starts_by_crop[crop["id"]]
                if start >= earliest and end < cycle_end), None)
            if candidate is None:
                break
            path.append((crop, *candidate))
            previous_end = candidate[1]
        if len(path) == len(crops) and previous_end < cycle_end:
            result.update({"is_feasible": True,
                "description": "Prototype planting and harvest windows fit a repeating year with at least seven days between crops. Confirm variety, drainage and actual Aman harvest date locally.",
                "schedule": [{"crop": crop["name"], "crop_id": crop["id"],
                    "planting": start.strftime("%d %b"), "harvest": end.strftime("%d %b"),
                    "planting_date": start.isoformat(), "harvest_date": end.isoformat()}
                    for crop, start, end in path]})
            return result
    return result


def _season_climate(crop, schedule, monthly):
    """Approximate rain within planted dates using uniform within-month rain."""
    if not schedule:
        months = set(crop["planting_months"] + crop["harvest_months"])
        selected = [row for index, row in enumerate(monthly, 1) if index in months]
        return sum(row["precip_mm"] for row in selected), sum(row["temp_mean_c"] for row in selected) / max(1, len(selected))
    start = date.fromisoformat(schedule["planting_date"])
    end = date.fromisoformat(schedule["harvest_date"])
    current = start
    rain = temperature = days = 0
    # This is an indicator, not an evapotranspiration/crop-water balance model.
    from calendar import monthrange
    while current <= end:
        row = monthly[current.month - 1]
        rain += row["precip_mm"] / monthrange(current.year, current.month)[1]
        temperature += row["temp_mean_c"]
        days += 1
        current += timedelta(days=1)
    return rain, temperature / days


def evaluate_rotations(farm_info, climate):
    if not is_nasa_climate(climate):
        raise ValueError("A validated NASA POWER baseline is required to compare rotations.")
    profiles = get_crop_database()["crops"]
    current_ids = farm_info.get("current_crops") or ["aman_rice", "boro_rice"]
    if not isinstance(current_ids, (list, tuple)):
        raise ValueError("Current crops must be an ordered list of crop IDs.")
    candidates = [
        ("current", "Your current rotation", "existing", list(current_ids), "Your entered crop sequence provides the comparison baseline."),
        ("legume", "Introduce a legume", "legume", ["aman_rice", "lentil"], "Explore Aman rice followed by lentil, with the remaining season fallow."),
        ("diversified", "Diversify across seasons", "diversified", ["aman_rice", "mustard", "mung_bean"], "Explore rice, a short-duration oilseed and a summer pulse in one annual cycle."),
    ]
    baseline_demand = sum(profiles.get(key, {}).get("water_demand_mm", 0) for key in current_ids)
    irrigation = farm_info.get("irrigation_availability", "limited")
    priority = farm_info.get("farming_priority", "water_conservation")
    if irrigation not in {"limited", "moderate", "abundant"} or priority not in PRIORITY_WEIGHTS:
        raise ValueError("Unknown irrigation availability or farming priority.")
    weights = PRIORITY_WEIGHTS[priority]
    soil = farm_info.get("soil_type", "unknown")
    ph = farm_info.get("soil_ph")
    ph = None if ph in (None, "") else float(ph)
    latitude, longitude = float(farm_info.get("latitude", 24.3745)), float(farm_info.get("longitude", 88.6042))
    supported = math.isfinite(latitude) and math.isfinite(longitude) and 20.5 <= latitude <= 26.7 and 88 <= longitude <= 92.8
    drainage = farm_info.get("drainage", "unknown")
    monthly = climate["monthly_data"]
    if len(monthly) != 12:
        raise ValueError("Twelve monthly climate observations are required.")
    results = []
    for strategy_id, name, kind, ids, description in candidates:
        crops = [profiles[key] for key in ids if key in profiles]
        calendar = validate_calendar(ids)
        blocked, risks, benefits = [], [], []
        unknown_ids = [key for key in ids if key not in profiles]
        if unknown_ids:
            blocked.append("The current rotation contains an unsupported crop; update the farm profile.")
        if not supported:
            blocked.append("This prototype crop calendar is for Bangladesh. Coordinates outside the Bangladesh planning envelope cannot be ranked as suitable.")
        if not calendar["is_feasible"]:
            blocked.append("Crop planting/harvest windows do not fit a repeating annual sequence.")
        total_demand = sum(crop["water_demand_mm"] for crop in crops)
        has_legume = any(crop["nitrogen_fixing"] for crop in crops)
        if drainage == "poor" and any(crop["id"] in {"lentil", "mung_bean", "mustard"} for crop in crops):
            blocked.append("Reported poor drainage or waterlogging conflicts with the pulse/oilseed crop profile. Resolve drainage and obtain local agronomic advice before considering this sequence.")
        if irrigation == "limited" and any(crop["irrigation_need"] == "intensive_groundwater" for crop in crops):
            blocked.append("The entered limited irrigation availability does not meet the intensive dry-season irrigation requirement in the Boro rice profile.")
        irrigation_need, thermal_penalty = 0, 0
        for index, crop in enumerate(crops):
            schedule = calendar["schedule"][index] if calendar["schedule"] else None
            crop_rain, crop_temperature = _season_climate(crop, schedule, monthly)
            irrigation_need += max(0, crop["water_demand_mm"] - .65 * crop_rain)
            thermal_penalty += max(0, crop_temperature - THERMAL_UPPER_MEAN.get(crop["id"], 30)) * 8
            if soil != "unknown" and soil not in crop["preferred_soils"]:
                blocked.append(f"{crop['name']}: entered soil texture is outside this prototype profile's preferred soils; verify drainage and suitability locally.")
            if ph is not None and (not math.isfinite(ph) or not crop["ph_min"] <= ph <= crop["ph_max"]):
                blocked.append(f"{crop['name']}: entered pH is outside the profile range {crop['ph_min']}–{crop['ph_max']}.")
        available_irrigation = {"limited": 100, "moderate": 450, "abundant": 900}[irrigation]
        unmet_indicator = max(0, irrigation_need - available_irrigation)
        water = _clamp(100 - 100 * unmet_indicator / max(1, total_demand))
        climate_score = _clamp(90 - thermal_penalty / max(1, len(crops)))
        soil_score = _clamp(sum(crop["soil_health_score"] for crop in crops) / max(1, len(crops)) + (8 if has_legume else 0) + (5 if len(set(ids)) >= 3 else 0))
        economic = sum(crop["economic_margin_score"] for crop in crops) / max(1, len(crops))
        budget = farm_info.get("budget", "medium")
        if budget == "low":
            economic -= 15 if "boro_rice" in ids else 0
            economic -= 8 if len(ids) >= 3 else 0
        components = {"water": water, "climate": climate_score, "soil": soil_score, "economic": _clamp(economic)}
        composite = round(sum(weights[key] * value for key, value in components.items()), 1)
        if total_demand < baseline_demand:
            benefits.append("Lower assumed total crop-water demand than your current sequence.")
        if has_legume:
            benefits.append("A legume can contribute biological nitrogen fixation and crop diversity when well managed.")
            risks.append("Pulses are vulnerable to waterlogging; verify field drainage before planting.")
        if kind == "existing":
            benefits.append("Keeps the crop sequence you entered and familiar management practices.")
        if len(set(crop["category"] for crop in crops)) >= 3:
            benefits.append("Includes cereal, oilseed and pulse crops across the year.")
        if unmet_indicator > 100:
            risks.append("The screening water-demand indicator exceeds the assumed irrigation allowance; confirm a reliable water supply.")
        if len(ids) >= 3:
            risks.append("Three crops require timely harvests and field preparation; a late Aman harvest may prevent the winter crop.")
        if thermal_penalty > 0:
            risks.append("Growing-period mean temperatures exceed at least one prototype crop threshold; review planting time and variety.")
        uncertainties = [
            "Suitability is a relative rule-based score, not a probability of success or a yield forecast.",
            "Crop durations, water demands, soil scores and economic scores are prototype assumptions requiring local agronomic validation.",
            "No local crop prices, production costs, field drainage or salinity measurements are available; economic scores do not predict profit.",
            "Bangladesh bounding coordinates provide a coarse planning envelope, not a verified national boundary or field polygon.",
        ]
        if soil == "unknown":
            uncertainties.insert(0, "Soil texture unknown: verify drainage and texture locally before deciding.")
        if drainage == "unknown":
            uncertainties.insert(0, "Field drainage unknown: verify waterlogging risk before planting pulses or oilseeds; satellite regional wetness cannot establish field drainage.")
        if ph is None:
            uncertainties.insert(0, "Soil pH unverified: NASA data cannot replace a local soil test.")
        if climate.get("annual_summary", {}).get("rabi_soil_wetness_avg") is None:
            uncertainties.append("Regional soil-wetness data is unavailable; no field moisture value is inferred.")
        results.append({
            "id": strategy_id, "name": name, "type": kind, "description": description,
            "sequence": [{key: crop[key] for key in ("id", "name", "season", "duration_days", "water_demand_mm")} for crop in crops],
            "composite_score": composite, "components": components, "weights": dict(weights),
            "benefits": benefits, "risks": risks + blocked, "uncertainties": uncertainties,
            "calendar": calendar, "water_demand_mm": total_demand,
            "water_saving_pct": round(100 * (baseline_demand - total_demand) / baseline_demand, 1) if baseline_demand else 0,
            "nitrogen_benefit": "Potential biological nitrogen contribution from a legume; not measured or quantified for this field." if has_legume else "No nitrogen-fixing legume in this sequence.",
            "is_eligible": not blocked, "blocked_reasons": blocked,
            "water_assumptions": {"effective_rain_fraction": .65, "annual_irrigation_allowance_mm": available_irrigation,
                "description": "Simple screening allowance only; farm size does not change the per-area demand indicator. Not an irrigation prescription."},
        })
    return sorted(results, key=lambda item: (item["is_eligible"], item["composite_score"]), reverse=True)
