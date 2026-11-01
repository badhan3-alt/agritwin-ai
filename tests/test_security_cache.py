"""A browser/shared cache must not retain private farm/account responses."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PrivateWorkspaceCacheTests(TestCase):
    def assert_private(self, response):
        directives = {item.strip() for item in response["Cache-Control"].split(",")}
        self.assertIn("private", directives)
        self.assertIn("no-store", directives)
        self.assertIn("Cookie", response["Vary"])

    def test_guest_account_and_farm_pages_disable_storage(self):
        for route in ["accounts:login", "accounts:signup", "farms:list", "chatbot:index"]:
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                self.assert_private(response)

    def test_authenticated_home_and_logout_disable_storage(self):
        user = get_user_model().objects.create_user(username="cache-owner", password="Synthetic-test-password-26")
        self.client.force_login(user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "cache-owner")
        self.assert_private(response)
        self.assert_private(self.client.post(reverse("accounts:logout")))
