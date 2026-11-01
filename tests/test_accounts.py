"""Account ownership, guest claiming and credential flows stay isolated."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from climate.services import NASADataUnavailable
from farms.models import Farm


class AccountOwnershipTests(TestCase):
    password = "FieldNotebook!2026-Safe"

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="farmer", password=self.password)
        self.other_user = get_user_model().objects.create_user(username="other", password=self.password)
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.guest_key = session.session_key
        self.guest = Farm.objects.create(owner_session=self.guest_key, **{**Farm.example_defaults(), "name": "Guest field"})
        self.saved = Farm.objects.create(owner=self.user, owner_session="", **{**Farm.example_defaults(), "name": "Account field"})

    def credentials(self, **overrides):
        data = {"username": "farmer", "password": self.password}
        data.update(overrides)
        return data

    def signup_data(self, **overrides):
        data = {"username": "newfarmer", "password1": self.password, "password2": self.password}
        data.update(overrides)
        return data

    def test_login_claims_only_this_guest_session_and_rotates_key(self):
        foreign = Farm.objects.create(owner_session="another-browser", **Farm.example_defaults())
        already_owned = Farm.objects.create(owner=self.other_user, owner_session=self.guest_key, **Farm.example_defaults())
        response = self.client.post(reverse("accounts:login"), self.credentials())
        self.assertRedirects(response, reverse("farms:list"))
        self.assertNotEqual(self.client.session.session_key, self.guest_key)
        self.guest.refresh_from_db()
        foreign.refresh_from_db()
        already_owned.refresh_from_db()
        self.assertEqual(self.guest.owner, self.user)
        self.assertEqual(self.guest.owner_session, "")
        self.assertIsNone(foreign.owner)
        self.assertEqual(already_owned.owner, self.other_user)
        response = self.client.get(reverse("farms:list"))
        self.assertQuerySetEqual(response.context["farms"], {self.guest, self.saved}, ordered=False)

    def test_same_account_can_access_farms_from_second_device(self):
        self.client.post(reverse("accounts:login"), self.credentials())
        second_device = Client()
        second_device.post(reverse("accounts:login"), self.credentials())
        response = second_device.get(reverse("farms:list"))
        self.assertEqual(set(response.context["farms"]), {self.guest, self.saved})
        self.assertEqual(second_device.get(reverse("farms:edit", args=[self.guest.pk])).status_code, 200)

    def test_registration_claims_guest_farm_and_hashes_password(self):
        response = self.client.post(reverse("accounts:signup"), self.signup_data())
        self.assertRedirects(response, reverse("farms:list"))
        new_user = get_user_model().objects.get(username="newfarmer")
        self.assertTrue(new_user.check_password(self.password))
        self.assertNotEqual(new_user.password, self.password)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.owner, new_user)
        self.assertEqual(int(self.client.session["_auth_user_id"]), new_user.pk)

    def test_failed_login_cannot_claim_guest_farm(self):
        response = self.client.post(reverse("accounts:login"), self.credentials(password="wrong"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].non_field_errors())
        self.guest.refresh_from_db()
        self.assertIsNone(self.guest.owner)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_weak_or_mismatched_password_does_not_create_account(self):
        for overrides in [{"password1": "123", "password2": "123"}, {"password2": "Different!2026"}]:
            with self.subTest(overrides=overrides):
                response = self.client.post(reverse("accounts:signup"), self.signup_data(**overrides))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertFalse(get_user_model().objects.filter(username="newfarmer").exists())
        self.guest.refresh_from_db()
        self.assertIsNone(self.guest.owner)

    def test_duplicate_username_is_rejected(self):
        response = self.client.post(reverse("accounts:signup"), self.signup_data(username="farmer"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)

    def test_inactive_account_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post(reverse("accounts:login"), self.credentials())
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_redirects_reject_external_targets_on_login_and_signup(self):
        for route, data in [("accounts:login", self.credentials()), ("accounts:signup", self.signup_data())]:
            with self.subTest(route=route):
                browser = Client()
                response = browser.post(reverse(route), {**data, "next": "https://attacker.invalid/steal"})
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, reverse("farms:list"))

    def test_login_preserves_safe_local_next(self):
        response = self.client.post(reverse("accounts:login"), self.credentials(next=reverse("accounts:profile")))
        self.assertRedirects(response, reverse("accounts:profile"))

    def test_other_account_cannot_read_edit_delete_or_export(self):
        outsider = Client()
        outsider.force_login(self.other_user)
        for route in ["farms:detail", "farms:edit", "climate:dashboard", "rotations:explorer", "simulator:workbench", "reports:detail"]:
            with self.subTest(route=route):
                self.assertEqual(outsider.get(reverse(route, args=[self.saved.pk])).status_code, 404)
        self.assertEqual(outsider.post(reverse("farms:delete", args=[self.saved.pk])).status_code, 404)
        self.assertEqual(outsider.get(reverse("reports:download", args=[self.saved.pk, "json"])).status_code, 404)
        self.assertEqual(outsider.get(reverse("chatbot:index") + f"?farm={self.saved.pk}").status_code, 404)
        self.assertTrue(Farm.objects.filter(pk=self.saved.pk).exists())

    def test_session_cookie_never_overrides_account_ownership(self):
        self.saved.owner_session = self.guest_key
        self.saved.save()
        response = self.client.get(reverse("farms:list"))
        self.assertEqual(list(response.context["farms"]), [self.guest])
        self.assertEqual(self.client.get(reverse("farms:edit", args=[self.saved.pk])).status_code, 404)
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("farms:list"))
        self.assertNotIn(self.saved, response.context["farms"])
        self.assertNotIn(self.guest, response.context["farms"])

    def test_logout_revokes_browser_access_and_retains_language(self):
        self.client.post(reverse("accounts:login"), self.credentials())
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("core:home"))
        self.assertEqual(self.client.session.get("language"), "en")
        self.assertEqual(self.client.get(reverse("farms:edit", args=[self.saved.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("farms:edit", args=[self.guest.pk])).status_code, 404)

    def test_authentication_forms_enforce_csrf(self):
        protected = Client(enforce_csrf_checks=True)
        for route, data in [("accounts:login", self.credentials()), ("accounts:signup", self.signup_data()), ("accounts:logout", {})]:
            with self.subTest(route=route):
                self.assertEqual(protected.post(reverse(route), data).status_code, 403)

    @patch("farms.views.ensure_analysis", side_effect=NASADataUnavailable("NASA unavailable"))
    def test_new_authenticated_farm_has_account_ownership(self, nasa):
        self.client.force_login(self.user)
        data = {"name": "New account field", "location_name": "Rajshahi, Bangladesh", "latitude": "24.3745", "longitude": "88.6042", "farm_size_acres": "3", "current_crops": ["aman_rice"], "soil_type": "unknown", "soil_ph": "", "drainage": "unknown", "irrigation_availability": "limited", "farming_priority": "water_conservation", "budget": "medium"}
        response = self.client.post(reverse("farms:create"), data)
        self.assertEqual(response.status_code, 302)
        farm = Farm.objects.get(name="New account field")
        self.assertEqual(farm.owner, self.user)
        self.assertEqual(farm.owner_session, "")

    @patch("core.views.ensure_analysis", side_effect=NASADataUnavailable("NASA unavailable"))
    def test_example_is_owned_by_account_and_reused(self, nasa):
        self.client.force_login(self.user)
        first = self.client.post(reverse("core:demo"))
        second = self.client.post(reverse("core:demo"))
        self.assertEqual(first.url, second.url)
        self.assertEqual(Farm.objects.filter(owner=self.user, name="Rajshahi example farm").count(), 1)

    def test_profile_requires_authentication_and_password_change_keeps_farms(self):
        self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 302)
        self.client.post(reverse("accounts:login"), self.credentials())
        response = self.client.post(reverse("accounts:password_change"), {"old_password": self.password, "new_password1": "Better!FieldNotes2027", "new_password2": "Better!FieldNotes2027"})
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Better!FieldNotes2027"))
        self.assertEqual(self.client.get(reverse("farms:edit", args=[self.saved.pk])).status_code, 200)

    def test_anonymous_browser_without_session_never_sees_unowned_data(self):
        Farm.objects.create(owner_session="", **Farm.example_defaults())
        response = Client().get(reverse("farms:list"))
        self.assertFalse(response.context["farms"].exists())
