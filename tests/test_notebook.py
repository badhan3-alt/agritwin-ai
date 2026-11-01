import io
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from farms.models import Farm
from notebook.forms import DiaryEntryForm, SoilTestForm
from notebook.models import CalendarEvent, DiaryEntry, LedgerEntry, SoilTest
from notebook.services import farm_record_summary, ledger_totals, soil_comparison


class FarmNotebookTests(TestCase):
    def setUp(self):
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.farm = Farm.objects.create(owner_session=session.session_key, **Farm.example_defaults())
        self.other_farm = Farm.objects.create(owner_session="another-browser", **Farm.example_defaults())
        self.today = timezone.localdate()
        self.media_dir = TemporaryDirectory()
        self.addCleanup(self.media_dir.cleanup)
        self.media_settings = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)

    def url(self, name, section=None, entry=None, farm=None):
        kwargs = {"pk": (farm or self.farm).pk}
        if section:
            kwargs["section"] = section
        if entry:
            kwargs["entry_id"] = entry.pk
        return reverse(f"notebook:{name}", kwargs=kwargs)

    def photo(self, name="field.jpg", extra=b""):
        data = io.BytesIO()
        Image.new("RGB", (20, 20), color="green").save(data, format="JPEG")
        return SimpleUploadedFile(name, data.getvalue() + extra, content_type="image/jpeg")

    def test_empty_workspaces_and_forms_work_without_nasa(self):
        for section in ["calendar", "ledger", "diary", "soil"]:
            response = self.client.get(self.url(section))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["farm"], self.farm)
            self.assertContains(response, self.url("create", section))
            form = self.client.get(self.url("create", section))
            self.assertEqual(form.status_code, 200)
            self.assertContains(form, 'type="date"')
            self.assertContains(form, 'data-loading-form')

    def test_crud_for_all_four_sections(self):
        cases = [
            ("calendar", CalendarEvent, {"title": "Plant rice", "event_type": "planting", "due_date": self.today.isoformat(), "reminder_days": "2"}),
            ("ledger", LedgerEntry, {"date": self.today.isoformat(), "entry_type": "expense", "title": "Buy seed", "amount": "123.45"}),
            ("diary", DiaryEntry, {"date": self.today.isoformat(), "title": "Field visit", "notes": "Leaves look healthy."}),
            ("soil", SoilTest, {"tested_on": self.today.isoformat(), "ph": "6.20"}),
        ]
        for section, model, data in cases:
            with self.subTest(section=section):
                created = self.client.post(self.url("create", section), data)
                self.assertRedirects(created, self.url(section))
                entry = model.objects.get(farm=self.farm)
                edited_data = {**data, "notes": "Updated observation"}
                if section == "soil":
                    edited_data["ph"] = "6.50"
                updated = self.client.post(self.url("edit", section, entry), edited_data)
                self.assertRedirects(updated, self.url(section))
                entry.refresh_from_db()
                self.assertEqual(entry.notes, "Updated observation")
                delete_url = self.url("delete", section, entry)
                self.assertEqual(self.client.get(delete_url).status_code, 405)
                self.assertRedirects(self.client.post(delete_url), self.url(section))
                self.assertFalse(model.objects.filter(pk=entry.pk).exists())

    def test_reminders_follow_each_task_window_and_completed_state(self):
        overdue = CalendarEvent.objects.create(farm=self.farm, title="Late irrigation", event_type="irrigation", due_date=self.today - timedelta(days=1))
        today = CalendarEvent.objects.create(farm=self.farm, title="Plant today", event_type="planting", due_date=self.today)
        soon = CalendarEvent.objects.create(farm=self.farm, title="Harvest soon", event_type="harvest", due_date=self.today + timedelta(days=3), reminder_days=4)
        CalendarEvent.objects.create(farm=self.farm, title="Later", event_type="other", due_date=self.today + timedelta(days=10), reminder_days=1)
        CalendarEvent.objects.create(farm=self.farm, title="Done", event_type="other", due_date=self.today, completed=True)
        response = self.client.get(self.url("calendar"))
        self.assertEqual(response.context["overdue_count"], 1)
        self.assertEqual(response.context["today_count"], 1)
        self.assertEqual({event.pk for event in response.context["reminders"]}, {overdue.pk, today.pk, soon.pk})
        self.assertEqual(self.client.get(self.url("complete", entry=overdue)).status_code, 405)
        for _ in range(2):
            self.client.post(self.url("complete", entry=overdue), {"completed": "1"})
        overdue.refresh_from_db()
        self.assertTrue(overdue.completed)
        self.assertFalse(overdue.reminder_due)
        self.client.post(self.url("complete", entry=overdue), {"completed": "0"})
        overdue.refresh_from_db()
        self.assertFalse(overdue.completed)

    def test_reminder_days_and_missing_task_fields_are_validated(self):
        response = self.client.post(self.url("create", "calendar"), {"title": "Water", "event_type": "irrigation", "due_date": self.today, "reminder_days": "31"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("reminder_days", response.context["form"].errors)
        self.assertFalse(CalendarEvent.objects.exists())

    def test_finances_use_exact_decimals_and_are_scoped_to_farm(self):
        LedgerEntry.objects.create(farm=self.farm, title="Seed", date=self.today, entry_type="expense", amount=Decimal("10.10"))
        LedgerEntry.objects.create(farm=self.farm, title="Labor", date=self.today, entry_type="expense", amount=Decimal("2.20"))
        LedgerEntry.objects.create(farm=self.farm, title="Sales", date=self.today, entry_type="income", amount=Decimal("20.50"))
        LedgerEntry.objects.create(farm=self.other_farm, title="Private sale", date=self.today, entry_type="income", amount=Decimal("999.99"))
        self.assertEqual(ledger_totals(self.farm), {"income": Decimal("20.50"), "expenses": Decimal("12.30"), "net": Decimal("8.20")})
        response = self.client.get(self.url("ledger"))
        self.assertEqual(response.context["net"], Decimal("8.20"))
        self.assertNotContains(response, "Private sale")
        for amount in ["-1", "0", "NaN", "1.234"]:
            invalid = self.client.post(self.url("create", "ledger"), {"date": self.today, "entry_type": "income", "title": "Invalid", "amount": amount})
            self.assertIn("amount", invalid.context["form"].errors)

    def test_soil_unknown_zero_and_ranges_are_distinct(self):
        blank = SoilTestForm(data={"tested_on": self.today.isoformat()})
        self.assertFalse(blank.is_valid())
        measured = SoilTestForm(data={"tested_on": self.today.isoformat(), "nitrogen": "0"})
        self.assertTrue(measured.is_valid(), measured.errors)
        self.assertEqual(measured.cleaned_data["nitrogen"], Decimal("0"))
        self.assertIsNone(measured.cleaned_data["ph"])
        invalid = SoilTestForm(data={"tested_on": (self.today + timedelta(days=1)).isoformat(), "ph": "15", "potassium": "-1"})
        self.assertFalse(invalid.is_valid())
        self.assertIn("ph", invalid.errors)
        self.assertIn("potassium", invalid.errors)
        self.assertIn("tested_on", invalid.errors)

    def test_soil_changes_compare_latest_non_missing_results(self):
        first = SoilTest.objects.create(farm=self.farm, tested_on=self.today - timedelta(days=20), ph=Decimal("6.00"), nitrogen=Decimal("5"))
        second = SoilTest.objects.create(farm=self.farm, tested_on=self.today - timedelta(days=10), nitrogen=Decimal("8"))
        latest = SoilTest.objects.create(farm=self.farm, tested_on=self.today, ph=Decimal("6.50"))
        comparison = soil_comparison(self.farm.soil_tests.all())
        self.assertEqual(comparison[0]["change"], Decimal("0.50"))
        self.assertEqual(comparison[0]["previous_date"], first.tested_on)
        self.assertEqual(comparison[1]["change"], Decimal("3"))
        self.assertEqual(comparison[1]["latest_date"], second.tested_on)
        self.assertIsNone(comparison[2]["latest"])
        self.assertEqual(self.client.get(self.url("soil")).context["comparisons"][0]["latest_date"], latest.tested_on)

    def test_photos_are_reencoded_and_only_streamed_to_owner(self):
        response = self.client.post(self.url("create", "diary"), {"date": self.today, "title": "Photo", "notes": "A field", "photo": self.photo(extra=b"SECRET_APPENDED_PAYLOAD"), "photo_caption": "Rice leaves"})
        self.assertRedirects(response, self.url("diary"))
        entry = DiaryEntry.objects.get()
        self.assertTrue(entry.photo.name.endswith(".png"))
        self.assertNotIn(b"SECRET_APPENDED_PAYLOAD", entry.photo.read())
        entry.photo.close()
        photo_url = self.url("photo", entry=entry)
        streamed = self.client.get(photo_url)
        self.assertEqual(streamed.status_code, 200)
        self.assertEqual(streamed["Content-Type"], "image/png")
        self.assertEqual(streamed["Cache-Control"], "private, no-store")
        self.assertTrue(b"".join(streamed.streaming_content).startswith(b"\x89PNG"))
        self.assertEqual(Client().get(photo_url).status_code, 404)
        edit_page = self.client.get(self.url("edit", "diary", entry))
        self.assertNotContains(edit_page, entry.photo.url)
        self.assertContains(edit_page, photo_url)
        with self.captureOnCommitCallbacks(execute=True):
            cleared = self.client.post(self.url("edit", "diary", entry), {"date": self.today, "title": "Photo", "notes": "Saved note", "remove_photo": "on"})
        self.assertRedirects(cleared, self.url("diary"))
        entry.refresh_from_db()
        self.assertFalse(entry.photo)
        self.assertEqual(self.client.get(photo_url).status_code, 404)
        self.assertFalse(list(Path(self.media_dir.name).rglob("*.png")))

    def test_invalid_photos_are_rejected_and_text_is_preserved(self):
        response = self.client.post(self.url("create", "diary"), {"date": self.today, "title": "Keep this note", "notes": "My observation", "photo": SimpleUploadedFile("bad.jpg", b"not an image", content_type="image/jpeg")})
        self.assertEqual(response.status_code, 200)
        self.assertIn("photo", response.context["form"].errors)
        self.assertContains(response, "Keep this note")
        self.assertFalse(DiaryEntry.objects.exists())

    def test_valid_photo_with_invalid_new_entry_keeps_validation_page_usable(self):
        response = self.client.post(self.url("create", "diary"), {"date": self.today, "title": "", "notes": "Keep this observation", "photo": self.photo()})
        self.assertEqual(response.status_code, 200)
        self.assertIn("title", response.context["form"].errors)
        self.assertContains(response, "Keep this observation")
        self.assertNotContains(response, '<figure class="diary-photo">')
        self.assertFalse(DiaryEntry.objects.exists())
        self.assertFalse(list(Path(self.media_dir.name).rglob("*.png")))

    def test_invalid_photo_replacement_previews_only_the_persisted_photo(self):
        self.client.post(self.url("create", "diary"), {"date": self.today, "title": "Saved title", "notes": "Saved note", "photo": self.photo(), "photo_caption": "Original leaves"})
        entry = DiaryEntry.objects.get()
        original_name = entry.photo.name
        original_bytes = entry.photo.read()
        entry.photo.close()
        replacement = self.client.post(self.url("edit", "diary", entry), {"date": self.today, "title": "", "notes": "Unsaved note", "photo": self.photo(), "photo_caption": "Unsaved caption"})
        self.assertEqual(replacement.status_code, 200)
        self.assertIn("title", replacement.context["form"].errors)
        self.assertContains(replacement, f'src="{self.url("photo", entry=entry)}"')
        self.assertContains(replacement, 'alt="Original leaves"')
        entry.refresh_from_db()
        self.assertEqual(entry.photo.name, original_name)
        self.assertEqual(entry.notes, "Saved note")
        streamed = self.client.get(self.url("photo", entry=entry))
        self.assertEqual(b"".join(streamed.streaming_content), original_bytes)
        self.assertEqual(len(list(Path(self.media_dir.name).rglob("*.png"))), 1)
        no_photo = DiaryEntry.objects.create(farm=self.farm, title="Note only", notes="Saved without a photo")
        invalid_addition = self.client.post(self.url("edit", "diary", no_photo), {"date": self.today, "title": "", "notes": "Unsaved photo", "photo": self.photo()})
        self.assertEqual(invalid_addition.status_code, 200)
        self.assertNotContains(invalid_addition, '<figure class="diary-photo">')

    def test_phone_photo_orientation_is_applied_before_metadata_is_removed(self):
        data = io.BytesIO()
        image = Image.new("RGB", (30, 10), color="green")
        exif = Image.Exif()
        exif[274] = 6  # The phone asks viewers to rotate the stored pixels 90°.
        image.save(data, format="JPEG", exif=exif)
        response = self.client.post(self.url("create", "diary"), {"date": self.today, "title": "Phone photo", "notes": "An upright field", "photo": SimpleUploadedFile("phone.jpg", data.getvalue(), content_type="image/jpeg")})
        self.assertRedirects(response, self.url("diary"))
        entry = DiaryEntry.objects.get()
        with entry.photo.open("rb") as photo:
            with Image.open(photo) as saved:
                self.assertEqual(saved.size, (10, 30))
                self.assertFalse(saved.getexif())

    def test_photo_cleanup_on_farm_deletion(self):
        self.client.post(self.url("create", "diary"), {"date": self.today, "title": "Photo", "notes": "A field", "photo": self.photo()})
        self.assertEqual(len(list(Path(self.media_dir.name).rglob("*.png"))), 1)
        with self.captureOnCommitCallbacks(execute=True):
            self.farm.delete()
        self.assertFalse(DiaryEntry.objects.exists())
        self.assertFalse(list(Path(self.media_dir.name).rglob("*.png")))

    def test_cross_farm_record_ids_cannot_be_read_or_modified(self):
        records = [
            ("calendar", CalendarEvent.objects.create(farm=self.other_farm, title="Private task", event_type="other", due_date=self.today)),
            ("ledger", LedgerEntry.objects.create(farm=self.other_farm, title="Private sale", entry_type="income", amount=10)),
            ("diary", DiaryEntry.objects.create(farm=self.other_farm, title="Private note", notes="Hidden")),
            ("soil", SoilTest.objects.create(farm=self.other_farm, tested_on=self.today, ph=6)),
        ]
        for section, entry in records:
            for method, name in [("get", "edit"), ("post", "edit"), ("post", "delete")]:
                with self.subTest(section=section, method=method, name=name):
                    self.assertEqual(getattr(self.client, method)(self.url(name, section, entry)).status_code, 404)
            self.assertEqual(Client().get(self.url(section)).status_code, 404)
        self.assertEqual(self.client.post(self.url("complete", entry=records[0][1]), {"completed": "1"}).status_code, 404)

    def test_csrf_required_for_record_writes(self):
        protected = Client(enforce_csrf_checks=True)
        protected.cookies = self.client.cookies
        self.assertEqual(protected.post(self.url("create", "ledger"), {"title": "Sale", "entry_type": "income", "date": self.today, "amount": "10"}).status_code, 403)
        self.assertFalse(LedgerEntry.objects.exists())

    def test_account_owner_can_access_records_from_another_browser(self):
        owner = get_user_model().objects.create_user(username="record-owner", password="test-password-491")
        self.farm.owner = owner
        self.farm.save(update_fields=["owner"])
        DiaryEntry.objects.create(farm=self.farm, title="Across devices", notes="Shared account record")
        second_device = Client()
        second_device.force_login(owner)
        self.assertContains(second_device.get(self.url("diary")), "Across devices")
        self.assertEqual(self.client.get(self.url("diary")).status_code, 404)

    def test_dashboard_summary_uses_only_farm_records(self):
        CalendarEvent.objects.create(farm=self.farm, title="Late", event_type="other", due_date=self.today - timedelta(days=1))
        DiaryEntry.objects.create(farm=self.other_farm, title="Other", notes="Other farm")
        summary = farm_record_summary(self.farm)
        self.assertEqual(summary["overdue_count"], 1)
        self.assertEqual(summary["diary_count"], 0)
        self.assertEqual(summary["finances"]["net"], Decimal("0"))
