"""Django settings for the web_barbecue project.

Independently deployed and configured, per the monorepo convention:
each app under apps/ (admin, pos, web_barbecue) is set up and run from
its own directory with its own .env.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = os.environ.get("DEBUG", "False") == "True"
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]

# Behind the Nginx reverse proxy (see deploy/), TLS is terminated at Nginx
# and the request forwarded to Gunicorn over plain HTTP with this header
# set, so Django knows to treat it as a secure request (redirects, cookies).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

# Shared secret admin/src/networking/web_sync_client.py authenticates with
# via the X-API-Key header on POST /api/products/sync/.
WEB_SYNC_API_KEY = os.environ["WEB_SYNC_API_KEY"]

TELEGRAM_ENABLED = os.environ.get("TELEGRAM_ENABLED", "false").lower() == "true"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_GROUP_CHAT_ID = os.environ.get("TELEGRAM_GROUP_CHAT_ID", "")

INSTALLED_APPS = [
    # Must be listed before django.contrib.staticfiles so `manage.py
    # runserver` serves ASGI (and therefore the /ws/admin/orders/
    # route) automatically in local dev, matching the daphne process
    # used in Docker (see deploy/entrypoint.sh).
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "products",
    "orders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "web_barbecue.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "web_barbecue.wsgi.application"
ASGI_APPLICATION = "web_barbecue.asgi.application"

# Redis-backed channel layer for the /ws/admin/orders/ consumer. Redis
# (not the in-memory layer) per the reconciled task-plan decision: this
# compose stack only ever runs one ASGI worker today, but Redis is the
# documented multi-worker-safe choice and keeps that door open without
# a later migration. docker-compose.yml/.env.docker.example set
# REDIS_URL explicitly; when it is unset (plain `pytest`/`manage.py
# test` with no .env, e.g. CI) this falls back to the in-memory layer
# so the test suite never needs a real Redis instance.
REDIS_URL = os.environ.get("REDIS_URL")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                # Keep the Redis socket timeout longer than channels_redis'
                # five-second blocking receive interval.
                "hosts": [
                    {
                        "address": REDIS_URL,
                        "socket_connect_timeout": 5,
                        "socket_timeout": 30,
                    }
                ],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        # Overridable so Docker can point it at a mounted volume
        # (deploy/: SQLITE_PATH=/app/data/db.sqlite3) that survives
        # container rebuilds; defaults to the repo-local file for
        # non-Docker development.
        "NAME": os.environ.get("SQLITE_PATH", str(BASE_DIR / "db.sqlite3")),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "hy"
TIME_ZONE = "Asia/Yerevan"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
