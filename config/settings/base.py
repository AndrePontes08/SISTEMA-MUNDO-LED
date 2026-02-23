from __future__ import annotations

from pathlib import Path

from decouple import config

from config.db import get_database_config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("DJANGO_SECRET_KEY", default="unsafe-dev-secret-key")
DEBUG = config("DJANGO_DEBUG", default=False, cast=bool)

ALLOWED_HOSTS = [
    h.strip() for h in config("DJANGO_ALLOWED_HOSTS", default="127.0.0.1,localhost").split(",") if h.strip()
]

DJANGO_ENV = config("DJANGO_ENV", default="dev").lower().strip()

# Apps
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

LOCAL_APPS = [
    "core",
    # Apps do ERP
    "compras",
    "estoque",
    "contas",
    "boletos",
    "vendas",
    "relatorios",
    "financeiro",
    "importadores",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
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

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "core" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.currency_formatter",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = get_database_config(BASE_DIR)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Recife"
USE_I18N = True
USE_TZ = True

# Static/Media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / config("STATIC_ROOT", default="staticfiles")

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / config("MEDIA_ROOT", default="media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Auth
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Mensagens
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# PaginaÃ§Ã£o padrÃ£o (20 / 50 / 100)
PAGINATION_DEFAULT_SIZE = 20
PAGINATION_ALLOWED_SIZES = (20, 40, 60)

# SeguranÃ§a bÃ¡sica (ajustada em prod.py)
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in config("CSRF_TRUSTED_ORIGINS", default="").split(",") if o.strip()
]

SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=False, cast=bool)


