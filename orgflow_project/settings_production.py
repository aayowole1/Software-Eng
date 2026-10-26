"""Explicit production configuration; TLS termination remains an operator task.

Import this module with DJANGO_SETTINGS_MODULE. Development .env files are not
loaded: inject environment variables through the deployment platform instead.
"""

import ipaddress
import os
import re
from copy import deepcopy
from email.utils import parseaddr
from urllib.parse import urlsplit

# settings.py imports python-dotenv. Disable its local-file loading before import.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from .settings import *  # noqa: F403,E402
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be explicitly configured for production.")
    return value


def flag(name, default=False):
    value = os.environ.get(name, str(default)).strip().lower()
    if value not in {"true", "false"}:
        raise ImproperlyConfigured(f"{name} must be true or false.")
    return value == "true"


def positive_integer(name, default, maximum):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        raise ImproperlyConfigured(f"{name} must be an integer.") from None
    if not 1 <= value <= maximum:
        raise ImproperlyConfigured(f"{name} is outside its permitted range.")
    return value


def explicit_host(host):
    if not host or "*" in host or host.startswith("."):
        return False
    try:
        ipaddress.ip_address(host.strip("[]"))
        return ":" not in host or (host.startswith("[") and host.endswith("]"))
    except ValueError:
        return len(host) <= 253 and all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.split(".")
        )


DEBUG = False
SECRET_KEY = required("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.lower().startswith(
    ("django-insecure-", "change-me", "replace-me", "example-")
):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong, unique production secret.")
SECRET_KEY_FALLBACKS = []

ALLOWED_HOSTS = list(dict.fromkeys(host.strip() for host in required("DJANGO_ALLOWED_HOSTS").split(",")))
if not all(explicit_host(host) for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain explicit hostnames/IPs without wildcard, scheme or port.")

CSRF_TRUSTED_ORIGINS = [
    value.strip() for value in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if value.strip()
]
for origin in CSRF_TRUSTED_ORIGINS:
    try:
        parsed = urlsplit(origin)
        valid_port = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS contains an invalid HTTPS origin.") from None
    if (
        parsed.scheme != "https" or not parsed.hostname or not explicit_host(
            f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        ) or not valid_port or parsed.username or parsed.password or parsed.path
        or parsed.query or parsed.fragment
    ):
        raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS requires exact HTTPS origins without wildcard or path.")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = positive_integer("DJANGO_HSTS_SECONDS", 3600, 63072000)
# An operator must confirm ownership/HTTPS coverage before widening HSTS policy.
SECURE_HSTS_INCLUDE_SUBDOMAINS = flag("DJANGO_HSTS_INCLUDE_SUBDOMAINS")
SECURE_HSTS_PRELOAD = flag("DJANGO_HSTS_PRELOAD")
if SECURE_HSTS_PRELOAD and not SECURE_HSTS_INCLUDE_SUBDOMAINS:
    raise ImproperlyConfigured("HSTS preload requires explicit subdomain HTTPS policy.")

# Enable only when the sole trusted TLS proxy strips client-supplied forwarding
# headers and overwrites this value. Loopback publishing is not a TLS proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if flag("DJANGO_TRUST_PROXY_HEADERS") else None
USE_X_FORWARDED_HOST = False
SECURE_REDIRECT_EXEMPT = [r"^health/$", r"^health/ready/$"]

DATABASES = deepcopy(DATABASES)  # noqa: F405
DATABASES["default"]["HOST"] = required("MONGODB_URI")
DATABASES["default"]["NAME"] = required("MONGODB_NAME")
DATABASES["default"]["OPTIONS"] = {
    **DATABASES["default"].get("OPTIONS", {}),
    "serverSelectionTimeoutMS": 2000,
    "connectTimeoutMS": 2000,
    "socketTimeoutMS": 10000,
}

STATIC_ROOT = os.environ.get("DJANGO_STATIC_ROOT", "/var/lib/orgflow/static")
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
MIDDLEWARE.insert(MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_USE_FINDERS = False
WHITENOISE_AUTOREFRESH = False

DJANGO_EMAIL_POLICY = os.environ.get("DJANGO_EMAIL_POLICY", "smtp").strip().lower()
if DJANGO_EMAIL_POLICY == "disabled":
    # Explicit operator policy: no password reset email is delivered in this mode.
    EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
elif DJANGO_EMAIL_POLICY == "smtp":
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = required("EMAIL_HOST")
    DEFAULT_FROM_EMAIL = required("DEFAULT_FROM_EMAIL")
    try:
        validate_email(parseaddr(DEFAULT_FROM_EMAIL)[1])
    except ValidationError:
        raise ImproperlyConfigured("DEFAULT_FROM_EMAIL must contain a valid sender address.") from None
    if "\r" in DEFAULT_FROM_EMAIL or "\n" in DEFAULT_FROM_EMAIL:
        raise ImproperlyConfigured("DEFAULT_FROM_EMAIL must be a single sender address.")
    EMAIL_USE_TLS = flag("EMAIL_USE_TLS", True)
    EMAIL_USE_SSL = flag("EMAIL_USE_SSL")
    if EMAIL_USE_TLS and EMAIL_USE_SSL:
        raise ImproperlyConfigured("Choose either EMAIL_USE_TLS or EMAIL_USE_SSL.")
    if not (EMAIL_USE_TLS or EMAIL_USE_SSL) and not flag("DJANGO_ALLOW_INSECURE_SMTP"):
        raise ImproperlyConfigured("SMTP requires TLS/SSL; plaintext staging needs DJANGO_ALLOW_INSECURE_SMTP=true.")
    EMAIL_PORT = positive_integer("EMAIL_PORT", 465 if EMAIL_USE_SSL else 587, 65535)
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    if bool(EMAIL_HOST_USER) != bool(EMAIL_HOST_PASSWORD):
        raise ImproperlyConfigured("SMTP credentials must be configured as a username/password pair.")
    EMAIL_TIMEOUT = positive_integer("EMAIL_TIMEOUT", 10, 120)
else:
    raise ImproperlyConfigured("DJANGO_EMAIL_POLICY must be smtp or explicitly disabled.")
