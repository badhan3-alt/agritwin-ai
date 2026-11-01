"""Server-side access boundaries across every private farm tool.

Only synthetic users, photos and recorded NASA evidence are used. No live
credentials, outbound calls or public media serving are needed by these tests.
"""
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from boundaries.models import FarmBoundary
from chatbot.models import Conversation, Message
from climate.services import NASADataUnavailable, _parse_power
from farms.models import Analysis, Farm
from notebook.models import CalendarEvent, DiaryEntry, LedgerEntry, SoilTest
from rotations.services import evaluate_rotations


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FarmSecurityAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(username="private-owner", password="SyntheticTest!2026")
        cls.other_user = get_user_model().objects.create_user(username="another-account", password="SyntheticTest!2026")

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.media_settings = override_settings(MEDIA_ROOT=self.media.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.network = patch("requests.sessions.Session.request", side_effect=AssertionError("Security tests must not reach any external provider"))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.client.force_login(self.owner)
        self.other = Client()
        self.other.force_login(self.other_user)
        self.anonymous = Client()
        # A session alone is useful for guest farms, but must never unlock an
        # account-owned farm even if legacy owner_session values happen to match.
        anonymous_session = self.anonymous.session
        anonymous_session.save()
        self.farm = Farm.objects.create(owner=self.owner, owner_session=anonymous_session.session_key, **{**Farm.example_defaults(), "name": "Owner-only secret field"})
        self.other_farm = Farm.objects.create(owner=self.other_user, owner_session="", **{**Farm.example_defaults(), "name": "Other account field"})
        self.today = timezone.localdate()
        self.event = CalendarEvent.objects.create(farm=self.farm, title="Private calendar task", event_type="irrigation", due_date=self.today)
        self.transaction = LedgerEntry.objects.create(farm=self.farm, entry_type="income", title="Private sales", amount="12.50")
        self.soil = SoilTest.objects.create(farm=self.farm, tested_on=self.today, ph="6.50")
        image = BytesIO()
        Image.new("RGB", (2, 2), color="green").save(image, format="PNG")
        self.diary = DiaryEntry.objects.create(farm=self.farm, title="Private observation", notes="Private diary text", photo=SimpleUploadedFile("synthetic.png", image.getvalue(), content_type="image/png"))
        self.boundary = FarmBoundary.objects.create(farm=self.farm, geometry={"type": "Polygon", "coordinates": [[[89, 24], [89.001, 24], [89.001, 24.001], [89, 24.001], [89, 24]]]})
        self.conversation = Conversation.objects.create(owner_session=self.client.session.session_key, title="Private conversation", farm=self.farm)
        Message.objects.create(conversation=self.conversation, role="user", body="Private question")
        raw = json.loads((Path(__file__).parent / "fixtures" / "nasa_power_climatology.json").read_text(encoding="utf-8"))
        climate = _parse_power(raw, self.farm.latitude, self.farm.longitude, "https://power.larc.nasa.gov/api/temporal/climatology/point")
        self.analysis = Analysis.objects.create(farm=self.farm, climate=climate, strategies=evaluate_rotations(self.farm.to_profile(), climate))

    def farm_url(self, route, *extra, farm=None):
        return reverse(route, args=[(farm or self.farm).pk, *extra])

    def record_url(self, route, section=None, entry=None, farm=None):
        kwargs = {"pk": (farm or self.farm).pk}
        if section:
            kwargs["section"] = section
        if entry:
            kwargs["entry_id"] = entry.pk
        return reverse(f"notebook:{route}", kwargs=kwargs)

    def private_get_urls(self):
        routes = ["farms:detail", "farms:edit", "boundaries:editor", "boundaries:download", "climate:dashboard", "climate:nasa_source", "rotations:explorer", "simulator:workbench", "reports:detail", "weather:dashboard", "notebook:calendar", "notebook:ledger", "notebook:diary", "notebook:soil"]
        urls = [self.farm_url(route) for route in routes]
        urls.extend(self.farm_url("reports:download", output) for output in ["json", "csv", "pdf"])
        for section, entry in [("calendar", self.event), ("ledger", self.transaction), ("diary", self.diary), ("soil", self.soil)]:
            urls.extend([self.record_url("create", section), self.record_url("edit", section, entry)])
        return urls + [self.record_url("photo", entry=self.diary), reverse("chatbot:index") + f"?farm={self.farm.pk}"]

    def test_anonymous_and_other_accounts_cannot_read_any_private_tool_or_export(self):
        for browser in [self.anonymous, self.other]:
            for url in self.private_get_urls():
                with self.subTest(authenticated=browser is self.other, route=url):
                    response = browser.get(url)
                    self.assertEqual(response.status_code, 404)
                    self.assertNotContains(response, self.farm.name, status_code=404)

    def test_foreign_posts_cannot_modify_delete_or_refresh_private_farm_data(self):
        urls = [self.farm_url(route) for route in ["farms:edit", "farms:delete", "boundaries:editor", "boundaries:delete", "climate:refresh", "weather:refresh", "simulator:workbench"]]
        for section, entry in [("calendar", self.event), ("ledger", self.transaction), ("diary", self.diary), ("soil", self.soil)]:
            urls.extend([self.record_url("create", section), self.record_url("edit", section, entry), self.record_url("delete", section, entry)])
        urls.append(self.record_url("complete", entry=self.event))
        for browser in [self.anonymous, self.other]:
            for url in urls:
                with self.subTest(authenticated=browser is self.other, route=url):
                    response = browser.post(url, {"owner": self.other_user.pk, "owner_id": self.other_user.pk, "owner_session": browser.session.session_key, "completed": "1"})
                    self.assertEqual(response.status_code, 404)
        self.farm.refresh_from_db()
        self.event.refresh_from_db()
        self.assertEqual(self.farm.owner, self.owner)
        self.assertFalse(self.event.completed)
        for model, record in [(FarmBoundary, self.boundary), (CalendarEvent, self.event), (LedgerEntry, self.transaction), (DiaryEntry, self.diary), (SoilTest, self.soil), (Analysis, self.analysis)]:
            self.assertTrue(model.objects.filter(pk=record.pk).exists())

    def test_owned_parent_route_does_not_allow_cross_farm_child_ids(self):
        for section, entry in [("calendar", self.event), ("ledger", self.transaction), ("diary", self.diary), ("soil", self.soil)]:
            for route in ["edit", "delete"]:
                url = self.record_url(route, section, entry, farm=self.other_farm)
                with self.subTest(section=section, route=route):
                    response = self.other.post(url, {"title": "Forged edit"})
                    self.assertEqual(response.status_code, 404)
        self.assertEqual(self.other.get(self.record_url("photo", entry=self.diary, farm=self.other_farm)).status_code, 404)
        self.assertEqual(self.other.post(self.record_url("complete", entry=self.event, farm=self.other_farm), {"completed": "1"}).status_code, 404)

    def test_client_supplied_privileged_headers_and_owner_query_fields_are_not_authentication(self):
        url = self.farm_url("farms:edit")
        for browser in [self.anonymous, self.other]:
            response = browser.get(url, {"owner": self.owner.pk, "owner_id": self.owner.pk, "owner_session": self.farm.owner_session, "is_staff": "true", "admin_secret": "synthetic-not-a-real-secret"}, HTTP_AUTHORIZATION="Bearer synthetic-not-a-service-role", HTTP_X_ADMIN_SECRET="synthetic-not-a-real-secret")
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.anonymous.get(self.farm_url("boundaries:download")).status_code, 404)

    @patch("farms.views.ensure_analysis", side_effect=NASADataUnavailable("Provider unavailable during test"))
    def test_farm_form_ignores_posted_owner_session_and_account_ownership(self, unavailable):
        data = {"name": "Injected owner test", "location_name": "Rajshahi, Bangladesh", "latitude": "24.3745", "longitude": "88.6042", "farm_size_acres": "3", "current_crops": ["aman_rice"], "soil_type": "unknown", "drainage": "unknown", "irrigation_availability": "limited", "farming_priority": "water_conservation", "budget": "medium", "owner": self.owner.pk, "owner_id": self.owner.pk, "owner_session": self.farm.owner_session, "is_staff": "true"}
        response = self.other.post(reverse("farms:create"), data)
        self.assertEqual(response.status_code, 302)
        created = Farm.objects.get(name="Injected owner test")
        self.assertEqual(created.owner, self.other_user)
        self.assertEqual(created.owner_session, "")
        self.assertEqual(self.client.get(self.farm_url("farms:edit", farm=created)).status_code, 404)

    def test_chat_rejects_foreign_farm_context_and_conversation_ids_before_answering(self):
        for browser in [self.anonymous, self.other]:
            with patch("chatbot.views.answer_question") as answer:
                response = browser.post(reverse("chatbot:send"), {"message": "Read private soil results", "farm": self.farm.pk, "include_farm": "on"}, HTTP_ACCEPT="application/json")
                self.assertEqual(response.status_code, 400)
                answer.assert_not_called()
                response = browser.get(reverse("chatbot:index"), {"conversation": self.conversation.pk})
                self.assertEqual(response.status_code, 404)
                response = browser.post(reverse("chatbot:clear", args=[self.conversation.pk]))
                self.assertEqual(response.status_code, 404)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertTrue(Message.objects.filter(conversation=self.conversation).exists())

    def test_mutations_require_csrf_even_for_the_authenticated_owner(self):
        protected = Client(enforce_csrf_checks=True)
        protected.cookies = self.client.cookies
        urls = [self.farm_url(route) for route in ["farms:edit", "farms:delete", "boundaries:editor", "boundaries:delete", "climate:refresh", "weather:refresh", "simulator:workbench"]]
        for section, entry in [("calendar", self.event), ("ledger", self.transaction), ("diary", self.diary), ("soil", self.soil)]:
            urls.extend([self.record_url("create", section), self.record_url("edit", section, entry), self.record_url("delete", section, entry)])
        urls.extend([self.record_url("complete", entry=self.event), reverse("chatbot:send"), reverse("chatbot:clear", args=[self.conversation.pk]), reverse("accounts:logout"), reverse("accounts:password_change"), reverse("core:demo")])
        for url in urls:
            with self.subTest(route=url):
                self.assertEqual(protected.post(url, {"completed": "1"}).status_code, 403)
        self.assertTrue(Farm.objects.filter(pk=self.farm.pk).exists())
        self.event.refresh_from_db()
        self.assertFalse(self.event.completed)
        self.assertEqual(int(protected.session["_auth_user_id"]), self.owner.pk)

    def test_valid_csrf_allows_owner_save_but_foreign_origin_cannot_reuse_token(self):
        protected = Client(enforce_csrf_checks=True)
        protected.cookies = self.client.cookies
        editor = self.farm_url("boundaries:editor")
        self.assertEqual(protected.get(editor).status_code, 200)
        token = protected.cookies[settings.CSRF_COOKIE_NAME].value
        geometry = {"type": "Polygon", "coordinates": [[[90, 25], [90.001, 25], [90.001, 25.001], [90, 25.001], [90, 25]]]}
        payload = {"geometry": json.dumps(geometry), "csrfmiddlewaretoken": token}
        response = protected.post(editor, payload, HTTP_ORIGIN="https://attacker.invalid")
        self.assertEqual(response.status_code, 403)
        self.boundary.refresh_from_db()
        self.assertNotEqual(self.boundary.geometry, geometry)
        response = protected.post(editor, payload)
        self.assertEqual(response.status_code, 302)
        self.boundary.refresh_from_db()
        self.assertEqual(self.boundary.geometry, geometry)

    def test_photos_env_database_and_settings_have_no_public_file_routes(self):
        paths = ["/.env", "/.env.example", "/db.sqlite3", "/agritwin/settings.py", "/agritwin/settings.pyc", "/media/" + self.diary.photo.name, "/static/.env", "/static/../.env", "/static/../db.sqlite3", "/frontend/dist/index.html"]
        for browser in [self.anonymous, self.other, self.client]:
            for url in paths:
                with self.subTest(authenticated=browser is not self.anonymous, route=url):
                    response = browser.get(url)
                    self.assertIn(response.status_code, {403, 404})
                    self.assertFalse(settings.SECRET_KEY.encode() in response.content, "A server signing secret must never be returned")

    def test_admin_requires_django_staff_and_ignores_secret_headers(self):
        for browser in [self.anonymous, self.other, self.client]:
            response = browser.get("/admin/farms/farm/", {"is_staff": "true", "admin_secret": "synthetic-not-a-real-secret"}, HTTP_X_ADMIN_SECRET="synthetic-not-a-real-secret")
            self.assertEqual(response.status_code, 302)
            self.assertIn("/admin/login/", response.url)
        self.other_user.refresh_from_db()
        self.assertFalse(self.other_user.is_staff)
        self.assertFalse(self.other_user.is_superuser)

    def test_authorized_owner_can_still_read_tools_and_private_photo_without_network(self):
        urls = [self.farm_url(route) for route in ["boundaries:editor", "boundaries:download", "notebook:calendar", "notebook:ledger", "notebook:diary", "notebook:soil", "climate:nasa_source", "reports:detail"]]
        urls.extend(self.farm_url("reports:download", output) for output in ["json", "csv", "pdf"])
        for url in urls:
            with self.subTest(route=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(settings.SECRET_KEY.encode() in response.content, "A server signing secret must never be delivered to an owner")
        photo = self.client.get(self.record_url("photo", entry=self.diary))
        self.assertEqual(photo.status_code, 200)
        self.assertEqual(photo["Cache-Control"], "private, no-store")
        self.assertTrue(b"".join(photo.streaming_content).startswith(b"\x89PNG"))
        photo.close()

    def test_logout_removes_access_to_every_private_farm_tool_and_photo(self):
        self.client.post(reverse("accounts:logout"))
        for url in self.private_get_urls():
            with self.subTest(route=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_guest_registration_claims_only_unowned_records_in_actual_server_session(self):
        guest_browser = Client()
        session = guest_browser.session
        session.save()
        guest = Farm.objects.create(owner_session=session.session_key, **{**Farm.example_defaults(), "name": "Claimable guest farm"})
        other_guest = Farm.objects.create(owner_session="separate-session", **{**Farm.example_defaults(), "name": "Unrelated guest farm"})
        response = guest_browser.post(reverse("accounts:signup"), {"username": "fresh-account", "password1": "FreshSynthetic!2026", "password2": "FreshSynthetic!2026", "owner_session": "separate-session", "owner_id": self.owner.pk})
        self.assertEqual(response.status_code, 302)
        guest.refresh_from_db()
        other_guest.refresh_from_db()
        self.farm.refresh_from_db()
        self.assertEqual(guest.owner.username, "fresh-account")
        self.assertEqual(guest.owner_session, "")
        self.assertIsNone(other_guest.owner)
        self.assertEqual(self.farm.owner, self.owner)
        self.assertEqual(guest_browser.get(self.farm_url("farms:edit", farm=guest)).status_code, 200)
        self.assertEqual(guest_browser.get(self.farm_url("farms:edit")).status_code, 404)
