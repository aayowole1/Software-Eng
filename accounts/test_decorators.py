"""Unit tests for accounts/decorators.py — role_required()."""

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .decorators import role_required
from .models import Role
from .testing import make_user


# A minimal view protected by the decorator so we can call it directly.
@role_required(Role.OFFICER)
def _officer_view(request):
    from django.http import HttpResponse
    return HttpResponse("OK")


@role_required(Role.MEMBER)
def _member_view(request):
    from django.http import HttpResponse
    return HttpResponse("OK")


@role_required(Role.ADMIN)
def _admin_view(request):
    from django.http import HttpResponse
    return HttpResponse("OK")


class RoleRequiredDecoratorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _get(self, view, user=None):
        request = self.factory.get("/fake/")
        if user is not None:
            request.user = user
        else:
            from django.contrib.auth.models import AnonymousUser
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

    def test_member_can_access_member_view(self):
        user = make_user("member@example.com", Role.MEMBER)
        response = self._get(_member_view, user)
        self.assertEqual(response.status_code, 200)

    def test_officer_can_access_member_view(self):
        user = make_user("officer@example.com", Role.OFFICER)
        response = self._get(_member_view, user)
        self.assertEqual(response.status_code, 200)

    # ---- access denied ----

    def test_member_cannot_access_officer_view(self):
        user = make_user("member@example.com", Role.MEMBER)
        with self.assertRaises(PermissionDenied):
            self._get(_officer_view, user)

    def test_applicant_cannot_access_officer_view(self):
        user = make_user("applicant@example.com", Role.APPLICANT)
        with self.assertRaises(PermissionDenied):
            self._get(_officer_view, user)

    def test_applicant_cannot_access_member_view(self):
        user = make_user("applicant@example.com", Role.APPLICANT)
        with self.assertRaises(PermissionDenied):
            self._get(_member_view, user)

    def test_officer_cannot_access_admin_view(self):
        user = make_user("officer@example.com", Role.OFFICER)
        with self.assertRaises(PermissionDenied):
            self._get(_admin_view, user)

    # ---- unauthenticated ----

    def test_anonymous_user_is_redirected_to_login(self):
        response = self._get(_officer_view)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_anonymous_user_cannot_access_member_view(self):
        response = self._get(_member_view)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    # ---- decorator preserves wrapped function name ----

    def test_decorated_view_preserves_function_name(self):
        # functools.wraps should keep __name__ intact through the login_required wrapper.
        self.assertEqual(_officer_view.__name__, "_officer_view")
