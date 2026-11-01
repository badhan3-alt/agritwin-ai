"""Saved work follows its farm through account claiming and offline export."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from boundaries.models import FarmBoundary
from climate.services import NASADataUnavailable
from farms.models import Farm
from notebook.models import CalendarEvent, DiaryEntry, LedgerEntry, SoilTest


class FarmToolsIntegrationTests(TestCase):
    @patch("climate.services.requests.get", side_effect=AssertionError("Saved farm tools must not request NASA"))
    def test_guest_records_follow_claimed_farm_to_second_device(self, network):
        session = self.client.session
        session["language"] = "en"
        session.save()
        farm = Farm.objects.create(owner_session=session.session_key, **Farm.example_defaults())
        task = CalendarEvent.objects.create(farm=farm, title="Irrigate north field", event_type="irrigation", due_date=timezone.localdate() - timedelta(days=1))
        LedgerEntry.objects.create(farm=farm, title="Irrigation cost", entry_type="expense", amount=Decimal("125.25"))
        DiaryEntry.objects.create(farm=farm, title="Field visit", notes="Water reached every corner.")
        SoilTest.objects.create(farm=farm, ph=Decimal("6.25"))
        FarmBoundary.objects.create(farm=farm, geometry={"type": "Polygon", "coordinates": [[[88.60, 24.37], [88.601, 24.37], [88.601, 24.371], [88.60, 24.371], [88.60, 24.37]]]})
        user = User.objects.create_user(username="field-owner", password="Dated-farm-records-38")
        self.assertEqual(self.client.post(reverse("accounts:login"), {"username": user.username, "password": "Dated-farm-records-38"}).status_code, 302)

        second = Client()
        session = second.session
        session["language"] = "en"
        session.save()
        self.assertTrue(second.login(username=user.username, password="Dated-farm-records-38"))
        with patch("farms.views.analysis_context", side_effect=NASADataUnavailable("NASA unavailable")):
            overview = second.get(reverse("farms:detail", args=[farm.pk]))
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.context["records"]["overdue_count"], 1)
        self.assertEqual(overview.context["records"]["finances"]["net"], Decimal("-125.25"))
        for route in ["boundaries:editor", "notebook:calendar", "notebook:ledger", "notebook:diary", "notebook:soil", "weather:dashboard"]:
            self.assertContains(overview, reverse(route, args=[farm.pk]))
        for route in ["boundaries:editor", "notebook:calendar", "notebook:ledger", "notebook:diary", "notebook:soil"]:
            url = reverse(route, args=[farm.pk])
            self.assertEqual(second.get(url).status_code, 200)
            self.assertEqual(Client().get(url).status_code, 404)
        second.post(reverse("notebook:complete", args=[farm.pk, task.pk]), {"completed": "1"})
        task.refresh_from_db()
        self.assertTrue(task.completed)
        pdf_url = reverse("reports:download", args=[farm.pk, "pdf"])
        pdf = second.get(pdf_url)
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF-"))
        self.assertEqual(Client().get(pdf_url).status_code, 404)
        network.assert_not_called()
