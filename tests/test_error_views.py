"""The configured CSRF handler must resolve during startup and reject safely."""
from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse
from django.urls.utils import get_callable

from core.error_views import csrf_failure

class CsrfErrorViewTests(TestCase):
    def test_configured_handler_imports_directly(self):
        self.assertEqual(settings.CSRF_FAILURE_VIEW, "core.error_views.csrf_failure")
        self.assertIs(get_callable(settings.CSRF_FAILURE_VIEW), csrf_failure)
        self.assertIs(get_callable("core.views.csrf_failure"), csrf_failure)

    def test_missing_csrf_token_shows_bangla_403(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("farms:create"), {})
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403.html")
        self.assertContains(response, '<html lang="bn">', status_code=403)
        self.assertNotContains(response, "CSRF cookie not set", status_code=403)

    def test_csrf_error_respects_english_selection(self):
        client = Client(enforce_csrf_checks=True)
        session = client.session
        session["language"] = "en"
        session.save()
        response = client.post(reverse("farms:create"), {})
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "403.html")
        self.assertContains(response, '<html lang="en">', status_code=403)
