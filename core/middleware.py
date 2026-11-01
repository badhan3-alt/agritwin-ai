"""Use Bangla by default and retain the farmer's explicit language choice."""
from django.conf import settings
from django.utils import translation
from django.utils.cache import patch_cache_control, patch_vary_headers

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


class PrivateWorkspaceMiddleware:
    """Keep authenticated and farm-specific responses out of browser/shared caches."""
    PRIVATE_NAMESPACES = {"accounts", "farms", "boundaries", "notebook", "climate", "rotations", "simulator", "reports", "weather", "chatbot", "admin"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, "resolver_match", None)
        namespace = match.namespace.split(":", 1)[0] if match and match.namespace else ""
        if request.user.is_authenticated or namespace in self.PRIVATE_NAMESPACES:
            patch_cache_control(response, private=True, no_store=True)
        return response
