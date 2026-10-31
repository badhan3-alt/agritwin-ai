"""Check local farmer chat without credentials or an external service."""
from django.core.management.base import BaseCommand, CommandError

from chatbot.services import answer_question


class Command(BaseCommand):
    help = "Verify the bundled Bangla and English farmer chatbot locally."

    def handle(self, *args, **options):
        for language, question in (
            ("bn", "সেচের পানি কীভাবে বাঁচাব?"),
            ("en", "How can I save irrigation water?"),
        ):
            answer = answer_question(question, language=language)
            if (
                not isinstance(answer, dict) or answer.get("mode") != "local"
                or not isinstance(answer.get("text"), str) or not answer["text"].strip()
            ):
                raise CommandError("The local chatbot did not return a valid answer. Check the bundled knowledge files.")
        self.stdout.write(self.style.SUCCESS("Local chatbot verified in Bangla and English. No API key or internet connection is required."))
