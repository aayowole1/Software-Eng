"""Bounded operator recovery of an explicitly marked, inactive signup."""

import logging

from bson import ObjectId
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError
from django.utils import timezone
from pymongo.errors import BulkWriteError, DuplicateKeyError

from membership.models import ApplicationStatus, MembershipApplication

from .models import GoogleIdentity, Profile, Role
from .signup_attempts import SignupAttempt

logger = logging.getLogger(__name__)


class SignupRecoveryRefused(ValueError):
    """The saved evidence does not permit this narrowly scoped repair."""


def is_identifier_conflict(error):
    """Classify a real Mongo username/email collision without exposing details.

    Profile signals run inside create_user too; their integrity failures must
    retain retry handling instead of being mislabeled as account collisions.
    """
    cause = error.__cause__
    if not isinstance(cause, (BulkWriteError, DuplicateKeyError)):
        return False
    details = cause.details or {}
    errors = details.get("writeErrors", [details])
    return any(
        entry.get("code", getattr(cause, "code", None)) == 11000
        and set(entry.get("keyPattern", {})) in ({"username"}, {"email"})
        for entry in errors
    )


def reserve_signup(channel, username, email, statement, google_subject=""):
    return SignupAttempt.objects.create(
        reserved_user_id=ObjectId(), application_id=ObjectId(), channel=channel,
        username=username, email=email.strip().lower(), statement=statement,
        google_subject=google_subject,
    )


def complete_signup(attempt):
    changed = SignupAttempt.objects.filter(
        pk=attempt.pk, state=SignupAttempt.State.PENDING,
    ).update(state=SignupAttempt.State.COMPLETED, completed_at=timezone.now())
    if changed != 1:
        current = SignupAttempt.objects.get(pk=attempt.pk)
        if current.state != SignupAttempt.State.COMPLETED:
            raise SignupRecoveryRefused("The signup attempt state changed; inspect it before retrying.")


def prepare_signup_compensation(attempt, *, application_attempted=False):
    """Confirm recoverable intent before removing any provisioned relation.

    Once application insertion starts, its visibility/review cannot be rolled
    back safely. Preserve it even if the insertion acknowledgement failed.
    """
    if application_attempted:
        logger.error("Signup attempt %s preserved after application insertion was attempted; inspect its recorded outcome.", attempt.pk)
        return False
    try:
        user, _ = _untouched_signup_account(attempt)
        if MembershipApplication.objects.filter(user_id=user.pk).exists():
            raise SignupRecoveryRefused("An application already exists; cleanup must preserve it.")
        changed = SignupAttempt.objects.filter(
            pk=attempt.pk, state__in=[SignupAttempt.State.PENDING, SignupAttempt.State.COMPLETED],
        ).update(state=SignupAttempt.State.PENDING, completed_at=None)
        if changed == 1:
            _untouched_signup_account(attempt)
            return True
    except (DatabaseError, SignupRecoveryRefused):
        pass
    logger.error("Signup attempt %s cleanup skipped: recoverable intent could not be confirmed.", attempt.pk)
    return False


def record_signup_compensation(attempt):
    """Retain the journal even when request-local compensation succeeds."""
    try:
        if not get_user_model().objects.filter(pk=attempt.reserved_user_id).exists():
            SignupAttempt.objects.filter(
                pk=attempt.pk, state__in=[SignupAttempt.State.PENDING, SignupAttempt.State.COMPLETED],
            ).update(
                state=SignupAttempt.State.COMPENSATED,
            )
            return
    except DatabaseError:
        pass
    logger.error("Incomplete signup attempt %s requires operator recovery.", attempt.pk)


def _unexpected_references(user):
    """A signup repair must not modify an account already used by the app."""
    allowed = {(Profile, "user"), (GoogleIdentity, "user"), (MembershipApplication, "user")}
    User = get_user_model()
    for model in apps.get_models(include_auto_created=True):
        for field in model._meta.local_fields:
            if (
                field.is_relation and field.remote_field.model == User
                and (model, field.name) not in allowed
                and model.objects.filter(**{field.attname: user.pk}).exists()
            ):
                return True
    return False


def _untouched_signup_account(attempt):
    """Require observed, never-used signup state before early compensation."""
    User = get_user_model()
    user = User.objects.filter(pk=attempt.reserved_user_id).first()
    if user is None:
        raise SignupRecoveryRefused("The reserved account does not exist; a new signup can be submitted. No account will be created by repair.")
    if (
        user.username != attempt.username or user.email.strip().lower() != attempt.email
        or user.is_active or user.is_staff or user.is_superuser or user.last_login is not None
    ):
        raise SignupRecoveryRefused("The reserved account identity or access state no longer matches an incomplete signup.")
    profile = Profile.objects.filter(user_id=user.pk).first()
    if profile and (
        profile.role != Role.APPLICANT or profile.is_suspended or profile.suspension_update_pending
        or profile.role_version or profile.role_history
        or profile.suspension_version or profile.suspension_was_active is not None
        or profile.suspension_restore_active is not None
    ):
        raise SignupRecoveryRefused("The reserved account has role, suspension or audit state that requires separate investigation.")
    if _unexpected_references(user):
        raise SignupRecoveryRefused("The reserved account has permissions or other application records; automatic repair is refused.")
    identity = GoogleIdentity.objects.filter(user_id=user.pk).first()
    if (
        (attempt.channel == SignupAttempt.Channel.PASSWORD and (identity or not user.has_usable_password()))
        or (attempt.channel == SignupAttempt.Channel.GOOGLE and (
            user.has_usable_password() or (identity and identity.subject != attempt.google_subject)
        ))
    ):
        raise SignupRecoveryRefused("The reserved account no longer has its original signup credentials.")
    return user, profile


def inspect_signup(attempt):
    """Validate the complete repair boundary without making any writes."""
    attempt = SignupAttempt.objects.get(pk=attempt.pk)
    if attempt.state == SignupAttempt.State.COMPLETED:
        return {"state": "completed", "actions": []}
    if attempt.state != SignupAttempt.State.PENDING:
        raise SignupRecoveryRefused("This attempt was compensated; submit a new signup instead.")
    user, profile = _untouched_signup_account(attempt)

    applications = list(MembershipApplication.objects.filter(user_id=user.pk))
    application = MembershipApplication.objects.filter(pk=attempt.application_id).first()
    if (
        len(applications) > 1
        or (applications and applications[0].pk != attempt.application_id)
        or (application and (
            application.user_id != user.pk or application.statement != attempt.statement
            or application.status != ApplicationStatus.PENDING or application.reviewed_by_id is not None
            or application.reviewed_at is not None or application.review_note or application.access_update_pending
        ))
    ):
        raise SignupRecoveryRefused("An application conflicts with this signup, or a review has already started. No review will be changed.")

    identity = GoogleIdentity.objects.filter(user_id=user.pk).first()
    if attempt.channel == SignupAttempt.Channel.GOOGLE:
        other = GoogleIdentity.objects.filter(subject=attempt.google_subject).first()
        if (
            not attempt.google_subject or user.has_usable_password()
            or (identity and identity.subject != attempt.google_subject)
            or (other and other.user_id != user.pk)
        ):
            raise SignupRecoveryRefused("The saved Google identity conflicts with an existing account. No accounts will be linked.")
    elif attempt.channel == SignupAttempt.Channel.PASSWORD:
        if attempt.google_subject or identity or not user.has_usable_password():
            raise SignupRecoveryRefused("The saved password signup identity does not match the reserved account.")
    else:
        raise SignupRecoveryRefused("The signup channel is not supported.")

    actions = []
    if profile is None:
        actions.append("create missing Applicant profile")
    if attempt.channel == SignupAttempt.Channel.GOOGLE and identity is None:
        actions.append("restore original verified Google subject link")
    if application is None:
        actions.append("create original pending membership application")
    actions.append("mark signup attempt completed; account remains inactive")
    return {"state": "pending", "actions": actions, "user": user}


def repair_signup(attempt):
    """Idempotent restore; operator must first quiesce registration workers.

    Reserved primary keys and unique identity/profile constraints make interrupted
    and repeated repairs safe. This never creates/deletes a User or grants access.
    """
    plan = inspect_signup(attempt)
    if plan["state"] == "completed":
        return plan
    user = plan["user"]
    Profile.objects.get_or_create(user=user, defaults={"role": Role.APPLICANT})
    if attempt.channel == SignupAttempt.Channel.GOOGLE:
        try:
            GoogleIdentity.objects.get_or_create(subject=attempt.google_subject, defaults={"user": user})
        except IntegrityError:
            # Revalidate a competing insert; do not assume it belongs to us.
            inspect_signup(attempt)
            raise
    try:
        MembershipApplication.objects.get_or_create(
            pk=attempt.application_id, defaults={"user": user, "statement": attempt.statement},
        )
    except IntegrityError:
        inspect_signup(attempt)
        raise
    inspect_signup(attempt)
    complete_signup(attempt)
    return {"state": "completed", "actions": plan["actions"]}
