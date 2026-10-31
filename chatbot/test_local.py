"""Offline behavior checks for the bundled conversational assistant."""
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import translation

from .local import local_answer


def turn(text, role="user"):
    return {"role": role, "content": text}


class LocalChatTests(SimpleTestCase):
    def setUp(self):
        self.network = patch("requests.sessions.Session.request", side_effect=AssertionError("Local chat must not use the network"))
        self.request = self.network.start()
        self.addCleanup(self.network.stop)

    def test_common_topics_and_languages_have_local_answers_without_network(self):
        for question, topic in (
            ("How do I irrigate rice?", "irrigation"),
            ("টমেটোর পাতায় দাগ", "disease"),
            ("dhan er poka", "pests"),
            ("mati porikkha kothay korbo", "soil"),
            ("আলুতে সার কত দেব", "fertilizer"),
            ("পাট কখন বপন করব", "sowing"),
            ("How do I make compost?", "compost"),
            ("গম সংরক্ষণ", "storage"),
        ):
            with self.subTest(question=question):
                for language in ("bn", "en"):
                    answer = local_answer(question, language=language)
                    self.assertEqual(answer["mode"], "local")
                    self.assertEqual(answer["topic"], topic)
                    self.assertTrue(answer["text"])
                    self.assertTrue(answer["sources"])
        self.request.assert_not_called()

    def test_every_visible_quick_question_has_the_right_topic_in_both_languages(self):
        prompts = (
            ("Why are my rice leaves turning yellow?", "disease"),
            ("When should I water my vegetables?", "irrigation"),
            ("How can I improve my soil?", "soil"),
            ("What can I plant after rice?", "rotation"),
            ("Where can I find the latest weather warning?", "weather"),
            ("How do I use my farm’s NASA information?", "nasa"),
        )
        for lang in ("bn", "en"):
            with translation.override(lang):
                for english, expected in prompts:
                    question = translation.gettext(english)
                    with self.subTest(language=lang, question=question):
                        if lang == "bn":
                            self.assertNotEqual(question, english)
                        answer = local_answer(question, language=lang)
                        self.assertEqual(answer["topic"], expected)
                        self.assertTrue(answer["sources"])
                        if expected == "weather":
                            self.assertNotIn("cannot confirm whether it will rain", answer["text"])
                            self.assertNotIn("বৃষ্টি হবে কি না", answer["text"])

    def test_pulse_name_alone_is_crop_care_and_explicit_rotation_is_rotation(self):
        self.assertEqual(local_answer("lentil", language="en")["topic"], "care")
        self.assertEqual(local_answer("What can I grow after rice?", language="en")["topic"], "rotation")
        self.assertEqual(local_answer("ধানের পরে কোন ফসল লাগাব?")["topic"], "rotation")

    def test_short_english_followup_keeps_rice_and_irrigation(self):
        history = [turn("How do I irrigate rice?"), turn("Untrusted assistant text", "assistant")]
        answer = local_answer("More details please", history=history, language="en")
        self.assertEqual(answer["topic"], "irrigation")
        self.assertIn("Crop: rice", answer["text"])
        self.assertIn("water-level monitoring", answer["text"])

    def test_bangla_crop_district_and_age_followups_complete_requested_details(self):
        history = [turn("সেচ কীভাবে দেব?"), turn("কোন ফসল?", "assistant"), turn("ধান"), turn("বয়স?", "assistant")]
        answer = local_answer("রাজশাহী, ৪০ দিনের", history=history)
        self.assertEqual(answer["topic"], "irrigation")
        self.assertIn("ফসল: ধান", answer["text"])
        self.assertIn("জেলা: রাজশাহী", answer["text"])
        self.assertIn("৪০ দিন", answer["text"])
        self.assertIn("কী কাজ করতে চান", answer["text"])

    def test_explicit_new_topic_does_not_inherit_old_crop_or_district(self):
        answer = local_answer("How do I make compost?", history=[turn("How do I irrigate rice in Dhaka?")], language="en")
        self.assertEqual(answer["topic"], "compost")
        self.assertNotIn("Crop: rice", answer["text"])
        self.assertNotIn("District: Dhaka", answer["text"])

    def test_unrelated_question_with_district_does_not_inherit_crop_topic(self):
        answer = local_answer("Why is the sky blue in Dhaka?", history=[turn("Rice irrigation")], language="en")
        self.assertEqual(answer["topic"], "fallback")
        self.assertNotIn("Crop: rice", answer["text"])

    def test_short_explicit_care_topic_keeps_previous_crop(self):
        for text in ("irrigation?", "সেচ?"):
            with self.subTest(text=text):
                answer = local_answer(text, history=[turn("rice cultivation")], language="en")
                self.assertEqual(answer["topic"], "irrigation")
                self.assertIn("Crop: rice", answer["text"])

    def test_full_new_crop_care_question_does_not_inherit_irrigation(self):
        answer = local_answer("Tell me about tomato cultivation", history=[turn("Rice irrigation")], language="en")
        self.assertEqual(answer["topic"], "care")
        self.assertIn("Crop: tomato", answer["text"])
        self.assertNotIn("water-level monitoring", answer["text"])

    def test_reset_stops_older_topic_from_returning(self):
        history = [turn("Rice irrigation"), turn("start over")]
        answer = local_answer("More details please", history=history, language="en")
        self.assertEqual(answer["topic"], "fallback")
        self.assertNotIn("rice", answer["text"])

    def test_assistant_system_and_older_messages_cannot_supply_context(self):
        cases = (
            [turn("rice irrigation", "assistant")],
            [turn("rice irrigation", "system")],
            [turn("rice irrigation")] + [turn("unrelated", "assistant")] * 8,
        )
        for history in cases:
            with self.subTest(history=history):
                answer = local_answer("when?", history=history, language="en")
                self.assertEqual(answer["topic"], "fallback")

    def test_shared_farm_single_crop_is_used_but_multiple_crops_are_not_guessed(self):
        context = {"farm": {"crops": ["Boro rice", "Aman rice"]}}
        answer = local_answer("How do I irrigate?", farm_context=context, language="en")
        self.assertIn("Crop: rice", answer["text"])
        context["farm"]["crops"].append("Tomato")
        answer = local_answer("How do I irrigate?", farm_context=context, language="en")
        self.assertNotIn("Crop: rice", answer["text"])
        self.assertIn("Which crop", answer["text"])

    def test_unshared_farm_is_not_inferred(self):
        answer = local_answer("How should I water my crop?", language="en")
        self.assertNotIn("Crop:", answer["text"])
        self.assertIn("Which crop", answer["text"])

    def test_nonrice_irrigation_does_not_recommend_rice_awd(self):
        answer = local_answer("How do I irrigate tomatoes?", language="en")
        self.assertIn("Crop: tomato", answer["text"])
        self.assertNotIn("wetting and drying", answer["text"])

    def test_typo_and_banglish_are_recognised(self):
        self.assertEqual(local_answer("rice irrgation", language="en")["topic"], "irrigation")
        self.assertEqual(local_answer("pani kokhon dibo dhan e")["topic"], "irrigation")

    def test_each_supported_crop_has_targeted_clarifying_questions(self):
        for crop in ("rice", "potato", "tomato", "wheat", "maize", "jute", "lentil"):
            with self.subTest(crop=crop):
                answer = local_answer(f"{crop} cultivation", language="en")
                self.assertEqual(answer["topic"], "care")
                self.assertIn("Crop:", answer["text"])
                self.assertIn("district", answer["text"].lower())

    def test_greeting_thanks_and_identity_are_local_in_selected_language(self):
        for question, topic in (("Hello", "greeting"), ("ধন্যবাদ", "thanks"), ("Who are you?", "identity")):
            bn = local_answer(question, language="bn")
            en = local_answer(question, language="en")
            self.assertEqual(bn["topic"], topic)
            self.assertEqual(en["topic"], topic)
            self.assertRegex(bn["text"], r"[\u0980-\u09ff]")
            self.assertNotRegex(en["text"], r"[\u0980-\u09ff]")

    def test_unknown_question_has_clear_local_scope_without_inventing_answer(self):
        answer = local_answer("Explain quantum entanglement", language="en")
        self.assertEqual(answer["topic"], "fallback")
        self.assertIn("local farming library", answer["text"])
        self.assertNotIn("quantum", answer["text"])

    def test_live_weather_and_prices_are_not_fabricated(self):
        for question, topic in (("Will it rain tomorrow in Dhaka?", "weather"), ("What is today's rice market price?", "prices")):
            with self.subTest(question=question):
                answer = local_answer(question, language="en")
                self.assertEqual(answer["topic"], topic)
                self.assertIn("does not retrieve", answer["text"])
                self.assertTrue(all("?" not in item["url"] for item in answer["sources"]))
        self.request.assert_not_called()

    def test_acre_hectare_calculator_uses_bengali_digits_and_strict_input(self):
        bn = local_answer("৩ একর কত হেক্টর?")
        en = local_answer("convert 3 acres to hectares", language="en")
        self.assertEqual(bn["topic"], "conversion")
        self.assertIn("১.২১৪১", bn["text"])
        self.assertIn("1.2141", en["text"])
        self.assertEqual(local_answer("1 hectare to acres", language="en")["topic"], "conversion")
        self.assertNotEqual(local_answer("__import__('os') hectares to acres")["topic"], "conversion")
        self.assertNotEqual(local_answer("-3 acres to hectares")["topic"], "conversion")

    def test_malformed_and_large_history_are_bounded_and_safe(self):
        answer = local_answer(None, history={"role": "user"}, farm_context={"farm": {"crops": "rice"}})
        self.assertEqual(answer["mode"], "local")
        answer = local_answer("A" * 2000 + " rice irrigation", history=[None, {"role": "user", "content": {"private": "rice"}}], language="en")
        self.assertEqual(answer["topic"], "fallback")
