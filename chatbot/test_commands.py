"""Offline checks for the local chatbot verification command."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings


class CheckChatbotCommandTests(SimpleTestCase):
    @override_settings(OPENAI_API_KEY="unused-private-key", CHATBOT_AI_ENABLED=True)
    @patch("requests.sessions.Session.request", side_effect=AssertionError("Chat must stay local"))
    def test_real_bilingual_check_works_without_network_even_with_legacy_credentials(self, request):
        output = StringIO()
        call_command("check_chatbot", stdout=output)
        self.assertIn("Local chatbot verified in Bangla and English", output.getvalue())
        self.assertNotIn("unused-private-key", output.getvalue())
        request.assert_not_called()

    @patch("chatbot.management.commands.check_chatbot.answer_question")
    def test_empty_or_nonlocal_answer_is_not_reported_as_success(self, answer):
        for reply in (None, {"mode": "local", "text": ""}, {"mode": "ai", "text": "Old provider answer"}):
            with self.subTest(reply=reply):
                answer.return_value = reply
                output = StringIO()
                with self.assertRaisesMessage(CommandError, "local chatbot did not return a valid answer"):
                    call_command("check_chatbot", stdout=output)
                self.assertNotIn("verified", output.getvalue())
