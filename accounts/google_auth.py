"""Google Identity Services sign-in; Google verifies tokens, OrgFlow binds sessions.

No account is linked by email alone. Existing local-account linking is a separate,
authenticated workflow and is deliberately not offered by this login endpoint.
"""

import secrets
import time
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from .forms import EmailLoginForm
from .models import GoogleIdentity

NONCE_SESSION_KEY = "google_signin_nonces"
NONCE_TTL_SECONDS = 300
MAX_NONCES = 5
VERIFY_TIMEOUT_SECONDS = 5


class GoogleSignInError(ValueError):
    """A safe explanation suitable for the sign-in page."""


class BoundedGoogleRequest(GoogleRequest):
    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = VERIFY_TIMEOUT_SECONDS
        return super().__call__(*args, **kwargs)


def _live_nonces(request):
    now = time.time()
    return [
        entry
        for entry in request.session.get(NONCE_SESSION_KEY, [])
        if isinstance(entry, dict)
        and isinstance(entry.get("token"), str)
        and isinstance(entry.get("issued"), (int, float))
        and 0 <= now - entry["issued"] <= NONCE_TTL_SECONDS
    ][-MAX_NONCES:]


def google_login_context(request):
    """Issue a fresh, short-lived nonce, retaining at most five open login tabs."""
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        return {"google_enabled": False}
    nonce = secrets.token_urlsafe(32)
    entries = _live_nonces(request)
    entries.append({"token": nonce, "issued": time.time()})
    request.session[NONCE_SESSION_KEY] = entries[-MAX_NONCES:]
    return {"google_enabled": True, "google_client_id": client_id, "google_nonce": nonce}


def _consume_nonce(request, claimed_nonce):
    if not isinstance(claimed_nonce, str) or not claimed_nonce.isascii():
        return False
    entries = _live_nonces(request)
    matched = False
    retained = []
    for entry in entries:
        if secrets.compare_digest(entry["token"], claimed_nonce):
            matched = True
        else:
            retained.append(entry)
    request.session[NONCE_SESSION_KEY] = retained
    return matched


def verify_google_credential(credential):
    """Use Google's library for signature, audience, issuer and expiry validation."""
    client_id = getattr(settings, "GOOGLE_CLIENT_ID", "").strip()
    if not client_id:
        raise GoogleSignInError("Google sign-in is currently unavailable.")
    if not isinstance(credential, str) or not credential or len(credential) > 16384:
        raise GoogleSignInError("Google did not provide a valid sign-in credential.")
    try:
        return id_token.verify_oauth2_token(
            credential, BoundedGoogleRequest(), audience=client_id
        )
    except (ValueError, TypeError, KeyError, GoogleAuthError) as error:
        # Malformed untrusted JWT fields can also raise structural errors in
        # google-auth (for example, an unhashable algorithm or key identifier).
        raise GoogleSignInError("Google sign-in could not be verified. Please try again.") from error


def _identity_user(claims):
    subject = claims.get("sub")
    email = claims.get("email")
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 255:
        raise GoogleSignInError("Google did not provide a valid account identifier.")
    if claims.get("email_verified") is not True or not isinstance(email, str):
        raise GoogleSignInError("Google sign-in requires a verified email address.")
    email = email.strip().lower()
    try:
        validate_email(email)
    except ValidationError as error:
        raise GoogleSignInError("Google did not provide a valid email address.") from error
    if len(email) > 254:
        raise GoogleSignInError("Google did not provide a valid email address.")

    identity = GoogleIdentity.objects.filter(subject=subject).select_related("user").first()
    if identity is not None:
        if not identity.user.is_active:
            raise GoogleSignInError("This account is inactive.")
        # The subject, not a mutable email address, identifies returning users.
        return identity.user

    User = get_user_model()
    collision = Q(email__iexact=email) | Q(username__iexact=email)
    if User.objects.filter(collision).exists():
        raise GoogleSignInError(
            "An account already uses this email. Sign in with that account; "
            "Google accounts are not linked automatically."
        )
    try:
        user = User.objects.create_user(
            username=f"google_{uuid4().hex}", email=email, password=None
        )
    except IntegrityError as error:
        raise GoogleSignInError("This account could not be created. Please try again.") from error
    # MongoDB's standalone development service cannot provide a multi-document
    # transaction. Recheck observed collisions and clean up failed provisioning;
    # a database-wide canonical-email constraint remains a separate improvement.
    if User.objects.filter(collision).exclude(pk=user.pk).exists():
        user.delete()
        raise GoogleSignInError("An account already uses this email. Sign in with that account.")
    try:
        GoogleIdentity.objects.create(subject=subject, user=user)
    except IntegrityError as error:
        user.delete()
        # A simultaneous sign-in with the same subject may have completed first.
        identity = GoogleIdentity.objects.filter(subject=subject).select_related("user").first()
        if identity is None:
            raise GoogleSignInError("Google sign-in could not be completed. Please try again.") from error
        if not identity.user.is_active:
            raise GoogleSignInError("This account is inactive.")
        return identity.user
    return user


def _safe_next(request):
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return reverse("core:dashboard")


def _login_error(request, message, status=400):
    messages.error(request, message)
    context = {
        "form": EmailLoginForm(request=request),
        "next": _safe_next(request),
        **google_login_context(request),
    }
    response = render(request, "accounts/login.html", context, status=status)
    if context.get("google_enabled"):
        response["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    return response


@require_POST
@csrf_protect
def google_signin(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    if not getattr(settings, "GOOGLE_CLIENT_ID", "").strip():
        return _login_error(request, "Google sign-in is currently unavailable.", status=503)
    try:
        claims = verify_google_credential(request.POST.get("credential", ""))
        if not isinstance(claims, dict) or not _consume_nonce(request, claims.get("nonce")):
            raise GoogleSignInError("This Google sign-in has expired. Please try again.")
        user = _identity_user(claims)
    except GoogleSignInError as error:
        return _login_error(request, str(error))
    target = _safe_next(request)
    request.session.pop(NONCE_SESSION_KEY, None)
    login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
    return redirect(target)
