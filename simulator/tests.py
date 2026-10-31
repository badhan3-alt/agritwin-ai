from copy import deepcopy
from unittest.mock import patch

from django.test import SimpleTestCase

from rotations.tests import sample_climate, sample_farm
from .services import simulate


class SimulatorServiceTests(SimpleTestCase):
    def setUp(self):
        self.farm = sample_farm()
        self.climate = sample_climate()

    @patch("climate.services.requests.get")
    def test_zero_change_is_identical_and_never_refetches(self, get):
        original = deepcopy(self.climate)
        result = simulate(self.farm, self.climate, 0, 0, "limited", "water_conservation")
        self.assertEqual(len(result["strategies_comparison"]), 3)
        self.assertTrue(all(item["score_change_delta"] == 0 for item in result["strategies_comparison"]))
        self.assertEqual(self.climate, original)
        get.assert_not_called()

    def test_less_rain_does_not_improve_water_component(self):
        result = simulate(self.farm, self.climate, -40, 3, "limited", "water_conservation")
        for item in result["strategies_comparison"]:
            self.assertLessEqual(item["component_changes"]["water"], 0)
            self.assertIn("score points", item["sensitivity_impact_summary"])

    def test_irrigation_and_priority_change_are_explained(self):
        result = simulate(self.farm, self.climate, 0, 0, "abundant", "soil_health")
        for item in result["strategies_comparison"]:
            self.assertGreaterEqual(item["component_changes"]["water"], 0)
            self.assertIn("priority weights changed", item["sensitivity_impact_summary"])
        self.assertEqual(result["parameters"]["priority"], "soil_health")

    def test_no_recommendation_when_all_strategies_blocked(self):
        self.farm["soil_ph"] = 3
        result = simulate(self.farm, self.climate, -20, 2)
        self.assertIsNone(result["top_strategy"])
        self.assertIn("No candidate", result["key_takeaway"])

    def test_scenario_uses_nasa_baseline_and_changes_water_or_heat_scores(self):
        result = simulate(self.farm, self.climate, -50, 5, "limited", "water_conservation")
        self.assertEqual(result["climate"]["status"], "live")
        self.assertEqual(result["climate"]["raw_response"], self.climate["raw_response"])
        self.assertTrue(any(item["score_change_delta"] != 0 for item in result["strategies_comparison"]))
        self.assertTrue(any(item["component_changes"]["water"] < 0 or item["component_changes"]["climate"] < 0 for item in result["strategies_comparison"]))

    def test_synthetic_baseline_cannot_be_simulated(self):
        self.climate["status"] = "demo"
        with self.assertRaises(ValueError):
            simulate(self.farm, self.climate, -20, 2)
