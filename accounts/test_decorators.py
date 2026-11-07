"""Unit tests for accounts/decorators.py — role_required().

Maps directly to SCRUM-59 acceptance criteria (FR-01 / NFR-02):
  AC1 — Protected pages require login.
  AC2 — Officer-only pages return 403 to members.
  AC3 — Pending applicants cannot sign in (enforced via is_active / applicant role).
"""

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .decorators import role_required
from .models import Role
from .testing import make_user


# ---------------------------------------------------------------------------
# Minimal protected views used as test subjects
# ---------------------------------------------------------------------------

@role_required(Role.OFFICER)
def _officer_view(request):
    return HttpResponse("OK")


@role_required(Role.MEMBER)
def _member_view(request):
    return HttpResponse("OK")


@role_required(Role.ADMIN)
def _admin_view(request):
    return HttpResponse("OK")


class RoleRequiredDecoratorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _get(self, view, user=None):
        request = self.factory.get("/fake/")
        if user is not None:
            request.user = user
        else:
            request.user = AnonymousUser()
        return view(request)

    # ---- access granted ----

    def test_officer_can_access_officer_view(self):
        user = make_user("officer@example.com", Role.OFFICER)
        response = self._get(_officer_view, user)
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access_officer_view(self):
        user = make_user("admin@example.com", Role.ADMIN)
        response = self._get(_officer_view, user)
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access_admin_view(self):
        user = make_user("admin@example.com", Role.ADMIN)
        response = self._get(_admin_view, user)
        self.assertEqual(response.status_code, 200)

    def test_member_can_access_member_view(self):
        user = make_user("member@example.com", Role.MEMBER)
        response = self._get(_member_view, user)
        self.assertEqual(response.status_code, 200)

    def test_officer_can_access_member_view(self):
        """Officers include all member permissions (role hierarchy)."""
        user = make_user("officer@example.com", Role.OFFICER)
        response = self._get(_member_view, user)
        self.assertEqual(response.status_code, 200)

    # ---- access denied ----

    def test_member_cannot_access_officer_view(self):
        """AC2: member role raises PermissionDenied (HTTP 403) on an officer view."""
        user = make_user("member@example.com", Role.MEMBER)
        with self.assertRaises(PermissionDenied):
            self._get(_officer_view, user)

    def test_member_cannot_access_admin_view(self):
        """AC2: member role raises PermissionDenied on an admin-only view."""
        user = make_user("member@example.com", Role.MEMBER)
        with self.assertRaises(PermissionDenied):
            self._get(_admin_view, user)

    def test_officer_cannot_access_admin_view(self):
        """AC2: officer role raises PermissionDenied on an admin-only view."""
        user = make_user("officer@example.com", Role.OFFICER)
        with self.assertRaises(PermissionDenied):
            self._get(_admin_view, user)

    def test_applicant_cannot_access_officer_view(self):
        """AC3: applicant (pending) role raises PermissionDenied on an officer view."""
        user = make_user("applicant@example.com", Role.APPLICANT)
        with self.assertRaises(PermissionDenied):
            self._get(_officer_view, user)

    def test_applicant_cannot_access_member_view(self):
        """AC3: applicant role raises PermissionDenied on a member view."""
        user = make_user("applicant@example.com", Role.APPLICANT)
        with self.assertRaises(PermissionDenied):
            self._get(_member_view, user)

    # ---- unauthenticated — AC1 ----

    def test_anonymous_user_is_redirected_to_login(self):
        """AC1: unauthenticated request → redirect to the login page."""
        response = self._get(_officer_view)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_anonymous_user_cannot_access_member_view(self):
        """AC1: unauthenticated request → redirect to login for member-gated view."""
        response = self._get(_member_view)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_anonymous_user_cannot_access_admin_view(self):
        """AC1: unauthenticated request → redirect to login for admin-gated view."""
        response = self._get(_admin_view)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    # ---- decorator preserves wrapped function name ----

    def test_decorated_view_preserves_function_name(self):
        # functools.wraps should keep __name__ intact through the login_required wrapper.
        self.assertEqual(_officer_view.__name__, "_officer_view")
        self.assertEqual(_member_view.__name__, "_member_view")
        self.assertEqual(_admin_view.__name__, "_admin_view")


class RoleRequiredIntegrationTests(TestCase):
    """HTTP-level integration tests via the test client (status codes).

    Verifies the same boundaries against real registered URL patterns so that
    any future routing or middleware change is caught as well.
    """

    def test_unauthenticated_access_to_profile_redirects_to_login(self):
        """AC1: /accounts/me/ requires login."""
        response = self.client.get(reverse("accounts:profile"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:profile')}",
        )

    def test_unauthenticated_access_to_user_list_redirects_to_login(self):
        """AC1: /accounts/users/ requires login."""
        response = self.client.get(reverse("accounts:user_list"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('accounts:user_list')}",
        )

    def test_member_gets_403_on_admin_user_list(self):
        """AC2: member cannot reach the admin user-list page."""
        self.client.force_login(make_user("member@example.com", Role.MEMBER))
        self.assertEqual(self.client.get(reverse("accounts:user_list")).status_code, 403)

    def test_officer_gets_403_on_admin_user_list(self):
        """AC2: officer cannot reach the admin-only user-list page."""
        self.client.force_login(make_user("officer@example.com", Role.OFFICER))
        self.assertEqual(self.client.get(reverse("accounts:user_list")).status_code, 403)

    def test_applicant_gets_403_on_admin_user_list(self):
        """AC2 / AC3: applicant (pending) cannot reach any protected page."""
        self.client.force_login(make_user("applicant@example.com", Role.APPLICANT))
        self.assertEqual(self.client.get(reverse("accounts:user_list")).status_code, 403)

    def test_admin_can_access_user_list(self):
        """Admin role clears the role_required gate."""
        self.client.force_login(make_user("admin@example.com", Role.ADMIN))
        self.assertEqual(self.client.get(reverse("accounts:user_list")).status_code, 200)
