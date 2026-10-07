"""Shared helpers for tests across OrgFlow apps."""

from django.contrib.auth import get_user_model

from .models import Role, set_role

PASSWORD = "correct-horse-battery"


def make_user(email, role=Role.APPLICANT):
    user = get_user_model().objects.create_user(username=email, email=email, password=PASSWORD)
    if role != Role.APPLICANT:
        set_role(user, role)
    return user
