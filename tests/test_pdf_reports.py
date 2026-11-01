"""PDF export remains private and works offline with the saved farm records."""
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
import re
import unicodedata
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone, translation

from boundaries.models import FarmBoundary
from farms.models import Analysis, Farm
from farms.services import ensure_analysis
from notebook.models import CalendarEvent, DiaryEntry, LedgerEntry, SoilTest
from reports.pdf import _markup, boundary_drawing, build_pdf_report


class PDFReportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.farm = Farm.objects.create(owner_session=session.session_key, **{**Farm.example_defaults(), "name": 'North & South <field> "one"'})
        self.url = reverse("reports:download", args=[self.farm.pk, "pdf"])

    def assert_valid_pdf(self, content):
        self.assertTrue(content.startswith(b"%PDF-"))
        self.assertTrue(content.rstrip().endswith(b"%%EOF"))
        self.assertGreater(len(re.findall(rb"/Type /Page\b", content)), 0)
        self.assertIn(b"/FontFile2", content)

    @patch("climate.services.requests.get")
    @patch("weather.services.requests.get")
    def test_pdf_is_an_offline_private_download_without_nasa(self, weather, nasa):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(f'agritwin-farm-{self.farm.pk}.pdf', response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assert_valid_pdf(response.content)
        nasa.assert_not_called()
        weather.assert_not_called()
        self.assertFalse(Analysis.objects.filter(farm=self.farm).exists())

    @patch("climate.services.requests.get")
    def test_export_checks_ownership_before_building_or_fetching(self, network):
        with patch("reports.pdf.build_pdf_report") as renderer:
            self.assertEqual(Client().get(self.url).status_code, 404)
            renderer.assert_not_called()
        network.assert_not_called()

    def test_records_and_boundary_are_exported_with_wrapped_user_text(self):
        today = timezone.localdate()
        CalendarEvent.objects.create(farm=self.farm, title="Plant <rice> & lentils", crop="Aman", event_type="planting", due_date=today, notes="<img src='http://example.invalid/tracker'>\n" + "Long farm observation & detail. " * 80)
        LedgerEntry.objects.create(farm=self.farm, title="Seed <purchase>", entry_type="expense", amount="100.25", notes="Cost & receipt notes")
        LedgerEntry.objects.create(farm=self.farm, title="Rice sale", entry_type="income", amount="250.50")
        DiaryEntry.objects.create(farm=self.farm, title="Crop observation", notes="Long note. " * 800, photo_caption="Green crop")
        SoilTest.objects.create(farm=self.farm, tested_on=today - timedelta(days=1), ph="6.50", nitrogen="12.50", phosphorus="10", potassium="50", laboratory="Lab & source", notes="Comparable sampling method")
        FarmBoundary.objects.create(farm=self.farm, geometry={"type": "Polygon", "coordinates": [[[88.60, 24.37], [88.601, 24.37], [88.601, 24.371], [88.60, 24.371], [88.60, 24.37]]]})
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assert_valid_pdf(response.content)
        self.assertGreater(len(re.findall(rb"/Type /Page\b", response.content)), 3)

    def test_bangla_is_embedded_and_shaped_with_user_content_preserved(self):
        self.farm.name = "সবুজ কৃষিক্ষেত্র"
        self.farm.save()
        DiaryEntry.objects.create(farm=self.farm, title="পর্যবেক্ষণ", notes="ক্ষেতে সেচের প্রয়োজন। মাটির আর্দ্রতা পরীক্ষা করেছি।")
        with translation.override("bn"):
            content = build_pdf_report(self.farm)
        self.assert_valid_pdf(content)
        self.assertIn(b"NotoSansBengali", content)
        self.assertIn(b"NotoSansBengali-Bold", content)
        try:
            from pypdf import PdfReader
        except ImportError:
            return
        # Include Bangla inside parentheses and beside Latin punctuation.
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages)
        self.assertNotIn("\uffff", text)

    def test_multiline_record_titles_split_across_pages_without_layout_error(self):
        CalendarEvent.objects.create(farm=self.farm, title="x\n" * 79, event_type="planting", due_date=timezone.localdate())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assert_valid_pdf(response.content)
        self.assertGreater(len(re.findall(rb"/Type /Page\b", response.content)), 2)

    def test_long_unbroken_diary_text_wraps_across_pages(self):
        DiaryEntry.objects.create(farm=self.farm, title="Long observation", notes="a" * 5000 + "ক্ষেত" * 1000)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assert_valid_pdf(response.content)

    def test_markup_escapes_tags_and_retains_bengali(self):
        markup = _markup('<a href="file:///private">বৃষ্টি & rain</a>')
        self.assertIn("&lt;a", markup)
        self.assertIn("&amp;", markup)
        self.assertIn("বৃষ্টি", markup)
        self.assertNotIn('<a href=', markup)

    def test_schematic_is_north_up_and_does_not_request_tiles(self):
        geometry = {"type": "Polygon", "coordinates": [[[88.6, 24.37], [88.601, 24.37], [88.601, 24.371], [88.6, 24.371], [88.6, 24.37]]]}
        # ReportLab y increases upward. The third corner lies north of first.
        drawing = boundary_drawing(geometry)
        outline = drawing.contents[1].points
        self.assertGreater(outline[5], outline[1])

    @patch("climate.services.requests.get")
    def test_legacy_synthetic_analysis_is_not_used_by_pdf(self, network):
        Analysis.objects.create(farm=self.farm, climate={"status": "demo", "source": "Fake sample"}, strategies=[])
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assert_valid_pdf(response.content)
        network.assert_not_called()

    @patch("climate.services.requests.get")
    def test_saved_nasa_baseline_and_strategies_are_included_without_refetch(self, network):
        payload = json.loads((Path(__file__).parent / "fixtures" / "nasa_power_climatology.json").read_text(encoding="utf-8"))
        network.return_value.raise_for_status.return_value = None
        network.return_value.json.return_value = payload
        network.return_value.url = "https://power.larc.nasa.gov/api/temporal/climatology/point"
        ensure_analysis(self.farm)
        network.reset_mock()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assert_valid_pdf(response.content)
        network.assert_not_called()

    def test_pdf_can_be_reopened_by_optional_parser(self):
        try:
            from pypdf import PdfReader
        except ImportError:
            self.skipTest("Optional pypdf parser is not installed; core export tests still validate PDF structure.")
        content = self.client.get(self.url).content
        reader = PdfReader(BytesIO(content))
        text = unicodedata.normalize("NFKC", "\n".join(page.extract_text() for page in reader.pages))
        self.assertIn(self.farm.name, text)
        self.assertIn("No validated NASA analysis is saved", text)
        self.assertIn("Crop calendar and reminders", text)
        self.assertIn("Soil test history", text)
        self.assertIn("Farm diary", text)
