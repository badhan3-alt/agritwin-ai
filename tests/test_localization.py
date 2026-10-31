"""Language selection changes presentation without changing scientific data."""
from copy import deepcopy
import csv
from html.parser import HTMLParser
from io import StringIO
import json
from pathlib import Path
import re
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import translation

from climate.services import _parse_power, NASADataUnavailable, UNAVAILABLE_MESSAGE
from core.localization import localize_text, localize_value
from core.templatetags.bangla import bn_number
from farms.forms import FarmForm
from farms.models import Analysis, Farm
from farms.regions import REGIONS
from rotations.services import evaluate_rotations

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden_depth = 0
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if not self.hidden_depth:
            self.text.append(data)

class FarmerLanguageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.network = patch("climate.services.requests.get", side_effect=AssertionError("Localization must use the saved NASA baseline"))
        self.network.start()
        self.addCleanup(self.network.stop)
        session = self.client.session
        session.save()
        self.farm = Farm.objects.create(owner_session=session.session_key, **Farm.example_defaults())
        self.raw = json.loads((Path(__file__).parent / "fixtures" / "nasa_power_climatology.json").read_text(encoding="utf-8"))
        climate = _parse_power(self.raw, self.farm.latitude, self.farm.longitude, "https://power.larc.nasa.gov/api/temporal/climatology/point?latitude=24.3745&longitude=88.6042")
        self.analysis = Analysis.objects.create(farm=self.farm, climate=climate, strategies=evaluate_rotations(self.farm.to_profile(), climate))

    def test_bangla_is_default_even_when_browser_prefers_english(self):
        response = self.client.get(reverse("core:home"), HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
        self.assertEqual(response["Content-Language"], "bn")
        self.assertContains(response, '<html lang="bn">')
        self.assertContains(response, "সারসংক্ষেপ")
        self.assertContains(response, "এগ্রিটুইন")

    def test_all_farmer_pages_are_predominantly_bangla(self):
        routes = ["core:home", "core:about", "farms:create", "farms:detail", "climate:dashboard", "rotations:explorer", "simulator:workbench", "reports:detail"]
        for route in routes:
            with self.subTest(route=route):
                kwargs = {} if route.startswith("core:") or route == "farms:create" else {"pk": self.farm.pk}
                response = self.client.get(reverse(route, kwargs=kwargs))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<html lang="bn">')
                parser = VisibleText()
                parser.feed(response.content.decode("utf-8"))
                text = " ".join(parser.text)
                bengali = len(re.findall(r"[\u0980-\u09ff]", text))
                english = len(re.findall(r"[A-Za-z]", text))
                self.assertGreater(bengali / max(1, bengali + english), .75)
                self.assertNotIn("Your current rotation", text)
                self.assertNotIn("Drier", text)
                leftovers = [part.strip() for part in parser.text
                    if re.search(r"[A-Za-z]{3,}", part)
                    and not re.search(r"[\u0980-\u09ff]", part)
                    and part.strip() != "English" and "https://" not in part]
                self.assertEqual(leftovers, [])

    def test_language_toggle_changes_whole_pages_and_remembers_choice(self):
        self.client.post(reverse("core:language"), {"language": "en", "next": reverse("farms:create")})
        response = self.client.get(reverse("farms:create"))
        self.assertEqual(response["Content-Language"], "en")
        self.assertContains(response, "Farm name")
        self.assertContains(response, "Choose a district or set coordinates")
        self.client.post(reverse("core:language"), {"language": "bn", "next": reverse("farms:create")})
        response = self.client.get(reverse("farms:create"))
        self.assertEqual(response["Content-Language"], "bn")
        self.assertContains(response, "খামারের নাম")
        self.assertContains(response, "জেলা বেছে নিন")
        self.assertNotContains(response, "Farm name")
        self.assertContains(self.client.get(reverse("core:about")), '<html lang="bn">')

    def test_district_crop_and_validation_labels_are_bangla(self):
        with translation.override("bn"):
            form = FarmForm()
            rendered = str(form["region"])
            for district in REGIONS:
                self.assertIn(district["district_bn"], rendered)
            self.assertIn("রোপা আমন ধান", str(form["current_crops"]))
            self.assertIn("সীমিত", str(form["irrigation_availability"]))
            self.assertEqual(str(form.fields["name"].label), "খামারের নাম")
            self.assertEqual(str(form.fields["soil_ph"].widget.attrs["placeholder"]), "জানা না থাকলে খালি রাখুন")
            invalid = FarmForm(data={})
            self.assertFalse(invalid.is_valid())
            self.assertRegex(str(invalid.errors["name"]), r"[\u0980-\u09ff]")
            self.assertNotIn("This field is required", str(invalid.errors["name"]))

    def test_translated_advice_does_not_rewrite_nasa_or_scores(self):
        original = deepcopy(self.analysis.strategies)
        with translation.override("bn"):
            displayed = localize_value(original)
            self.assertEqual(localize_text("Rajshahi example farm"), "রাজশাহীর নমুনা খামার")
            self.assertEqual(localize_text("My north field"), "My north field")
            self.assertEqual(localize_text("Your current rotation"), "আপনার বর্তমান ফসলের পর্যায়ক্রম")
            for before, after in zip(original, displayed):
                self.assertEqual(before["composite_score"], after["composite_score"])
                self.assertEqual(before["components"], after["components"])
                self.assertEqual(before["id"], after["id"])
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.strategies, original)
        raw = self.client.get(reverse("climate:nasa_source", kwargs={"pk": self.farm.pk})).json()
        self.assertEqual(raw, self.raw)

    def test_bangla_reports_and_original_nasa_download(self):
        response = self.client.get(reverse("reports:download", kwargs={"pk": self.farm.pk, "format": "csv"}))
        text = response.content.decode("utf-8-sig")
        self.assertIn("খামারের প্রতিবেদন", text)
        self.assertIn("মাটির অম্লত্ব", text)
        self.assertIn("বোরো ধান", text)
        self.assertNotIn("Your current rotation", text)
        json_report = self.client.get(reverse("reports:download", kwargs={"pk": self.farm.pk, "format": "json"})).json()
        self.assertEqual(json_report["language"], "bn")
        self.assertEqual(json_report["climate"]["raw_response"], self.raw)
        self.assertIn("display_strategies", json_report)

    def test_bangla_scenario_controls_and_results(self):
        response = self.client.post(reverse("simulator:workbench", kwargs={"pk": self.farm.pk}), {"rainfall_delta_pct": "-20", "temp_delta_c": "2", "irrigation": "limited", "priority": "water_conservation"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "বৃষ্টিপাতের পরিবর্তন")
        self.assertNotContains(response, "score points:")
        self.assertNotContains(response, "Drier")
        self.assertEqual(response.context["result"]["parameters"]["rainfall_delta_pct"], -20)
        self.assertContains(response, 'value="-20"')

    def test_bangla_outage_and_security_messages(self):
        self.analysis.delete()
        with patch("climate.services.get_climate", side_effect=NASADataUnavailable(UNAVAILABLE_MESSAGE)):
            response = self.client.get(reverse("climate:dashboard", kwargs={"pk": self.farm.pk}))
        self.assertEqual(response.status_code, 503)
        self.assertContains(response, "নাসা", status_code=503)
        self.assertNotContains(response, "No sample data has been substituted", status_code=503)
        denied = Client(enforce_csrf_checks=True).post(reverse("farms:create"), {})
        self.assertEqual(denied.status_code, 403)
        self.assertContains(denied, '<html lang="bn">', status_code=403)

    def test_bangla_display_digits_do_not_change_numbers(self):
        with translation.override("bn"):
            self.assertEqual(bn_number("24.3745"), "২৪.৩৭৪৫")
        with translation.override("en"):
            self.assertEqual(bn_number("24.3745"), "24.3745")
        response = self.client.get(reverse("farms:edit", kwargs={"pk": self.farm.pk}))
        self.assertContains(response, 'value="24.3745"')
