import os
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / "infrastructure" / ".env"

if not _ENV_PATH.exists() and not os.environ.get("SENTINEL_SKIP_ENV_CHECK"):
    raise ImproperlyConfigured(
        f"infrastructure/.env not found at {_ENV_PATH}.\n"
        f"Run `just env` from the repo root to generate it, then retry.\n"
        f"(Set SENTINEL_SKIP_ENV_CHECK=1 to bypass — e.g. in CI where env vars are injected directly.)"
    )

load_dotenv(dotenv_path=_ENV_PATH)

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key-change-in-production")

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.postgres",
    "api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "sentinel.urls"

WSGI_APPLICATION = "sentinel.wsgi.application"

# Database — reads DATABASE_URL (same env var as Express/Drizzle)
_db_url = os.environ.get("DATABASE_URL", "postgresql://sentinel_admin:password@localhost:5432/sentinel_world")
_parsed = urlparse(_db_url)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _parsed.path.lstrip("/"),
        "USER": _parsed.username or "sentinel_admin",
        "PASSWORD": _parsed.password or "",
        "HOST": _parsed.hostname or "localhost",
        "PORT": str(_parsed.port or 5432),
    }
}

# LiteLLM / OpenAI config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", None)
DM_MODEL = os.environ.get("DM_MODEL", "gpt-4o-mini")

# CORS — allow local Vite dev server
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173",
).split(",")

CORS_ALLOW_ALL_ORIGINS = DEBUG

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

USE_TZ = True
TIME_ZONE = "UTC"
