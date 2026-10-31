"""Offline checks for session-private farmer chat and explicit farm sharing."""
from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from chatbot.models import Conversation, Message
from climate.services import _parse_power
from farms.models import Analysis, Farm
from rotations.services import evaluate_rotations


class ChatVisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data.strip())


class FarmerChatFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.network = patch(
            "requests.sessions.Session.request",
            side_effect=AssertionError("Local chat flow must not fetch any network service"),
        )
        self.network_mock = self.network.start()
        self.addCleanup(self.network.stop)
        self.reply = {
            "text": "মাটি পরীক্ষা করে সেচ ও সার পরিকল্পনা করুন।",
            "mode": "local",
            "sources": [{"title": "কৃষি তথ্য সার্ভিস", "url": "https://ais.gov.bd/"}],
            "notice": "",
            "topic": "soil",
        }
        self.answer = patch("chatbot.views.answer_question", side_effect=lambda *args, **kwargs: deepcopy(self.reply))
        self.answer_mock = self.answer.start()
        self.addCleanup(self.answer.stop)
        session = self.client.session
        session.save()
        self.owner = session.session_key
        self.farm = Farm.objects.create(owner_session=self.owner, **Farm.example_defaults())
        self.other_client = Client()
        other_session = self.other_client.session
        other_session.save()
        other_defaults = Farm.example_defaults()
        other_defaults["name"] = "Other browser private field"
        self.other_farm = Farm.objects.create(owner_session=other_session.session_key, **other_defaults)

    def send(self, *, client=None, **data):
        return (client or self.client).post(
            reverse("chatbot:send"),
            {"message": "আমার জমির মাটির যত্ন কীভাবে নেব?", **data},
            HTTP_ACCEPT="application/json",
        )

    def saved_analysis(self, farm=None):
        farm = farm or self.farm
        raw = json.loads((Path(__file__).parent / "fixtures" / "nasa_power_climatology.json").read_text(encoding="utf-8"))
        climate = _parse_power(
            raw, farm.latitude, farm.longitude,
            "https://power.larc.nasa.gov/api/temporal/climatology/point?latitude=24.3745&longitude=88.6042",
        )
        return Analysis.objects.create(farm=farm, climate=climate, strategies=evaluate_rotations(farm.to_profile(), climate))

    def test_opening_chat_is_read_only_and_defaults_to_bangla(self):
        response = self.client.get(reverse("chatbot:index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Language"], "bn")
        self.assertContains(response, '<html lang="bn">')
        self.assertRegex(str(response.context["form"].fields["message"].label), r"[\u0980-\u09ff]")
        self.assertFalse(response.context["form"].fields["include_farm"].initial)
        self.assertEqual(list(response.context["form"].fields["farm"].queryset), [self.farm])
        self.assertEqual(response.context["chat_mode"], "local")
        self.assertEqual(Conversation.objects.count(), 0)
        self.answer_mock.assert_not_called()

    def test_default_chat_has_no_untranslated_english_interface_text(self):
        response = self.client.get(reverse("chatbot:index"))
        parser = ChatVisibleText()
        parser.feed(response.content.decode("utf-8"))
        untranslated = [
            part for part in parser.parts
            if re.search(r"[A-Za-z]{3,}", part)
            and not re.search(r"[\u0980-\u09ff]", part)
            and part not in {"English", "AgriTwin", "AgriTwin AI", "CSV", "JSON"} and "https://" not in part
        ]
        self.assertEqual(untranslated, [])

    def test_json_send_saves_question_reply_and_owned_conversation(self):
        response = self.send()
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        conversation = Conversation.objects.get(pk=payload["conversation_id"])
        self.assertEqual(conversation.owner_session, self.owner)
        self.assertEqual(conversation.messages.count(), 2)
        self.assertEqual(payload["user"]["role"], "user")
        self.assertEqual(payload["assistant"]["body"], self.reply["text"])
        self.assertEqual(payload["assistant"]["mode"], "local")
        self.assertEqual(payload["assistant"]["sources"], self.reply["sources"])
        self.assertEqual(payload["clear_url"], reverse("chatbot:clear", kwargs={"pk": conversation.pk}))
        self.assertEqual(self.answer_mock.call_args.kwargs["language"], "bn")
        self.assertIsNone(self.answer_mock.call_args.kwargs["farm_context"])
        self.network_mock.assert_not_called()

    def test_normal_html_form_redirects_and_restores_history(self):
        response = self.client.post(reverse("chatbot:send"), {"message": "How can I conserve irrigation water?"})
        self.assertEqual(response.status_code, 302)
        conversation = Conversation.objects.get(owner_session=self.owner)
        self.assertEqual(response.url, reverse("chatbot:index") + f"?conversation={conversation.pk}")
        page = self.client.get(response.url)
        self.assertContains(page, "How can I conserve irrigation water?")
        self.assertContains(page, self.reply["text"])
        self.assertEqual(len(page.context["chat_messages"]), 2)

    def test_subsequent_question_uses_only_its_conversation_history(self):
        first = self.send(message="Private irrigation question").json()
        foreign = Conversation.objects.create(owner_session=self.other_client.session.session_key, title="Private outsider")
        Message.objects.create(conversation=foreign, role="user", body="Other browser secret message")
        response = self.send(conversation=first["conversation_id"], message="What should I check next?")
        self.assertEqual(response.status_code, 200)
        history = self.answer_mock.call_args.kwargs["history"]
        serialized = json.dumps(history, ensure_ascii=False)
        self.assertIn("Private irrigation question", serialized)
        self.assertIn(self.reply["text"], serialized)
        self.assertNotIn("Other browser secret message", serialized)
        self.assertEqual(Conversation.objects.get(pk=first["conversation_id"]).messages.count(), 4)

    def test_other_browser_cannot_list_read_append_or_clear_conversation(self):
        payload = self.send(message="My private crop question").json()
        pk = payload["conversation_id"]
        foreign_index = self.other_client.get(reverse("chatbot:index"))
        self.assertNotContains(foreign_index, "My private crop question")
        self.assertEqual(list(foreign_index.context["conversations"]), [])
        self.answer_mock.reset_mock()
        self.assertEqual(self.other_client.get(payload["conversation_url"]).status_code, 404)
        self.assertEqual(self.send(client=self.other_client, conversation=pk).status_code, 404)
        self.assertEqual(self.other_client.post(payload["clear_url"]).status_code, 404)
        self.assertEqual(Message.objects.filter(conversation_id=pk).count(), 2)
        self.answer_mock.assert_not_called()

    def test_mutations_reject_get(self):
        conversation = Conversation.objects.create(owner_session=self.owner, title="Keep this history")
        self.assertEqual(self.client.get(reverse("chatbot:send")).status_code, 405)
        self.assertEqual(self.client.get(reverse("chatbot:clear", kwargs={"pk": conversation.pk})).status_code, 405)
        self.assertTrue(Conversation.objects.filter(pk=conversation.pk).exists())
        self.answer_mock.assert_not_called()

    def test_missing_csrf_token_cannot_send_or_clear(self):
        secured = Client(enforce_csrf_checks=True)
        session = secured.session
        session.save()
        conversation = Conversation.objects.create(owner_session=session.session_key, title="CSRF protected")
        self.assertEqual(self.send(client=secured).status_code, 403)
        self.assertEqual(secured.post(reverse("chatbot:clear", kwargs={"pk": conversation.pk})).status_code, 403)
        self.assertTrue(Conversation.objects.filter(pk=conversation.pk).exists())
        self.assertEqual(Message.objects.count(), 0)
        self.answer_mock.assert_not_called()

    def test_csrf_token_from_chat_form_allows_send(self):
        secured = Client(enforce_csrf_checks=True)
        self.assertEqual(secured.get(reverse("chatbot:index")).status_code, 200)
        token = secured.cookies["csrftoken"].value
        response = secured.post(reverse("chatbot:send"), {"message": "How should I test soil?", "csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Message.objects.count(), 2)

    def test_empty_oversized_and_invalid_conversation_input_is_rejected(self):
        for fields in ({"message": "   "}, {"message": "x" * 2001}, {"conversation": "not-an-id"}, {"conversation": "-1"}):
            with self.subTest(fields=fields):
                response = self.send(**fields)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json()["errors"])
        self.assertEqual(Conversation.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)
        self.answer_mock.assert_not_called()

    def test_foreign_farm_and_opt_in_without_farm_are_rejected(self):
        for fields in ({"farm": self.other_farm.pk, "include_farm": "on"}, {"include_farm": "on"}):
            with self.subTest(fields=fields):
                response = self.send(**fields)
                self.assertEqual(response.status_code, 400)
                self.assertIn("farm", response.json()["errors"])
        self.assertEqual(Conversation.objects.count(), 0)
        self.answer_mock.assert_not_called()

    def test_selecting_a_farm_does_not_share_it_without_explicit_opt_in(self):
        self.saved_analysis()
        response = self.send(farm=self.farm.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.answer_mock.call_args.kwargs["farm_context"])
        response = self.send(conversation=response.json()["conversation_id"], farm=self.farm.pk, include_farm="on")
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(self.answer_mock.call_args.kwargs["farm_context"])
        response = self.send(conversation=response.json()["conversation_id"], farm=self.farm.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.answer_mock.call_args.kwargs["farm_context"])
        self.network_mock.assert_not_called()

    def test_shared_farm_context_uses_saved_nasa_summary_and_excludes_private_data(self):
        self.farm.name = "Do not share this exact private field name"
        self.farm.save(update_fields=["name"])
        analysis = self.saved_analysis()
        original_climate = deepcopy(analysis.climate)
        response = self.send(farm=self.farm.pk, include_farm="on")
        self.assertEqual(response.status_code, 200)
        context = self.answer_mock.call_args.kwargs["farm_context"]
        self.assertEqual(context["climate"]["status"], "live")
        for key, value in analysis.climate["annual_summary"].items():
            if isinstance(value, (int, float)):
                self.assertEqual(context["climate"]["annual_summary"][key], value)
        analysis.refresh_from_db()
        self.assertEqual(analysis.climate, original_climate)
        self.assertEqual(
            re.findall(r"\d+", context["climate"]["provenance"]["period"]),
            re.findall(r"\d+", analysis.climate["provenance"]["period"]),
        )
        self.assertEqual(context["climate"]["provenance"]["retrieved_at"], analysis.climate["provenance"]["retrieved_at"])
        self.assertEqual(len(context["strategies"]), 3)
        serialized = json.dumps(context, ensure_ascii=False)
        for forbidden in (self.owner, self.farm.name, "owner_session", "latitude", "longitude", "raw_response", "budget", "24.3745", "88.6042", "?latitude="):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)
        self.assertEqual(context["climate"]["provenance"]["url"], "https://power.larc.nasa.gov/docs/services/api/temporal/climatology/")
        self.network_mock.assert_not_called()

    def test_unknown_custom_location_is_excluded_from_chat_context(self):
        self.farm.location_name = "Private homestead beside a named house"
        self.farm.save(update_fields=["location_name"])
        response = self.send(farm=self.farm.pk, include_farm="on")
        self.assertEqual(response.status_code, 200)
        context = self.answer_mock.call_args.kwargs["farm_context"]
        self.assertEqual(context["farm"]["location_name"], "বাংলাদেশ")
        self.assertNotIn(self.farm.location_name, json.dumps(context))

    def test_missing_or_unverified_analysis_never_invents_nasa_context(self):
        for unverified in (None, {"status": "live", "annual_summary": {"total_precip_mm": 1234}}):
            with self.subTest(unverified=unverified):
                if unverified is not None:
                    Analysis.objects.create(farm=self.farm, climate=unverified, strategies=[])
                response = self.send(farm=self.farm.pk, include_farm="on")
                self.assertEqual(response.status_code, 200)
                context = self.answer_mock.call_args.kwargs["farm_context"]
                self.assertIsNone(context["climate"])
                self.assertEqual(context["strategies"], [])
        self.network_mock.assert_not_called()

    def test_switching_to_english_changes_form_and_answer_language(self):
        response = self.client.post(reverse("core:language"), {"language": "en", "next": reverse("chatbot:index")})
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("chatbot:index"))
        self.assertEqual(response["Content-Language"], "en")
        self.assertContains(response, "Your question")
        self.assertContains(response, '<html lang="en">')
        self.assertEqual(self.send(message="How should I irrigate my rice?").status_code, 200)
        self.assertEqual(self.answer_mock.call_args.kwargs["language"], "en")

    def test_user_and_assistant_html_are_rendered_as_plain_text(self):
        self.reply["text"] = '<img src=x onerror="alert(\'assistant\')">'
        self.reply["notice"] = '<script>alert("notice")</script>'
        question = '<script>alert("farmer")</script>'
        payload = self.send(message=question).json()
        page = self.client.get(payload["conversation_url"])
        self.assertNotContains(page, question)
        self.assertNotContains(page, self.reply["text"])
        self.assertNotContains(page, self.reply["notice"])
        self.assertContains(page, "&lt;script&gt;")
        self.assertContains(page, "&lt;img src=x")

    def test_untrusted_reference_urls_are_not_saved_or_returned(self):
        self.reply["sources"] = [
            {"title": "Script", "url": "javascript:alert(1)"},
            {"title": "Unreviewed site", "url": "https://example.com/"},
            {"title": "Insecure source", "url": "http://ais.gov.bd/"},
            {"title": "Misleading credentials", "url": "https://attacker@ais.gov.bd/"},
            {"title": "Official", "url": "https://ais.gov.bd/"},
            {"title": "Malformed URL", "url": "https://["},
        ]
        payload = self.send().json()
        expected = [{"title": "Official", "url": "https://ais.gov.bd/"}]
        self.assertEqual(payload["assistant"]["sources"], expected)
        self.assertEqual(Message.objects.get(role="assistant").sources, expected)

    def test_reference_does_not_expose_a_precise_nasa_query(self):
        self.reply["sources"] = [{
            "title": "NASA response",
            "url": "https://power.larc.nasa.gov/api/temporal/climatology/point?latitude=24.3745&longitude=88.6042",
        }]
        payload = self.send().json()
        self.assertEqual(payload["assistant"]["sources"], [])

    def test_rate_limit_blocks_thirteenth_question_without_creating_messages(self):
        with patch("chatbot.views.time.time", return_value=2_000_000_000):
            payload = self.send().json()
            for _ in range(11):
                self.assertEqual(self.send(conversation=payload["conversation_id"]).status_code, 200)
            self.assertEqual(Message.objects.count(), 24)
            response = self.send(conversation=payload["conversation_id"])
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response["Retry-After"], "60")
            self.assertTrue(response.json()["error"])
            self.assertEqual(Message.objects.count(), 24)
            self.assertEqual(self.answer_mock.call_count, 12)

    def test_full_conversation_is_preserved_and_rejects_another_question(self):
        conversation = Conversation.objects.create(owner_session=self.owner, title="Full conversation")
        Message.objects.bulk_create([
            Message(conversation=conversation, role="user" if index % 2 == 0 else "assistant", body=f"Saved message {index}")
            for index in range(80)
        ])
        response = self.send(conversation=conversation.pk)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(conversation.messages.count(), 80)
        self.answer_mock.assert_not_called()

    def test_clear_deletes_only_owned_conversation_and_its_messages(self):
        payload = self.send().json()
        foreign = Conversation.objects.create(owner_session=self.other_client.session.session_key, title="Keep outsider")
        foreign_message = Message.objects.create(conversation=foreign, role="user", body="Keep outsider history")
        response = self.client.post(payload["clear_url"])
        self.assertRedirects(response, reverse("chatbot:index"))
        self.assertFalse(Conversation.objects.filter(pk=payload["conversation_id"]).exists())
        self.assertFalse(Message.objects.filter(conversation_id=payload["conversation_id"]).exists())
        self.assertTrue(Message.objects.filter(pk=foreign_message.pk).exists())

    def test_real_local_chat_works_without_network(self):
        from chatbot.services import answer_question

        self.answer_mock.side_effect = answer_question
        response = self.send(message="ধানের জমিতে সেচ কীভাবে দেব?")
        self.assertEqual(response.status_code, 200)
        reply = response.json()["assistant"]
        self.assertEqual(reply["mode"], "local")
        self.assertRegex(reply["body"], r"[\u0980-\u09ff]")
        self.assertTrue(reply["sources"])
        self.assertEqual(Message.objects.get(role="assistant").mode, "local")
        self.network_mock.assert_not_called()

    @override_settings(OPENAI_API_KEY="legacy-key-must-stay-unused", CHATBOT_AI_ENABLED=True)
    def test_old_api_settings_cannot_change_chat_from_local_mode(self):
        from chatbot.services import answer_question

        self.answer_mock.side_effect = answer_question
        response = self.send(message="Where can I get a soil test?")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["assistant"]["mode"], "local")
        self.assertNotIn("legacy-key-must-stay-unused", response.content.decode("utf-8"))
        page = self.client.get(payload["conversation_url"])
        self.assertEqual(page.context["chat_mode"], "local")
        self.assertEqual(Message.objects.get(role="assistant").mode, "local")
        self.network_mock.assert_not_called()

    def test_real_local_conversation_answers_a_crop_followup_in_english(self):
        from chatbot.services import answer_question

        self.answer_mock.side_effect = answer_question
        self.client.post(reverse("core:language"), {"language": "en", "next": reverse("chatbot:index")})
        first = self.send(message="How do I irrigate rice?").json()
        response = self.send(conversation=first["conversation_id"], message="More details please")
        self.assertEqual(response.status_code, 200)
        reply = response.json()["assistant"]
        self.assertEqual(reply["mode"], "local")
        self.assertIn("rice", reply["body"].lower())
        self.assertEqual(Conversation.objects.get(pk=first["conversation_id"]).messages.count(), 4)
        self.network_mock.assert_not_called()

    def test_real_local_nasa_answer_reads_only_saved_shared_analysis(self):
        from chatbot.services import answer_question

        self.answer_mock.side_effect = answer_question
        self.saved_analysis()
        response = self.send(message="আমার নাসার জলবায়ু তথ্য দেখাও", farm=self.farm.pk, include_farm="on")
        self.assertEqual(response.status_code, 200)
        reply = response.json()["assistant"]
        self.assertEqual(reply["mode"], "local")
        self.assertIn("জানুয়ারি ২০০১", reply["body"])
        self.assertIn("নাসা", reply["body"])
        self.assertNotIn("latitude", str(reply))
        self.assertTrue(reply["sources"])
        self.network_mock.assert_not_called()
