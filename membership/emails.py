"""Transactional email notifications for membership decisions.

Each function sends exactly one email and swallows all delivery failures so that
a misconfigured or temporarily unavailable SMTP server never rolls back a review
decision that has already been committed to the database.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_application_approved(application):
    """Notify the applicant that their membership application was approved.

    Called only after a successful, committed review. Never raises; delivery
    failures are logged and the decision record is not affected.
    """
    _send_notification(application, approved=True)


def send_application_rejected(application):
    """Notify the applicant that their membership application was rejected.

    Called only after a successful, committed review. Never raises; delivery
    failures are logged and the decision record is not affected.
    """
    _send_notification(application, approved=False)


def _send_notification(application, *, approved):
    kind = "approved" if approved else "rejected"
    try:
        context = {"application": application, "user": application.user}
        subject = render_to_string(
            f"membership/application_{kind}_subject.txt", context
        ).strip()
        body = render_to_string(
            f"membership/application_{kind}_email.txt", context
        )
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [application.user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Membership %s notification could not be delivered (application pk omitted).",
            kind,
        )
