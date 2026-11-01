"""Secrets are server-only configuration and deployment fails safely."""
import base64
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import os
import runpy
import tempfile
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from core.security import require_secret_key, validate_public_environment

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_TEST_KEY = "test-only-private-server-signing-value-with-more-than-fifty-characters-73"


def role_token(role):
    payload = base64.urlsafe_b64encode(json.dumps({"role": role}).encode()).decode().rstrip("=")
    return "header." + payload + ".signature"


class ServerSecretConfigurationTests(SimpleTestCase):
    def test_requires_private_nonplaceholder_key_without_logging_the_value(self):
        for value in ("", "short-secret", "x" * 80, "django-insecure-" + "known-development-value" * 4, "replace-this-with-a-long-random-private-key-before-hosting"):
            with self.subTest(value_length=len(value)):
                with self.assertRaises(ImproperlyConfigured) as error:
                    require_secret_key({"DJANGO_SECRET_KEY": value})
                if value:
                    self.assertNotIn(value, str(error.exception))
                self.assertIn("DJANGO_SECRET_KEY", str(error.exception))
        self.assertEqual(require_secret_key({"DJANGO_SECRET_KEY": PRIVATE_TEST_KEY}), PRIVATE_TEST_KEY)

    def test_rejects_privileged_credentials_under_browser_public_names(self):
        examples = {
            "VITE_SUPABASE_SERVICE_ROLE_KEY": "private-canary-service-role-value",
            "NEXT_PUBLIC_ADMIN_SECRET": "private-canary-admin-value",
            "NEXT_PUBLIC_ADMIN_API_KEY": "private-canary-admin-api-value",
            "VITE_ADMIN_ACCESS_TOKEN": "private-canary-admin-token-value",
            "PUBLIC_DJANGO_SECRET_KEY": PRIVATE_TEST_KEY,
            "REACT_APP_SUPABASE_KEY": role_token("service_role"),
            "EXPO_PUBLIC_SUPABASE_KEY": "sb_secret_test_canary",
            "NUXT_PUBLIC_SECRET": "private-canary-server-value",
            "VITE_CREDENTIAL": "-----BEGIN PRIVATE KEY-----\ncanary\n-----END PRIVATE KEY-----",
        }
        for name, value in examples.items():
            with self.subTest(name=name):
                with self.assertRaises(ImproperlyConfigured) as error:
                    validate_public_environment({name: value})
                self.assertIn(name, str(error.exception))
                self.assertNotIn(value, str(error.exception))

    def test_public_publishable_and_anon_keys_and_server_only_secrets_are_allowed(self):
        validate_public_environment({
            "VITE_SUPABASE_URL": "https://example.supabase.co",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY": role_token("anon"),
            "PUBLIC_SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test_canary",
            "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_server_only_canary",
            "ADMIN_SECRET_KEY": "server-only-canary",
            "DJANGO_SECRET_KEY": PRIVATE_TEST_KEY,
            "VITE_ADMIN_SECRET": "",
        })

    def test_invalid_public_token_cannot_crash_the_config_check(self):
        for value in ("not-a-token", "x.%%%.y", "x.W10.y", "x." + "a" * 17000 + ".y"):
            validate_public_environment({"VITE_SUPABASE_ANON_KEY": value})

    def _load_settings(self, **overrides):
        environment = {"DJANGO_SECRET_KEY": PRIVATE_TEST_KEY, "DJANGO_DEBUG": "False", "DJANGO_ALLOWED_HOSTS": "farm.example.test", **overrides}
        with patch.dict(os.environ, environment, clear=True), patch("pathlib.Path.exists", return_value=False):
            return runpy.run_path(str(ROOT / "agritwin/settings.py"))

    def test_production_enforces_https_secure_cookies_explicit_hosts_and_hsts(self):
        config = self._load_settings()
        self.assertFalse(config["DEBUG"])
        for option in ("SESSION_COOKIE_HTTPONLY", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_SSL_REDIRECT", "SECURE_CONTENT_TYPE_NOSNIFF"):
            self.assertTrue(config[option], option)
        self.assertGreater(config["SECURE_HSTS_SECONDS"], 0)
        self.assertEqual(config["X_FRAME_OPTIONS"], "DENY")
        self.assertEqual(config["ALLOWED_HOSTS"], ["farm.example.test"])

    def test_production_refuses_wildcard_hosts_or_missing_key(self):
        for values in ({"DJANGO_ALLOWED_HOSTS": "*"}, {"DJANGO_ALLOWED_HOSTS": ""}, {"DJANGO_SECRET_KEY": ""}):
            with self.subTest(options=list(values)):
                with self.assertRaises(ImproperlyConfigured):
                    self._load_settings(**values)

    def test_development_still_requires_a_key_and_keeps_local_http_working(self):
        config = self._load_settings(DJANGO_DEBUG="True")
        self.assertFalse(config["SESSION_COOKIE_SECURE"])
        self.assertFalse(config["SECURE_SSL_REDIRECT"])
        self.assertEqual(config["SECURE_HSTS_SECONDS"], 0)
        with self.assertRaises(ImproperlyConfigured):
            self._load_settings(DJANGO_DEBUG="True", DJANGO_SECRET_KEY="")

    def test_unset_debug_is_secure_by_default(self):
        environment = {"DJANGO_SECRET_KEY": PRIVATE_TEST_KEY, "DJANGO_ALLOWED_HOSTS": "farm.example.test"}
        with patch.dict(os.environ, environment, clear=True), patch("pathlib.Path.exists", return_value=False):
            config = runpy.run_path(str(ROOT / "agritwin/settings.py"))
        self.assertFalse(config["DEBUG"])
        self.assertTrue(config["SECURE_SSL_REDIRECT"])

    def test_settings_reject_browser_exposed_service_role_key(self):
        with self.assertRaises(ImproperlyConfigured):
            self._load_settings(VITE_SUPABASE_KEY=role_token("service_role"))


class LocalSecretSetupTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        spec = spec_from_file_location("agritwin_local_setup", ROOT / "scripts/setup_env.py")
        cls.setup = module_from_spec(spec)
        spec.loader.exec_module(cls.setup)

    def test_setup_generates_private_key_and_preserves_other_config(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / ".env"
            file.write_text("# local config\nOTHER_PROVIDER_KEY=keep-this-value\n", encoding="utf-8")
            self.assertTrue(self.setup.configure_local_env(file))
            result = file.read_text(encoding="utf-8")
            self.assertIn("OTHER_PROVIDER_KEY=keep-this-value", result)
            self.assertIn("DJANGO_DEBUG=True", result)
            key = next(line.split("=", 1)[1] for line in result.splitlines() if line.startswith("DJANGO_SECRET_KEY="))
            self.assertEqual(require_secret_key({"DJANGO_SECRET_KEY": key}), key)
            self.assertFalse(self.setup.configure_local_env(file))
            self.assertEqual(file.read_text(encoding="utf-8"), result)

    def test_setup_replaces_example_placeholder_and_removes_duplicate_definitions(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / ".env"
            file.write_text("DJANGO_SECRET_KEY=replace-this-with-a-long-random-private-key-before-hosting\nDJANGO_SECRET_KEY=\n", encoding="utf-8")
            self.assertTrue(self.setup.configure_local_env(file))
            result = file.read_text(encoding="utf-8")
            self.assertEqual(sum(line.startswith("DJANGO_SECRET_KEY=") for line in result.splitlines()), 1)
            self.assertNotIn("replace-this", result)

    def test_setup_keeps_existing_key_and_production_debug_setting(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / ".env"
            before = "DJANGO_DEBUG=False\nDJANGO_SECRET_KEY=" + PRIVATE_TEST_KEY + "\n"
            file.write_text(before, encoding="utf-8")
            self.assertFalse(self.setup.configure_local_env(file))
            self.assertEqual(file.read_text(encoding="utf-8"), before)
