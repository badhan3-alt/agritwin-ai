"""Local-first Django settings. Production options are environment controlled."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from core.security import require_secret_key, validate_public_environment

BASE_DIR = Path(__file__).resolve().parent.parent

# Read simple KEY=value settings without requiring an additional dependency.
env_path = BASE_DIR / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

def env_bool(key, default=False):
    return os.environ.get(key, str(default)).lower() in {"true", "1", "yes"}

DEBUG = env_bool("DJANGO_DEBUG", False)
validate_public_environment(os.environ)
SECRET_KEY = require_secret_key(os.environ)
ALLOWED_HOSTS = [v.strip() for v in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if v.strip()]
CSRF_TRUSTED_ORIGINS = [v.strip() for v in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if v.strip()]
if not DEBUG and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured("Set explicit DJANGO_ALLOWED_HOSTS for production; wildcard hosts are not allowed.")
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "core", "farms", "climate", "rotations", "simulator", "reports", "chatbot",
    "accounts", "boundaries", "notebook", "weather",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "core.middleware.FarmerLanguageMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.PrivateWorkspaceMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "agritwin.urls"
CSRF_FAILURE_VIEW = "core.error_views.csrf_failure"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "core.context_processors.navigation",
    ]},
}]
WSGI_APPLICATION = "agritwin.wsgi.application"
ASGI_APPLICATION = "agritwin.asgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("DJANGO_DATABASE_PATH", str(BASE_DIR / "db.sqlite3"))}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "bn"
LANGUAGES = [("bn", "বাংলা"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = BASE_DIR / "media"
# Photos are deliberately served through notebook's ownership-checked endpoint.
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "farms:list"
LOGOUT_REDIRECT_URL = "core:home"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0" if DEBUG else "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = "DENY"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "agritwin-climate", "TIMEOUT": 3600}}
LOGGING = {"version": 1, "disable_existing_loggers": False, "handlers": {"console": {"class": "logging.StreamHandler"}}, "loggers": {"agritwin": {"handlers": ["console"], "level": "INFO"}}}

# Farmer chat uses the bundled local knowledge library without a provider.
CHATBOT_MESSAGES_PER_MINUTE = 12
CHATBOT_MAX_MESSAGES = 80
