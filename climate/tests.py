"""Offline verification using an archived, real NASA POWER response."""
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase
import requests

from .services import (
    MONTHS, POWER_URL, NASADataUnavailable, _parse_power,
    apply_scenario, get_climate, is_nasa_climate,
)

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "nasa_power_climatology.json"


def power_payload():
    with FIXTURE.open(encoding="utf-8") as stream:
        return json.load(stream)


class ClimateServiceTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def response(self, payload=None):
        response = Mock()
        response.json.return_value = payload if payload is not None else power_payload()
        response.url = POWER_URL + "?latitude=24.3745&longitude=88.6042&community=AG&format=JSON"
        return response

    def baseline(self):
        return _parse_power(power_payload(), 24.3745, 88.6042, self.response().url)

    @patch("climate.services.requests.get")
    def test_real_nasa_fixture_retains_raw_response_source_period_and_units(self, get):
        original = power_payload()
        get.return_value = self.response(original)
        result = get_climate(24.3745, 88.6042)
        self.assertTrue(is_nasa_climate(result))
        self.assertEqual(result["raw_response"], original)
        self.assertEqual(result["provenance"]["period"], original["header"]["range"])
        self.assertEqual(result["provenance"]["request_parameters"]["latitude"], 24.3745)
        self.assertEqual(result["provenance"]["parameter_units"]["PRECTOTCORR"], original["parameters"]["PRECTOTCORR"]["units"])
        self.assertEqual(len(result["monthly_data"]), 12)
        self.assertIn("not a SMAP retrieval", result["soil_moisture"]["description"])
        self.assertEqual(result["monthly_data"][0]["precip_mm"], round(original["properties"]["parameter"]["PRECTOTCORR"]["JAN"] * 31, 1))

    @patch("climate.services.requests.get")
    def test_daily_rain_conversion_uses_units_not_magnitude(self, get):
        payload = power_payload()
        payload["properties"]["parameter"]["PRECTOTCORR"] = {month: 30 for month in MONTHS}
        get.return_value = self.response(payload)
        result = get_climate(24.3745, 88.6042)
        self.assertEqual(result["monthly_data"][0]["precip_mm"], 930)
        self.assertEqual(result["monthly_data"][1]["precip_mm"], 847.5)

    @patch("climate.services.requests.get")
    def test_monthly_mm_metadata_prevents_double_conversion(self, get):
        payload = power_payload()
        payload["parameters"]["PRECTOTCORR"]["units"] = "mm"
        payload["properties"]["parameter"]["PRECTOTCORR"] = {month: 8 for month in MONTHS}
        get.return_value = self.response(payload)
        self.assertEqual(get_climate(24.3745, 88.6042)["monthly_data"][0]["precip_mm"], 8)

    @patch("climate.services.requests.get")
    def test_missing_required_observation_raises_without_synthetic_fallback(self, get):
        payload = power_payload()
        payload["properties"]["parameter"]["T2M"]["FEB"] = -999
        get.return_value = self.response(payload)
        with self.assertRaisesMessage(NASADataUnavailable, "No sample data has been substituted"):
            get_climate(24.3745, 88.6042)

    @patch("climate.services.requests.get", side_effect=requests.Timeout)
    def test_timeout_raises_and_failure_marker_never_becomes_climate_data(self, get):
        for attempt in range(2):
            with self.subTest(attempt=attempt), self.assertRaises(NASADataUnavailable):
                get_climate(24.3745, 88.6042)
        self.assertEqual(get.call_count, 1)

    @patch("climate.services.requests.get")
    def test_refresh_can_recover_immediately_after_network_failure(self, get):
        get.side_effect = [requests.Timeout(), self.response()]
        with self.assertRaises(NASADataUnavailable):
            get_climate(24.3745, 88.6042)
        result = get_climate(24.3745, 88.6042, refresh=True)
        self.assertTrue(is_nasa_climate(result))
        self.assertEqual(get.call_count, 2)

    @patch("climate.services.requests.get")
    def test_http_error_and_malformed_json_cannot_produce_analysis(self, get):
        response = self.response()
        response.raise_for_status.side_effect = requests.HTTPError("503")
        get.return_value = response
        with self.assertRaises(NASADataUnavailable):
            get_climate(24.3745, 88.6042)
        cache.clear()
        response.raise_for_status.side_effect = None
        response.json.side_effect = ValueError("Invalid JSON")
        with self.assertRaises(NASADataUnavailable):
            get_climate(24.3745, 88.6042)

    @patch("climate.services.requests.get")
    def test_cache_is_coordinate_specific_and_returns_independent_real_data(self, get):
        get.return_value = self.response()
        get_climate(24.3745, 88.6042)
        result = get_climate(24.3745, 88.6042)
        result["monthly_data"][0]["precip_mm"] = -1
        result["raw_response"]["properties"]["parameter"]["T2M"]["JAN"] = -1
        fresh_copy = get_climate(24.3745, 88.6042)
        self.assertGreater(fresh_copy["monthly_data"][0]["precip_mm"], 0)
        self.assertGreater(fresh_copy["raw_response"]["properties"]["parameter"]["T2M"]["JAN"], 0)
        self.assertEqual(get.call_count, 1)
        get_climate(25.75, 89.25)
        get_climate(24.3745, 88.6042, refresh=True)
        self.assertEqual(get.call_count, 3)

    @patch("climate.services.requests.get")
    def test_optional_missing_wetness_remains_unknown_without_fake_smap(self, get):
        payload = power_payload()
        payload["properties"]["parameter"].pop("GWETROOT")
        get.return_value = self.response(payload)
        result = get_climate(24.3745, 88.6042)
        self.assertIsNone(result["soil_moisture"]["relative_wetness"])
        self.assertEqual(result["soil_moisture"]["status"], "unavailable")

    def test_scenario_preserves_real_baseline_and_raw_observations(self):
        baseline = self.baseline()
        original = deepcopy(baseline)
        result = apply_scenario(baseline, -20, 2)
        self.assertEqual(baseline, original)
        self.assertEqual(result["raw_response"], original["raw_response"])
        self.assertEqual(result["monthly_data"][0]["precip_mm"], round(baseline["monthly_data"][0]["precip_mm"] * .8, 1))
        self.assertEqual(result["monthly_data"][0]["temp_mean_c"], round(baseline["monthly_data"][0]["temp_mean_c"] + 2, 2))
        self.assertEqual(result["monthly_data"][0]["soil_wetness_root"], baseline["monthly_data"][0]["soil_wetness_root"])
        self.assertIn("not a climate forecast", result["scenario"]["disclaimer"])

    def test_scenario_rejects_legacy_synthetic_or_unsourced_baselines(self):
        for baseline in [{"status": "demo"}, {"status": "live", "monthly_data": [{}] * 12}]:
            with self.assertRaises(NASADataUnavailable):
                apply_scenario(baseline, -20, 2)

    def test_invalid_coordinates_and_nonfinite_scenarios_are_rejected(self):
        for latitude, longitude in [(91, 0), (0, 181), (float("nan"), 0)]:
            with self.assertRaises(ValueError):
                get_climate(latitude, longitude)
        baseline = self.baseline()
        for rain, temperature in [(float("nan"), 0), (-51, 0), (0, 6)]:
            with self.assertRaises(ValueError):
                apply_scenario(baseline, rain, temperature)

    @patch("climate.services.requests.get")
    def test_verify_command_uses_the_runtime_client_and_prints_actual_provenance(self, get):
        get.return_value = self.response()
        output = StringIO()
        call_command("verify_nasa", latitude=24.3745, longitude=88.6042, stdout=output)
        self.assertIn("Verified real NASA POWER data", output.getvalue())
        self.assertIn(power_payload()["header"]["range"], output.getvalue())
        self.assertIn("Original response preserved: True", output.getvalue())
        get.assert_called_once()
