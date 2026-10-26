"""Google Identity Services sign-in; Google verifies tokens, OrgFlow binds sessions.

No account is linked by email alone. Existing local-account linking is a separate,
authenticated workflow and is deliberately not offered by this login endpoint.
"""

import logging
import secrets
import time
from urllib.parse import urlsplit
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import DatabaseError, IntegrityError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

from membership.models import MembershipApplication, inactive_account_message

from .forms import EmailLoginForm, GoogleApplicationForm
from .models import GoogleIdentity, Profile
from .provisioning import complete_signup, prepare_signup_compensation, record_signup_compensation, reserve_signup

logger = logging.getLogger(__name__)

NONCE_SESSION_KEY = "google_signin_nonces"
NONCE_TTL_SECONDS = 300
# A verified Google identity waiting for its membership application.
PENDING_SIGNUP_SESSION_KEY = "google_signup_pending"
PENDING_SIGNUP_TTL_SECONDS = 600
MAX_NONCES = 5
VERIFY_TIMEOUT_SECONDS = 5


class GoogleSignInError(ValueError):
    """A safe explanation suitable for the sign-in page."""


class GoogleSignupRetryError(GoogleSignInError):
    """Provisioning failed; retain the verified signup and entered statement."""


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


def apply_google_login_headers(request, response):
    """Permit GIS popups, with Google's referrer policy only for HTTP loopback."""
    if not getattr(settings, "GOOGLE_CLIENT_ID", "").strip():
        return response
    response["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    host = urlsplit(f"//{request.get_host()}").hostname
    if not request.is_secure() and host in {"localhost", "127.0.0.1"}:
        response["Referrer-Policy"] = "no-referrer-when-downgrade"
    return response


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


def _validated_claims(claims):
    """Return (subject, email) from verified claims, or raise a safe error."""
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
    return subject, email


def _existing_identity_user(subject):
    """The account already linked to this Google subject, if any."""
    identity = GoogleIdentity.objects.filter(subject=subject).select_related("user").first()
    if identity is None:
        return None
    if Profile.objects.filter(user_id=identity.user_id, is_suspended=True).exists():
        raise GoogleSignInError("This account is administratively suspended.")
    if Profile.objects.filter(user_id=identity.user_id, suspension_update_pending=True).exists():
        raise GoogleSignInError("Your account access is still being updated. Please try again shortly.")
    if not identity.user.is_active:
        # Pending or refused membership applications land here too.
        raise GoogleSignInError(inactive_account_message(identity.user))
    if MembershipApplication.objects.filter(
        user_id=identity.user_id, access_update_pending=True
    ).exists():
        raise GoogleSignInError("Your membership review is still being applied. Please try again shortly.")
    # The subject, not a mutable email address, identifies returning users.
    return identity.user


def _email_collision(email):
    return Q(email__iexact=email) | Q(username__iexact=email)


def _ensure_email_unused(email):
    if get_user_model().objects.filter(_email_collision(email)).exists():
        raise GoogleSignInError(
            "An account already uses this email. Sign in with that account; "
            "Google accounts are not linked automatically."
        )


def _cleanup_google_signup(attempt, *, application_attempted=False):
    """Best-effort compensation limited to the account reserved by this attempt."""
    if not prepare_signup_compensation(attempt, application_attempted=application_attempted):
        return
    try:
        get_user_model().objects.filter(pk=attempt.reserved_user_id, username=attempt.username).delete()
    except Exception:
        # Database exceptions can include connection strings or account data.
        # Keep the recovery alert free of exception details and credentials.
        logger.error("An incomplete Google signup could not be cleaned up; operator recovery is required.")


def create_google_applicant(subject, email, statement):
    """Create a switched-off account, its Google link, and its membership application.

    Like password sign-up, the account can't sign in until an officer
    approves the application.
    """
    User = get_user_model()
    username = f"google_{uuid4().hex}"
    attempt = None
    attempted_create = False
    stage = "precheck"
    try:
        if GoogleIdentity.objects.filter(subject=subject).exists():
            raise GoogleSignInError("This Google account has already applied. Sign in to check its status.")
        _ensure_email_unused(email)
        attempt = reserve_signup("google", username, email, statement, subject)
        stage = "user"
        attempted_create = True
        user = User.objects.create_user(
            pk=attempt.reserved_user_id, username=username, email=email, password=None, is_active=False
        )
        # Canonical database indexes reject identity races. Retain this check
        # for a safe response when inspecting an older unmigrated database.
        if User.objects.filter(_email_collision(email)).exclude(pk=user.pk).exists():
            raise GoogleSignInError("An account already uses this email. Sign in with that account.")
        stage = "identity"
        GoogleIdentity.objects.create(subject=subject, user=user)
        stage = "application"
        MembershipApplication.objects.create(pk=attempt.application_id, user=user, statement=statement)
        complete_signup(attempt)
    except IntegrityError as error:
        if attempted_create:
            _cleanup_google_signup(attempt, application_attempted=stage == "application")
            record_signup_compensation(attempt)
        if stage == "identity":
            # A simultaneous sign-up with this subject may have won the race.
            raise GoogleSignInError(
                "This Google account has already applied. Sign in to check its status."
            ) from error
        if stage == "user":
            raise GoogleSignInError("This account could not be created. Please try again.") from error
        raise GoogleSignupRetryError(
            "Your application could not be confirmed right now. Please try submitting it again."
        ) from error
    except DatabaseError as error:
        if attempted_create:
            _cleanup_google_signup(attempt, application_attempted=stage == "application")
            record_signup_compensation(attempt)
        raise GoogleSignupRetryError(
            "Your application could not be confirmed right now. Please try submitting it again."
        ) from error
    except Exception:
        if attempted_create:
            _cleanup_google_signup(attempt, application_attempted=stage == "application")
            record_signup_compensation(attempt)
        raise
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
        apply_google_login_headers(request, response)
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
        subject, email = _validated_claims(claims)
        user = _existing_identity_user(subject)
        if user is None:
            _ensure_email_unused(email)
    except GoogleSignInError as error:
        return _login_error(request, str(error))
    request.session.pop(NONCE_SESSION_KEY, None)
    if user is None:
        # New to OrgFlow: collect the membership application before creating
        # anything. Only the verified subject and email are kept, briefly.
        request.session[PENDING_SIGNUP_SESSION_KEY] = {
            "subject": subject,
            "email": email,
            "issued": time.time(),
        }
        return redirect("accounts:google_apply")
    target = _safe_next(request)
    login(request, user, backend="accounts.backends.EmailOrUsernameBackend")
    return redirect(target)


def _pending_signup(request):
    pending = request.session.get(PENDING_SIGNUP_SESSION_KEY)
    if (
        isinstance(pending, dict)
        and isinstance(pending.get("subject"), str)
        and isinstance(pending.get("email"), str)
        and isinstance(pending.get("issued"), (int, float))
        and 0 <= time.time() - pending["issued"] <= PENDING_SIGNUP_TTL_SECONDS
    ):
        return pending
    request.session.pop(PENDING_SIGNUP_SESSION_KEY, None)
    return None


@csrf_protect
def google_apply(request):
    """Second step of Google sign-up: the membership application."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    pending = _pending_signup(request)
    if pending is None:
        messages.error(request, "Your Google sign-up expired. Please sign in with Google again.")
        return redirect("accounts:login")

    form = GoogleApplicationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            create_google_applicant(pending["subject"], pending["email"], form.cleaned_data["statement"])
        except GoogleSignupRetryError as error:
            form.add_error(None, str(error))
            return render(
                request, "accounts/google_apply.html",
                {"form": form, "email": pending["email"]}, status=503,
            )
        except GoogleSignInError as error:
            request.session.pop(PENDING_SIGNUP_SESSION_KEY, None)
            messages.error(request, str(error))
            return redirect("accounts:login")
        request.session.pop(PENDING_SIGNUP_SESSION_KEY, None)
        messages.success(
            request,
            "Application submitted. You can sign in with Google once an officer approves it.",
        )
        return redirect("core:home")
    return render(request, "accounts/google_apply.html", {"form": form, "email": pending["email"]})
