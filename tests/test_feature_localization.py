"""Farmer records remain bilingual without rewriting user data or measurements."""
from datetime import timedelta
from decimal import Decimal
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from farms.models import Farm
from notebook.models import DiaryEntry, LedgerEntry, SoilTest
from tests.test_localization import VisibleText


class FarmFeatureLanguageTests(TestCase):
    def setUp(self):
        session = self.client.session
        session.save()
        self.farm = Farm.objects.create(owner_session=session.session_key, **{**Farm.example_defaults(), "name": "পূর্বের মাঠ"})
        self.today = timezone.localdate()
        self.nasa_network = patch("climate.services.requests.get", side_effect=AssertionError("Farm records must not request climate data"))
        self.nasa_network.start()
        self.addCleanup(self.nasa_network.stop)

    def assert_bangla_page(self, response, heading):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Language"], "bn")
        self.assertContains(response, '<html lang="bn">')
        with translation.override("bn"):
            translated_heading = translation.gettext(heading)
        self.assertNotEqual(translated_heading, heading, f"Missing Bangla translation: {heading}")
        self.assertContains(response, translated_heading)
        parser = VisibleText()
        parser.feed(response.content.decode("utf-8"))
        text = " ".join(parser.text)
        bengali = len(re.findall(r"[\u0980-\u09ff]", text))
        english = len(re.findall(r"[A-Za-z]", text))
        # Technical units, provider attribution, and editable GeoJSON stay in
        # their source forms; the surrounding instructions must be Bangla.
        untranslated = [part.strip() for part in parser.text if re.search(r"[A-Za-z]{4,}", part) and not re.search(r"[\u0980-\u09ff]", part)]
        self.assertGreater(bengali / max(1, bengali + english), .65, untranslated)

    def test_guest_account_and_all_record_pages_default_to_bangla(self):
        routes = [
            ("accounts:signup", {}, "Create an account"),
            ("accounts:login", {}, "Sign in"),
            ("boundaries:editor", {"pk": self.farm.pk}, "Farm boundary"),
            ("notebook:calendar", {"pk": self.farm.pk}, "Crop calendar"),
            ("notebook:ledger", {"pk": self.farm.pk}, "Expenses and income"),
            ("notebook:diary", {"pk": self.farm.pk}, "Farm diary"),
            ("notebook:soil", {"pk": self.farm.pk}, "Soil test records"),
        ]
        for route, kwargs, heading in routes:
            with self.subTest(route=route):
                response = self.client.get(reverse(route, kwargs=kwargs), HTTP_ACCEPT_LANGUAGE="en-US")
                self.assert_bangla_page(response, heading)

    def test_new_record_forms_and_validation_are_bangla(self):
        for section, heading in [("calendar", "Add task"), ("ledger", "Add transaction"), ("diary", "Add diary entry"), ("soil", "Add soil test")]:
            with self.subTest(section=section):
                url = reverse("notebook:create", kwargs={"pk": self.farm.pk, "section": section})
                self.assert_bangla_page(self.client.get(url), heading)
                invalid = self.client.post(url, {})
                self.assertEqual(invalid.status_code, 200)
                errors = str(invalid.context["form"].errors)
                self.assertRegex(errors, r"[\u0980-\u09ff]")
                self.assertNotIn("This field is required", errors)

    def test_custom_soil_and_boundary_errors_are_translated(self):
        soil_url = reverse("notebook:create", kwargs={"pk": self.farm.pk, "section": "soil"})
        empty = self.client.post(soil_url, {"tested_on": self.today.isoformat()})
        with translation.override("bn"):
            message = translation.gettext("Enter at least one measured soil result.")
        self.assertNotEqual(message, "Enter at least one measured soil result.")
        self.assertContains(empty, message)
        bad_polygon = self.client.post(reverse("boundaries:editor", args=[self.farm.pk]), {"geometry": '{"type":"Point","coordinates":[88.6,24.3]}'})
        with translation.override("bn"):
            message = translation.gettext("Enter a GeoJSON Polygon with one closed ring.")
        self.assertNotEqual(message, "Enter a GeoJSON Polygon with one closed ring.")
        self.assertContains(bad_polygon, message)

    def test_weather_conditions_and_forecast_labels_use_selected_language(self):
        current_time = timezone.now()
        forecast = {
            "current": {"weather_code": 0, "time": current_time, "temperature_c": 29.5, "humidity_pct": 70, "precipitation_mm": 0, "wind_kmh": 8, "interval_minutes": 15},
            "days": [{"weather_code": 61, "date": self.today + timedelta(days=index), "minimum_c": 23, "maximum_c": 31, "precipitation_mm": 2, "rain_probability": 60, "wind_kmh": 12} for index in range(7)],
            "retrieved_at": current_time,
        }
        weather_url = reverse("weather:dashboard", args=[self.farm.pk])
        with patch("weather.views.get_weather", return_value=forecast):
            bangla = self.client.get(weather_url)
            self.assert_bangla_page(bangla, "Seven-day forecast")
            self.assertContains(bangla, "পরিষ্কার আকাশ")
            self.assertContains(bangla, "হালকা বৃষ্টি")
            self.assertContains(bangla, "২৯.৫")
            self.client.post(reverse("core:language"), {"language": "en", "next": weather_url})
            english = self.client.get(weather_url)
            self.assertContains(english, '<html lang="en">')
            self.assertContains(english, "Clear sky")
            self.assertContains(english, "Seven-day forecast")

    def test_language_switch_preserves_notes_and_numeric_records(self):
        note = DiaryEntry.objects.create(farm=self.farm, date=self.today, title="Farmer's exact title", notes="My observation: Plot B was irrigated.")
        entry = LedgerEntry.objects.create(farm=self.farm, date=self.today, entry_type="expense", title="Seed invoice", amount=Decimal("123.45"))
        soil = SoilTest.objects.create(farm=self.farm, tested_on=self.today, ph=Decimal("6.50"), nitrogen=Decimal("0"))
        ledger_url = reverse("notebook:ledger", args=[self.farm.pk])
        bangla = self.client.get(ledger_url)
        self.assertContains(bangla, "১২৩.৪৫")
        self.assertContains(bangla, "Seed invoice")
        diary = self.client.get(reverse("notebook:diary", args=[self.farm.pk]))
        diary_text = VisibleText()
        diary_text.feed(diary.content.decode("utf-8"))
        self.assertIn(note.title, diary_text.text)
        self.assertContains(diary, note.notes)
        soil_edit_url = reverse("notebook:edit", kwargs={"pk": self.farm.pk, "section": "soil", "entry_id": soil.pk})
        self.assertContains(self.client.get(soil_edit_url), 'value="6.50"')
        self.client.post(reverse("core:language"), {"language": "en", "next": ledger_url})
        english = self.client.get(ledger_url)
        self.assertContains(english, "123.45")
        self.assertEqual(bangla.context["net"], english.context["net"])
        note.refresh_from_db()
        entry.refresh_from_db()
        soil.refresh_from_db()
        self.assertEqual(note.notes, "My observation: Plot B was irrigated.")
        self.assertEqual(entry.amount, Decimal("123.45"))
        self.assertEqual(soil.ph, Decimal("6.50"))
        self.assertEqual(soil.nitrogen, Decimal("0"))

    def test_account_settings_and_password_forms_are_bangla(self):
        owner = get_user_model().objects.create_user(username="language-owner", password="test-password-582")
        self.client.force_login(owner)
        self.assert_bangla_page(self.client.get(reverse("accounts:profile")), "Your account")
        password_url = reverse("accounts:password_change")
        self.assert_bangla_page(self.client.get(password_url), "Change password")
        invalid = self.client.post(password_url, {"old_password": "wrong", "new_password1": "short", "new_password2": "different"})
        self.assertEqual(invalid.status_code, 200)
        self.assertRegex(str(invalid.context["form"].errors), r"[\u0980-\u09ff]")
