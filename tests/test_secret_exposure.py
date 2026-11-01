"""Exercise rendered responses and served assets with backend-only sentinels.

These values are generated for the test process. No test reads or prints the
developer's .env values or copies credentials into a browser-visible fixture.
"""
import os
from pathlib import Path
import secrets
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles.views import serve
from django.core.exceptions import SuspiciousFileOperation
from django.http import Http404
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import path, reverse


def fail_with_server_setting(request):
    # A real production exception must not turn server settings into HTML.
    server_only_value = settings.SUPABASE_SERVICE_ROLE_KEY
    raise RuntimeError("Deliberate test exception")


urlpatterns = [path("test-failure/", fail_with_server_setting)]


class SecretExposureTests(TestCase):
    def setUp(self):
        self.sentinels = {
            "DJANGO_SECRET_KEY": "test-only-server-key-" + secrets.token_hex(32),
            "SUPABASE_SERVICE_ROLE_KEY": "test-only-service-role-" + secrets.token_hex(24),
            "SUPABASE_SECRET_KEY": "test-only-supabase-secret-" + secrets.token_hex(24),
            "ADMIN_API_KEY": "test-only-admin-key-" + secrets.token_hex(24),
        }
        environment = patch.dict(os.environ, self.sentinels)
        environment.start()
        self.addCleanup(environment.stop)
        configuration = override_settings(
            DEBUG=False,
            SECRET_KEY=self.sentinels["DJANGO_SECRET_KEY"],
            SUPABASE_SERVICE_ROLE_KEY=self.sentinels["SUPABASE_SERVICE_ROLE_KEY"],
            SUPABASE_SECRET_KEY=self.sentinels["SUPABASE_SECRET_KEY"],
            ADMIN_API_KEY=self.sentinels["ADMIN_API_KEY"],
            SECURE_SSL_REDIRECT=False,
        )
        configuration.enable()
        self.addCleanup(configuration.disable)

    def assert_no_backend_secrets(self, content):
        for name, sentinel in self.sentinels.items():
            # The assertion reports only a key name if a future regression
            # serializes one. Do not include the matching response in errors.
            self.assertFalse(sentinel.encode() in content, f"Backend credential exposed: {name}")

    def response_bytes(self, response):
        return b"".join(response.streaming_content) if response.streaming else response.content

    def test_public_html_json_and_auth_pages_do_not_serialize_backend_values(self):
        for route in ("core:home", "core:about", "core:health", "accounts:login", "accounts:signup", "farms:list", "chatbot:index"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route), follow=True)
                self.assertEqual(response.status_code, 200)
                self.assert_no_backend_secrets(self.response_bytes(response))
                self.assert_no_backend_secrets(str(dict(response.headers)).encode())

    def test_first_party_browser_assets_do_not_serialize_backend_values(self):
        request = RequestFactory().get("/static/test-asset")
        tested = 0
        root = Path(settings.BASE_DIR) / "static"
        for asset in root.rglob("*"):
            if not asset.is_file() or asset.suffix.lower() not in {".js", ".css", ".html", ".json", ".map"}:
                continue
            relative = asset.relative_to(root).as_posix()
            with self.subTest(asset=relative):
                response = serve(request, relative, insecure=True)
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assert_no_backend_secrets(self.response_bytes(response))
                finally:
                    response.close()
                tested += 1
        self.assertGreater(tested, 0)

    def test_source_database_environment_and_private_media_are_not_public_routes(self):
        for target in (
            "/.env", "/.env.local", "/.git/config", "/db.sqlite3",
            "/agritwin/settings.py", "/core/security.py", "/manage.py",
            "/frontend/dist/index.html", "/media/diary/private-photo.jpg",
            "/api/env/", "/api/config/",
        ):
            with self.subTest(target=target):
                response = self.client.get(target)
                self.assertEqual(response.status_code, 404)
                self.assert_no_backend_secrets(self.response_bytes(response))

    def test_static_handler_cannot_read_project_environment_or_traverse_outside_assets(self):
        request = RequestFactory().get("/static/missing")
        for target in (".env", "../.env", "../../.env", "../db.sqlite3", "../agritwin/settings.py", "../media/diary/private-photo.jpg"):
            with self.subTest(target=target):
                with self.assertRaises((Http404, SuspiciousFileOperation)):
                    serve(request, target, insecure=True)

    @override_settings(ROOT_URLCONF="tests.test_secret_exposure")
    def test_production_error_response_hides_server_settings_and_locals(self):
        client = Client(raise_request_exception=False)
        response = client.get("/test-failure/")
        self.assertEqual(response.status_code, 500)
        self.assert_no_backend_secrets(response.content)
        self.assertNotIn(b"Traceback", response.content)
        self.assertNotIn(b"server_only_value", response.content)
