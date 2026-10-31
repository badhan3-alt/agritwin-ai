"""Use Bangla by default and retain the farmer's explicit language choice."""
from django.conf import settings
from django.utils import translation
from django.utils.cache import patch_vary_headers

class FarmerLanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        chosen = request.session.get("language", settings.LANGUAGE_CODE)
        language = chosen if chosen in {"bn", "en"} else settings.LANGUAGE_CODE
        request.LANGUAGE_CODE = language
        with translation.override(language):
            response = self.get_response(request)
        response.setdefault("Content-Language", language)
        patch_vary_headers(response, ("Cookie",))
        return response
