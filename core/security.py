"""Server configuration guards. Error messages never include secret values."""
import base64
import json
import re

from django.core.exceptions import ImproperlyConfigured


PUBLIC_PREFIXES = ("VITE_", "NEXT_PUBLIC_", "PUBLIC_", "REACT_APP_", "NUXT_PUBLIC_", "EXPO_PUBLIC_")
_PRIVILEGED_NAME = re.compile(r"SERVICE_?ROLE|ADMIN_?(?:SECRET|KEY|TOKEN|PASSWORD)|(?:SECRET|PRIVATE)_?KEY|(?:^|_)SECRET(?:_|$)|JWT_?SECRET|DATABASE_?PASSWORD")


def is_strong_secret_key(value):
    if not isinstance(value, str) or len(value) < 50 or len(set(value)) < 5:
        return False
    normalized = value.lower()
    return not any(marker in normalized for marker in ("django-insecure-", "replace-this", "changeme", "change-me", "your-secret", "example-secret", "development-only"))


def require_secret_key(environ):
    key = environ.get("DJANGO_SECRET_KEY", "")
    if not is_strong_secret_key(key):
        raise ImproperlyConfigured(
            "Set DJANGO_SECRET_KEY to a private random value of at least 50 characters. "
            "For local setup, run: python scripts/setup_env.py"
        )
    return key


def _is_service_role_jwt(value):
    # Classification only, never token verification or an authorization decision.
    if not isinstance(value, str) or len(value) > 16384:
        return False
    parts = value.split(".")
    if len(parts) != 3:
        return False
    try:
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    except (ValueError, TypeError, UnicodeDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("role") == "service_role"


def validate_public_environment(environ):
    unsafe = []
    for name, value in environ.items():
        upper_name = name.upper()
        if not upper_name.startswith(PUBLIC_PREFIXES) or not value:
            continue
        tokens = set(upper_name.split("_"))
        admin_credential = "ADMIN" in tokens and bool(tokens & {"SECRET", "KEY", "TOKEN", "PASSWORD"})
        private_pem = value.startswith(("-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----", "-----BEGIN EC PRIVATE KEY-----"))
        if _PRIVILEGED_NAME.search(upper_name) or admin_credential or value.startswith("sb_secret_") or private_pem or _is_service_role_jwt(value):
            unsafe.append(name)
    if unsafe:
        raise ImproperlyConfigured(
            "Privileged credentials must use server-only environment names. "
            "Remove these browser-public variables: " + ", ".join(sorted(unsafe))
        )
