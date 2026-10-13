"""
Settings for the student portal.

Everything that changes between your laptop and Render is read from
environment variables, so the same code runs in both places. For local work,
copy .env.example to .env and the values below are picked up automatically.
"""

import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _load_env_file(path):
    """Tiny .env reader so local development needs no extra package."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file(BASE_DIR / ".env")


def env(name, default=""):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def env_list(name):
    return [item.strip() for item in env(name).split(",") if item.strip()]


def parse_database_url(url):
    """postgres://user:pass@host:5432/dbname  ->  Django DATABASES entry."""
    parsed = urlparse(url)
    scheme = parsed.scheme.split("+")[0]
    if scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured(
            f"DATABASE_URL must start with postgres:// (got '{parsed.scheme}://')."
        )
    host = parsed.hostname or ""
    options = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
    # Render's *external* connection string lives on *.render.com and needs TLS.
    if host.endswith(".render.com") and "sslmode" not in options:
        options["sslmode"] = "require"
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed.path.lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": host,
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": 600,
        "CONN_HEALTH_CHECKS": True,
    }
    if options:
        config["OPTIONS"] = options
    return config


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == "test"
DEBUG = env_bool("DEBUG", False)
PRODUCTION = not DEBUG and not RUNNING_TESTS

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG or RUNNING_TESTS:
        SECRET_KEY = "insecure-development-key-never-use-in-production"
    else:
        raise ImproperlyConfigured(
            "SECRET_KEY is not set. Locally, copy .env.example to .env. "
            "On Render, the blueprint generates one for you."
        )

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
RENDER_HOST = env("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)
if DEBUG or RUNNING_TESTS:
    ALLOWED_HOSTS += ["localhost", "127.0.0.1", "[::1]"]

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if RENDER_HOST:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOST}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
]

MIDDLEWARE = [
    "accounts.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.site",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Database: Postgres on Render, SQLite on your laptop
# ---------------------------------------------------------------------------

DATABASE_URL = env("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {"default": parse_database_url(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailOrStudentIdBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

if RUNNING_TESTS:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

SESSION_COOKIE_AGE = 60 * 60 * 24 * 14          # default: 14 days
SESSION_COOKIE_SAMESITE = "Lax"
REMEMBER_ME_AGE = 60 * 60 * 24 * 30             # "keep me signed in": 30 days
PASSWORD_RESET_TIMEOUT = 60 * 60                # reset links last 1 hour


# ---------------------------------------------------------------------------
# Portal behaviour
# ---------------------------------------------------------------------------

SITE_NAME = env("SITE_NAME", "Student Portal")

# Lock a sign-in name after this many wrong passwords inside the window.
LOGIN_MAX_ATTEMPTS = env_int("LOGIN_MAX_ATTEMPTS", 5)
LOGIN_LOCKOUT_MINUTES = env_int("LOGIN_LOCKOUT_MINUTES", 15)

# False: people can use the portal straight after registering.
# True : they must click the emailed link first (needs real SMTP, see README).
REQUIRE_EMAIL_VERIFICATION = env_bool("REQUIRE_EMAIL_VERIFICATION", False)
EMAIL_VERIFY_MAX_AGE_DAYS = env_int("EMAIL_VERIFY_MAX_AGE_DAYS", 3)

# Public-demo helpers. Turn DEMO_MODE off for a real deployment.
DEMO_MODE = env_bool("DEMO_MODE", False)
SEED_DEMO = env_bool("SEED_DEMO", False)
DEMO_ACCOUNT_EMAIL = env("DEMO_ACCOUNT_EMAIL", "demo@student.test")
DEMO_ACCOUNT_PASSWORD = env("DEMO_ACCOUNT_PASSWORD", "Demo-Pass-2026!")


# ---------------------------------------------------------------------------
# Email: console (visible in Render logs) until you configure SMTP
# ---------------------------------------------------------------------------

EMAIL_HOST = env("EMAIL_HOST")
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = env_int("EMAIL_PORT", 587)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
    EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", f"{SITE_NAME} <no-reply@localhost>")


# ---------------------------------------------------------------------------
# Static files (served by WhiteNoise, no separate web server needed)
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if PRODUCTION
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}
WHITENOISE_MANIFEST_STRICT = False


# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Messages, security, logging
# ---------------------------------------------------------------------------

from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {
    message_constants.DEBUG: "info",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "error",
}

X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

if PRODUCTION:
    # Render terminates TLS and tells Django via this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Start small. Raise it once you are sure HTTPS works everywhere.
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 3600)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}
