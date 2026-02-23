from .base import *  # noqa
from decouple import config

DEBUG = False

if SECRET_KEY == "unsafe-dev-secret-key":
    raise RuntimeError("Defina DJANGO_SECRET_KEY em produção.")
if ALLOWED_HOSTS == ["127.0.0.1", "localhost"]:
    raise RuntimeError("Defina DJANGO_ALLOWED_HOSTS em produção.")
if not CSRF_TRUSTED_ORIGINS:
    raise RuntimeError("Defina CSRF_TRUSTED_ORIGINS em produção.")

# Reforços comuns em produção (ajuste conforme infra)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 dias
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
CSRF_COOKIE_HTTPONLY = True
SECURE_REFERRER_POLICY = "same-origin"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
