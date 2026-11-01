"""Weather transport/validation and private forecast pages, without network."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

import requests
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from farms.models import Farm
from weather.services import DHAKA, WeatherUnavailable, get_weather


def provider_payload():
    now = timezone.now().astimezone(DHAKA).replace(second=0, microsecond=0)
    return {
        "timezone": "Asia/Dhaka", "utc_offset_seconds": 21600,
        "current_units": {"temperature_2m": "°C", "relative_humidity_2m": "%", "precipitation": "mm", "weather_code": "wmo code", "wind_speed_10m": "km/h"},
        "current": {"time": now.isoformat(timespec="minutes"), "interval": 900, "temperature_2m": 28.5, "relative_humidity_2m": 77, "precipitation": 0.2, "weather_code": 61, "wind_speed_10m": 12.1},
        "daily_units": {"weather_code": "wmo code", "temperature_2m_max": "°C", "temperature_2m_min": "°C", "precipitation_sum": "mm", "precipitation_probability_max": "%", "wind_speed_10m_max": "km/h"},
        "daily": {
            "time": [(now.date() + timedelta(days=i)).isoformat() for i in range(7)],
            "weather_code": [61, 3, 2, 1, 0, 63, 95],
            "temperature_2m_max": [32] * 7, "temperature_2m_min": [23] * 7,
            "precipitation_sum": [2.5, 0, 0, 0, 0, 20, 35],
            "precipitation_probability_max": [50, 10, 5, 0, 0, 80, 90],
            "wind_speed_10m_max": [20] * 7,
        },
    }


class WeatherTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.farm = Farm.objects.create(owner_session=session.session_key, **Farm.example_defaults())
        self.payload = provider_payload()
        mocker = patch("weather.services.requests.get")
        self.network = mocker.start()
        self.addCleanup(mocker.stop)
        self.network.return_value.raise_for_status.return_value = None
        self.network.return_value.json.side_effect = lambda: deepcopy(self.payload)

    def test_valid_response_uses_explicit_units_timezone_and_seven_days(self):
        result = get_weather(24.3745, 88.6042)
        self.assertEqual(result["current"]["temperature_c"], 28.5)
        self.assertEqual(result["current"]["interval_minutes"], 15)
        self.assertEqual(len(result["days"]), 7)
        params = self.network.call_args.kwargs["params"]
        self.assertEqual(params["timezone"], "Asia/Dhaka")
        self.assertEqual(params["forecast_days"], 7)
        self.assertEqual(params["precipitation_unit"], "mm")
        self.assertEqual(params["wind_speed_unit"], "kmh")
        self.assertIn("precipitation_probability_max", params["daily"])
        self.assertEqual(self.network.call_args.kwargs["timeout"], (4, 12))

    def test_success_is_cached_and_refresh_bypasses_it(self):
        first = get_weather(self.farm.latitude, self.farm.longitude)
        self.assertEqual(first, get_weather(self.farm.latitude, self.farm.longitude))
        self.network.assert_called_once()
        self.payload["current"]["temperature_2m"] = 30
        fresh = get_weather(self.farm.latitude, self.farm.longitude, refresh=True)
        self.assertEqual(fresh["current"]["temperature_c"], 30)
        self.assertEqual(self.network.call_count, 2)

    def test_other_coordinates_have_separate_cache(self):
        get_weather(24.3745, 88.6042)
        get_weather(25.0, 89.0)
        self.assertEqual(self.network.call_count, 2)

    def test_timeout_is_reported_without_fabricated_conditions(self):
        self.network.side_effect = requests.Timeout("provider unavailable")
        with self.assertRaises(WeatherUnavailable):
            get_weather(self.farm.latitude, self.farm.longitude)
        response = self.client.get(reverse("weather:dashboard", args=[self.farm.pk]))
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(response.context["forecast"])
        self.assertContains(response, "Weather is temporarily unavailable", status_code=503)
        self.assertNotContains(response, "28.5", status_code=503)

    def test_invalid_or_incomplete_provider_values_are_rejected(self):
        broken = []
        for field, value in (("temperature_2m", float("nan")), ("relative_humidity_2m", 101), ("precipitation", None), ("wind_speed_10m", -1), ("weather_code", True)):
            payload = provider_payload()
            payload["current"][field] = value
            broken.append(payload)
        missing_day = provider_payload()
        missing_day["daily"]["temperature_2m_max"].pop()
        broken.append(missing_day)
        wrong_units = provider_payload()
        wrong_units["daily_units"]["precipitation_sum"] = "inch"
        broken.append(wrong_units)
        wrong_timezone = provider_payload()
        wrong_timezone["timezone"] = "GMT"
        broken.append(wrong_timezone)
        inverted = provider_payload()
        inverted["daily"]["temperature_2m_max"][0] = 1
        broken.append(inverted)
        stale = provider_payload()
        stale["current"]["time"] = (timezone.now() - timedelta(days=1)).isoformat()
        broken.append(stale)
        for index, payload in enumerate(broken):
            with self.subTest(index=index):
                self.payload = payload
                with self.assertRaises(WeatherUnavailable):
                    get_weather(self.farm.latitude, self.farm.longitude, refresh=True)

    def test_wrong_forecast_dates_and_provider_errors_are_rejected(self):
        self.payload["daily"]["time"][1] = self.payload["daily"]["time"][0]
        with self.assertRaises(WeatherUnavailable):
            get_weather(self.farm.latitude, self.farm.longitude)
        self.payload = {"error": True, "reason": "invalid query"}
        with self.assertRaises(WeatherUnavailable):
            get_weather(self.farm.latitude, self.farm.longitude)

    def test_page_separates_forecast_from_nasa_and_shows_source(self):
        response = self.client.get(reverse("weather:dashboard", args=[self.farm.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Seven-day forecast")
        self.assertContains(response, "Light rain")
        self.assertContains(response, "NASA historical climate averages")
        self.assertContains(response, "https://open-meteo.com/en/docs")
        self.assertContains(response, "Asia/Dhaka")
        self.assertContains(response, "up to 15 minutes")
        self.assertFalse(hasattr(self.farm, "analysis"))

    def test_forecast_and_refresh_require_farm_ownership_before_network(self):
        outsider = Client()
        for route, method in (("weather:dashboard", outsider.get), ("weather:refresh", outsider.post)):
            response = method(reverse(route, args=[self.farm.pk]))
            self.assertEqual(response.status_code, 404)
        self.network.assert_not_called()

    def test_refresh_requires_post_and_csrf(self):
        url = reverse("weather:refresh", args=[self.farm.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        protected = Client(enforce_csrf_checks=True)
        self.assertEqual(protected.post(url).status_code, 403)
        self.network.assert_not_called()
        self.assertEqual(self.client.post(url).status_code, 200)

    def test_failed_refresh_shows_unavailable_instead_of_a_successful_status(self):
        get_weather(self.farm.latitude, self.farm.longitude)
        self.network.side_effect = requests.ConnectionError("offline")
        response = self.client.post(reverse("weather:refresh", args=[self.farm.pk]))
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(response.context["forecast"])
