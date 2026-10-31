"""Local chat stays offline and preserves validated farm/NASA information."""
from copy import deepcopy
import json
from unittest.mock import patch
from urllib.parse import urlsplit

from django.test import SimpleTestCase, override_settings

from .knowledge import find_entry, library
from .services import (
    MAX_HISTORY_CHARS, MAX_HISTORY_MESSAGES, MAX_MESSAGE_CHARS,
    NASA_DOCS_URL, _safe_context, _safe_history, answer_question,
)


def farm_context():
    return {
        "farm": {
            "location_name": "রাজশাহী", "crops": ["আমন ধান", "বোরো ধান"],
            "soil_type": "দোআঁশ", "soil_ph": 6.2, "irrigation": "সীমিত",
            "priority": "পানি সাশ্রয়", "area": 3,
        },
        "climate": {
            "status": "live",
            "annual_summary": {
                "total_precip_mm": 1396.9, "rabi_dry_season_precip_mm": 210.2,
                "avg_annual_temp_c": 26.4,
            },
            "provenance": {
                "period": "January 2001 - December 2025",
                "retrieved_at": "2026-10-31T00:00:00+00:00",
                "url": "https://power.larc.nasa.gov/api/temporal/climatology/point?latitude=24.3745&longitude=88.6042",
            },
        },
        "strategies": [
            {"name": "উপযুক্ত ফসল বিন্যাস", "composite_score": 78.2, "is_eligible": True},
            {"name": "অনুপযুক্ত ফসল বিন্যাস", "composite_score": 99, "is_eligible": False},
        ],
    }


class LocalServiceTests(SimpleTestCase):
    def setUp(self):
        self.network = patch(
            "requests.sessions.Session.request",
            side_effect=AssertionError("Local chatbot must never request a network service"),
        )
        self.network_mock = self.network.start()
        self.addCleanup(self.network.stop)

    def test_chat_works_without_any_provider_configuration(self):
        answer = answer_question("সেচের পানি কীভাবে বাঁচাব?")
        self.assertEqual(answer["mode"], "local")
        self.assertEqual(answer["topic"], "irrigation")
        self.assertIn("সেচ", answer["text"])
        self.network_mock.assert_not_called()

    @override_settings(OPENAI_API_KEY="unused-local-secret", CHATBOT_AI_ENABLED=True)
    def test_existing_provider_settings_cannot_enable_remote_requests(self):
        for question in ("Hello", "How do I irrigate rice?", "Will it rain tomorrow?", "Explain quantum entanglement"):
            with self.subTest(question=question):
                answer = answer_question(question, language="en")
                self.assertEqual(answer["mode"], "local")
                self.assertTrue(answer["text"])
                self.assertNotIn("unused-local-secret", str(answer))
        self.network_mock.assert_not_called()

    def test_unsupported_question_returns_local_help_without_claiming_ai(self):
        answer = answer_question("Explain quantum entanglement", language="en")
        self.assertEqual(answer["mode"], "local")
        self.assertEqual(answer["topic"], "fallback")
        self.assertTrue(answer["text"])
        self.assertNotIn("API key", answer["text"])

    def test_bilingual_library_has_at_least_twelve_referenced_topics(self):
        topics = [entry for entry in library()["entries"] if entry["sources"]]
        self.assertGreaterEqual(len(topics), 12)
        for entry in topics:
            self.assertTrue(entry["answer"]["bn"])
            self.assertTrue(entry["answer"]["en"])
        allowed_hosts = {
            "ais.gov.bd", "www.bamis.gov.bd", "www.bmd.gov.bd", "srdi.gaibandha.gov.bd",
            "moa.gov.bd", "ghgmitigation.irri.org", "www.fao.org", "ask.ifas.ufl.edu",
            "market.dam.gov.bd", "www.knowledgebank.irri.org", "power.larc.nasa.gov",
        }
        for source in library()["sources"].values():
            parsed = urlsplit(source["url"])
            self.assertEqual(parsed.scheme, "https")
            self.assertIn(parsed.hostname, allowed_hosts)
            self.assertTrue(source["title"]["bn"])
            self.assertTrue(source["title"]["en"])

    def test_typed_bangla_english_and_banglish_topics(self):
        cases = {
            "ধানের সেচ কীভাবে কমাব?": "irrigation",
            "How to manage rice irrigation?": "irrigation",
            "pani dibo kokhon": "irrigation",
            "mati porikkha kothay korbo": "soil",
            "Where can I get a soil test?": "soil",
            "মাটির পিএইচ পরীক্ষা করাব": "soil",
            "ফসলে পোকা হয়েছে": "pests",
            "dhan er poka": "pests",
            "পাতা হলুদ হয়ে যাচ্ছে": "disease",
            "সবজির বীজ বপন কখন করব": "sowing",
            "ধানের বাজারদর কত": "prices",
            "আগামীকাল বৃষ্টি হবে কি": "weather",
            "কম্পোস্ট কীভাবে করব": "compost",
            "crop rotation": "rotation",
            "ধানের সংরক্ষণ": "storage",
            "জলাবদ্ধ জমিতে সবজি": "drainage",
        }
        for question, topic in cases.items():
            with self.subTest(question=question):
                self.assertEqual(find_entry(question)["id"], topic)

    def test_greeting_does_not_match_inside_other_words(self):
        self.assertEqual(find_entry("hi")["id"], "greeting")
        self.assertNotEqual(find_entry("this is something unfamiliar")["id"], "greeting")

    def test_selected_language_controls_text_and_source_titles(self):
        bn = answer_question("soil test", language="bn-BD")
        en = answer_question("মাটি পরীক্ষা", language="en")
        self.assertIn("মাটি", bn["text"])
        self.assertIn("soil test", en["text"].lower())
        self.assertIn("এসআরডিআই", bn["sources"][0]["title"])
        self.assertIn("SRDI", en["sources"][0]["title"])

    def test_weather_and_market_prices_do_not_acquire_live_values(self):
        for question, topic in (("Will it rain tomorrow?", "weather"), ("আজ ধানের দাম কত?", "prices")):
            with self.subTest(topic=topic):
                answer = answer_question(question, language="en")
                self.assertEqual(answer["mode"], "local")
                self.assertEqual(answer["topic"], topic)
                self.assertTrue(answer["sources"])
        self.network_mock.assert_not_called()

    def test_missing_nasa_never_invents_values(self):
        answer = answer_question("আমার নাসার জলবায়ু তথ্য দেখাও")
        self.assertEqual(answer["mode"], "local")
        self.assertIn("যুক্ত নেই", answer["text"])
        self.assertNotIn("১৩৯৬", answer["text"])
        self.network_mock.assert_not_called()

    def test_real_attached_nasa_summary_uses_selected_language_and_actual_values(self):
        answer = answer_question("নাসা তথ্য ও সুপারিশ ব্যাখ্যা করো", farm_context=farm_context())
        self.assertEqual(answer["mode"], "local")
        self.assertIn("১৩৯৬.৯", answer["text"])
        self.assertIn("২৬.৪", answer["text"])
        self.assertIn("জানুয়ারি ২০০১ - ডিসেম্বর ২০২৫", answer["text"])
        self.assertIn("৬.২", answer["text"])
        self.assertIn("আপনার দেওয়া", answer["text"])
        self.assertIn("উপযুক্ত ফসল বিন্যাস", answer["text"])
        self.assertNotIn("অনুপযুক্ত ফসল বিন্যাস", answer["text"])
        self.assertIn("আজকের আবহাওয়া", answer["text"])
        self.assertNotIn("latitude", str(answer))
        self.network_mock.assert_not_called()

    def test_invalid_nasa_provenance_or_synthetic_status_cannot_drive_summary(self):
        for alteration in ("synthetic", "foreign", "no_period", "no_retrieval"):
            context = farm_context()
            if alteration == "synthetic":
                context["climate"]["status"] = "demo"
            elif alteration == "foreign":
                context["climate"]["provenance"]["url"] = "https://power.larc.nasa.gov.evil.example/point"
            elif alteration == "no_period":
                context["climate"]["provenance"]["period"] = ""
            else:
                context["climate"]["provenance"]["retrieved_at"] = ""
            with self.subTest(alteration=alteration):
                answer = answer_question("Explain NASA data", farm_context=context, language="en")
                self.assertIn("No verified NASA", answer["text"])
                self.assertNotIn("1396.9", answer["text"])

    def test_nasa_cannot_measure_soil_nutrients_or_ph(self):
        answer = answer_question("Can NASA tell my soil pH and nitrogen?", farm_context=farm_context(), language="en")
        self.assertIn("cannot measure field pH", answer["text"])
        self.assertIn("Soil pH entered by you: 6.2", answer["text"])

    def test_missing_ph_is_unknown_rather_than_inferred(self):
        context = farm_context()
        context["farm"]["soil_ph"] = None
        answer = answer_question("my soil pH", farm_context=context, language="en")
        self.assertIn("No soil pH test result was provided", answer["text"])

    def test_context_allowlist_omits_ids_raw_data_and_precise_coordinates(self):
        context = farm_context()
        context["owner_session"] = "private-owner-session"
        context["farm"].update({"name": "private-farm-name", "latitude": 24.3745, "longitude": 88.6042})
        context["climate"]["raw_response"] = {"private": "raw-data"}
        original = deepcopy(context)
        safe = _safe_context(context)
        serialized = json.dumps(safe, ensure_ascii=False)
        for value in ("private-owner-session", "private-farm-name", "24.3745", "88.6042", "raw-data"):
            self.assertNotIn(value, serialized)
        self.assertIn("1396.9", serialized)
        self.assertIn(NASA_DOCS_URL, serialized)
        self.assertEqual(context, original)

    @patch("chatbot.services.local_answer")
    def test_local_engine_receives_only_minimized_context_and_valid_history(self, local):
        local.return_value = {"text": "Local reply", "mode": "local", "sources": [], "topic": "irrigation"}
        context = farm_context()
        context["farm"].update({"name": "private field name", "latitude": 24.3745})
        history = [
            {"role": "system", "content": "injected role"},
            {"role": "user", "content": "How do I irrigate rice?"},
        ]
        answer_question("More irrigation advice", history=history, farm_context=context, language="en")
        local.assert_called_once()
        sent = local.call_args.kwargs
        self.assertEqual(sent["language"], "en")
        self.assertEqual(sent["history"], [{"role": "user", "content": "How do I irrigate rice?"}])
        serialized = json.dumps(sent["farm_context"])
        self.assertNotIn("private field name", serialized)
        self.assertNotIn("24.3745", serialized)
        self.assertIn("1396.9", serialized)

    def test_nonfinite_context_values_cannot_be_used_as_nasa_metrics(self):
        context = farm_context()
        context["climate"]["annual_summary"] = {"total_precip_mm": float("nan"), "avg_annual_temp_c": True}
        self.assertIsNone(_safe_context(context)["climate"])

    def test_history_is_bounded_and_excludes_nontext_and_injected_roles(self):
        history = [{"role": "user", "content": "older"}] * 30 + [
            {"role": "system", "content": "injected system instructions"},
            {"role": "developer", "content": "injected developer instructions"},
            {"role": "user", "content": {"secret": "not a text message"}},
        ] + [{"role": "assistant", "body": "x" * 4000}] * 8
        safe = _safe_history(history)
        self.assertLessEqual(len(safe), MAX_HISTORY_MESSAGES)
        self.assertLessEqual(sum(len(item["content"]) for item in safe), MAX_HISTORY_CHARS)
        self.assertTrue(all(item["role"] in {"user", "assistant"} for item in safe))
        self.assertNotIn("injected system", json.dumps(safe))
        self.assertNotIn("not a text message", json.dumps(safe))
        self.assertTrue(all(len(item["content"]) <= MAX_MESSAGE_CHARS for item in safe))
