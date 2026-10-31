from copy import deepcopy
import json
from pathlib import Path

from django.test import SimpleTestCase

from climate.services import _parse_power
from .services import PRIORITY_WEIGHTS, evaluate_rotations, validate_calendar


def sample_farm():
    return {"latitude": 24.3745, "longitude": 88.6042, "current_crops": ["aman_rice", "boro_rice"],
        "soil_type": "unknown", "soil_ph": None, "irrigation_availability": "limited",
        "farming_priority": "water_conservation", "budget": "medium", "farm_size_acres": 3}

def sample_climate():
    payload = json.loads((Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "nasa_power_climatology.json").read_text(encoding="utf-8"))
    return _parse_power(payload, 24.3745, 88.6042, "https://power.larc.nasa.gov/api/temporal/climatology/point?latitude=24.3745&longitude=88.6042")


class RotationServiceTests(SimpleTestCase):
    def setUp(self):
        self.farm = sample_farm()
        self.climate = sample_climate()

    def test_three_candidates_preserve_actual_current_crops(self):
        self.farm["current_crops"] = ["aman_rice", "wheat"]
        result = evaluate_rotations(self.farm, self.climate)
        self.assertEqual(len(result), 3)
        current = next(item for item in result if item["type"] == "existing")
        self.assertEqual([item["id"] for item in current["sequence"]], ["aman_rice", "wheat"])

    def test_candidate_calendars_fit_real_windows_with_turnaround(self):
        for ids in (["aman_rice", "boro_rice"], ["aman_rice", "lentil"], ["aman_rice", "mustard", "mung_bean"]):
            result = validate_calendar(ids)
            self.assertTrue(result["is_feasible"], ids)
            self.assertEqual(len(result["schedule"]), len(ids))
        self.assertEqual(validate_calendar(["aman_rice", "lentil"])["total_cropping_days"], 240)

    def test_overlapping_seasons_fail_even_when_duration_sum_would_fit(self):
        result = validate_calendar(["lentil", "wheat"])
        self.assertLess(result["total_cropping_days"], 300)
        self.assertFalse(result["is_feasible"])
        self.assertFalse(validate_calendar(["unlisted_crop"])["is_feasible"])

    def test_water_priority_ranks_low_demand_legume_above_irrigated_rice(self):
        result = {item["id"]: item for item in evaluate_rotations(self.farm, self.climate)}
        self.assertGreater(result["legume"]["components"]["water"], result["current"]["components"]["water"])
        self.assertGreater(result["legume"]["composite_score"], result["current"]["composite_score"])
        self.assertTrue(any("pH unverified" in item for item in result["legume"]["uncertainties"]))

    def test_known_soil_and_ph_constraints_gate_eligibility(self):
        self.farm["soil_type"] = "clay"
        result = {item["id"]: item for item in evaluate_rotations(self.farm, self.climate)}
        self.assertFalse(result["legume"]["is_eligible"])
        self.assertTrue(result["legume"]["blocked_reasons"])
        self.farm["soil_type"] = "unknown"
        self.farm["soil_ph"] = 3.5
        self.assertTrue(all(not item["is_eligible"] for item in evaluate_rotations(self.farm, self.climate)))

    def test_unsupported_region_is_never_recommended(self):
        self.farm.update(latitude=51.5, longitude=-.12)
        result = evaluate_rotations(self.farm, self.climate)
        self.assertTrue(all(not item["is_eligible"] for item in result))

    def test_poor_drainage_blocks_pulse_and_oilseed_rotations(self):
        self.farm["drainage"] = "poor"
        result = {item["id"]: item for item in evaluate_rotations(self.farm, self.climate)}
        for strategy in ("legume", "diversified"):
            self.assertFalse(result[strategy]["is_eligible"])
            self.assertTrue(any("poor drainage" in reason for reason in result[strategy]["blocked_reasons"]))

    def test_unknown_drainage_is_an_uncertainty_not_an_invented_measurement(self):
        self.farm["drainage"] = "unknown"
        for item in evaluate_rotations(self.farm, self.climate):
            self.assertTrue(any("Field drainage unknown" in reason for reason in item["uncertainties"]))

    def test_known_irrigation_constraint_blocks_intensive_dry_season_rice(self):
        result = {item["id"]: item for item in evaluate_rotations(self.farm, self.climate)}
        self.assertFalse(result["current"]["is_eligible"])
        self.assertTrue(any("limited irrigation" in reason for reason in result["current"]["blocked_reasons"]))

    def test_form_longitude_boundary_is_within_supported_envelope(self):
        self.farm.update(latitude=23, longitude=92.8)
        result = evaluate_rotations(self.farm, self.climate)
        self.assertFalse(any("outside the Bangladesh" in reason for item in result for reason in item["blocked_reasons"]))

    def test_weights_sum_to_one_and_composite_reconstructs(self):
        for priority, weights in PRIORITY_WEIGHTS.items():
            self.assertAlmostEqual(sum(weights.values()), 1)
            self.farm["farming_priority"] = priority
            for item in evaluate_rotations(self.farm, self.climate):
                expected = round(sum(item["components"][key] * weight for key, weight in item["weights"].items()), 1)
                self.assertEqual(item["composite_score"], expected)
                self.assertTrue(0 <= expected <= 100)

    def test_evaluation_does_not_mutate_farmer_profile(self):
        original = deepcopy(self.farm)
        evaluate_rotations(self.farm, self.climate)
        self.assertEqual(self.farm, original)

    def test_synthetic_climate_cannot_produce_rotation_scores(self):
        self.climate["status"] = "demo"
        with self.assertRaises(ValueError):
            evaluate_rotations(self.farm, self.climate)
