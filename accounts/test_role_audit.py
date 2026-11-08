"""Role changes and their audit state commit together on standalone MongoDB."""

from importlib import import_module
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import DatabaseError, connection
from django.db.migrations.loader import MigrationLoader
from django.db.models.query import QuerySet
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.dateparse import parse_datetime

from membership.models import ApplicationStatus, MembershipApplication

from .admin import ProfileAdmin
from .models import Profile, Role, RoleChangeBlocked, RoleChangeConflict, set_role
from .testing import make_user

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RoleAuditTests(TestCase):
    def setUp(self):
        self.admin = make_user("role-admin@example.com", Role.ADMIN)
        self.officer = make_user("role-officer@example.com", Role.OFFICER)
        self.target = make_user("role-target@example.com")

    def profile(self):
        return Profile.objects.get(user=self.target)

    def url(self):
        return reverse("accounts:change_role", args=[self.target.pk])

    def test_role_and_actor_history_are_persisted_together(self):
        profile = set_role(self.target, Role.MEMBER, actor=self.admin, source="role_audit_test")
        self.assertEqual(profile.role, Role.MEMBER)
        self.assertEqual(profile.role_version, 1)
        self.assertEqual(len(profile.role_history), 1)
        entry = profile.role_history[0]
        self.assertEqual(entry["actor_id"], str(self.admin.pk))
        self.assertEqual(entry["actor"], self.admin.get_username())
        self.assertEqual(entry["old_role"], Role.APPLICANT)
        self.assertEqual(entry["new_role"], Role.MEMBER)
        self.assertEqual(entry["source"], "role_audit_test")
        self.assertIsNotNone(parse_datetime(entry["at"]).tzinfo)
        self.assertEqual(self.profile().role_history, profile.role_history)

    def test_legacy_call_records_system_without_inventing_a_human_actor(self):
        entry = set_role(self.target, Role.MEMBER).role_history[0]
        self.assertIsNone(entry["actor_id"])
        self.assertEqual(entry["actor"], "System")
        self.assertEqual(entry["source"], "system")

    def test_noop_and_retry_do_not_duplicate_history_or_version(self):
        first = set_role(self.target, Role.APPLICANT, actor=self.admin)
        self.assertEqual(first.role_version, 0)
        self.assertEqual(first.role_history, [])
        set_role(self.target, Role.MEMBER, actor=self.admin, expected_version=0)
        retry = set_role(self.target, Role.MEMBER, actor=self.admin, expected_version=0)
        self.assertEqual(retry.role_version, 1)
        self.assertEqual(len(retry.role_history), 1)

    def test_new_profiles_have_independent_empty_audit_defaults(self):
        first = self.profile()
        other = make_user("second-applicant@example.com").profile
        self.assertEqual((first.role_version, other.role_version), (0, 0))
        first.role_history.append({"not_saved": True})
        self.assertEqual(other.role_history, [])
        self.assertEqual(self.profile().role_history, [])

    def test_stale_version_preserves_first_change_and_history(self):
        set_role(self.target, Role.OFFICER, actor=self.admin, expected_version=0)
        with self.assertRaises(RoleChangeConflict):
            set_role(self.target, Role.MEMBER, actor=self.admin, expected_version=0)
        current = self.profile()
        self.assertEqual(current.role, Role.OFFICER)
        self.assertEqual(current.role_version, 1)
        self.assertEqual(len(current.role_history), 1)

    def test_interleaving_role_writer_keeps_only_the_winning_history(self):
        original = QuerySet.update
        interleaved = False

        def update(queryset, **values):
            nonlocal interleaved
            if queryset.model is Profile and values.get("role") == Role.MEMBER and not interleaved:
                interleaved = True
                set_role(self.target, Role.OFFICER, actor=self.admin, source="winning_request")
            return original(queryset, **values)

        with patch.object(QuerySet, "update", autospec=True, side_effect=update):
            with self.assertRaises(RoleChangeConflict):
                set_role(self.target, Role.MEMBER, actor=self.admin, source="stale_request")
        current = self.profile()
        self.assertEqual(current.role, Role.OFFICER)
        self.assertEqual(current.role_version, 1)
        self.assertEqual([entry["source"] for entry in current.role_history], ["winning_request"])

    def test_database_failure_leaves_role_and_history_unchanged(self):
        with patch.object(QuerySet, "update", side_effect=DatabaseError("Unavailable")):
            with self.assertRaises(DatabaseError):
                set_role(self.target, Role.MEMBER, actor=self.admin)
        current = self.profile()
        self.assertEqual(current.role, Role.APPLICANT)
        self.assertEqual(current.role_history, [])
        self.assertEqual(current.role_version, 0)

    def test_lost_acknowledgement_retry_does_not_append_another_event(self):
        original = QuerySet.update

        def write_then_fail(queryset, **values):
            result = original(queryset, **values)
            if queryset.model is Profile and "role_history" in values:
                raise DatabaseError("Write succeeded but acknowledgement was lost")
            return result

        with patch.object(QuerySet, "update", autospec=True, side_effect=write_then_fail):
            with self.assertRaises(DatabaseError):
                set_role(self.target, Role.MEMBER, actor=self.admin, expected_version=0)
        retry = set_role(self.target, Role.MEMBER, actor=self.admin, expected_version=0)
        self.assertEqual(retry.role, Role.MEMBER)
        self.assertEqual(len(retry.role_history), 1)
        self.assertEqual(retry.role_version, 1)

    def test_superuser_guard_rechecks_saved_authority_before_demotion(self):
        User.objects.filter(pk=self.target.pk).update(is_superuser=True)
        with self.assertRaisesMessage(ValueError, "Superusers must remain admins"):
            set_role(self.target, Role.MEMBER, actor=self.admin)
        self.assertEqual(self.profile().role_history, [])
        self.assertEqual(self.profile().role, Role.APPLICANT)

    def test_invalid_values_do_not_create_audit_events(self):
        for kwargs in [{"role": "wizard"}, {"role": Role.MEMBER, "expected_version": -1},
                       {"role": Role.MEMBER, "expected_version": True},
                       {"role": Role.MEMBER, "source": "x" * 101}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                set_role(self.target, actor=self.admin, **kwargs)
        self.assertEqual(self.profile().role_history, [])

    def test_admin_route_records_authenticated_actor_and_shows_readable_history(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url(), {"role": Role.MEMBER, "version": 0}, follow=True)
        self.assertContains(response, "Role history")
        self.assertContains(response, "Applicant to Member")
        self.assertContains(response, self.admin.get_username())
        entry = self.profile().role_history[0]
        self.assertEqual(entry["actor_id"], str(self.admin.pk))
        self.assertEqual(entry["source"], "account_role_management")

    def test_non_admin_cannot_read_history_or_change_roles(self):
        set_role(self.target, Role.MEMBER, actor=self.admin)
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get(reverse("accounts:user_list")).status_code, 403)
        self.assertEqual(self.client.post(self.url(), {"role": Role.ADMIN, "version": 1}).status_code, 403)
        self.assertEqual(self.profile().role, Role.MEMBER)
        self.assertEqual(len(self.profile().role_history), 1)

    def test_stale_admin_form_does_not_report_a_successful_overwrite(self):
        set_role(self.target, Role.OFFICER, actor=self.admin)
        self.client.force_login(self.admin)
        response = self.client.post(self.url(), {"role": Role.MEMBER, "version": 0})
        notices = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("changed while you were editing", notices)
        self.assertNotIn("is now member", notices)
        self.assertEqual(self.profile().role, Role.OFFICER)

    def test_admin_database_error_gives_uncertain_write_feedback_not_success(self):
        self.client.force_login(self.admin)
        with patch("accounts.views.set_role", side_effect=DatabaseError("Unavailable")):
            response = self.client.post(self.url(), {"role": Role.MEMBER, "version": 0})
        notices = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("could not be confirmed", notices)
        self.assertNotIn("is now member", notices)
        self.assertEqual(self.profile().role_history, [])

    def test_history_display_escapes_actor_and_source(self):
        self.admin.username = "<script>audit-actor</script>"
        self.admin.save(update_fields=["username"])
        set_role(self.target, Role.MEMBER, actor=self.admin, source="<script>audit-source</script>")
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertContains(response, "&lt;script&gt;audit-actor&lt;/script&gt;")
        self.assertContains(response, "&lt;script&gt;audit-source&lt;/script&gt;")
        self.assertNotContains(response, "<script>audit-actor")
        self.assertNotContains(response, "<script>audit-source")

    def test_django_profile_admin_cannot_bypass_role_writer_or_edit_history(self):
        model_admin = ProfileAdmin(Profile, admin.site)
        request = RequestFactory().get("/admin/")
        request.user = self.officer
        self.assertFalse(model_admin.has_view_permission(request, self.profile()))
        self.assertFalse(model_admin.has_change_permission(request, self.profile()))
        readonly = model_admin.get_readonly_fields(request, self.profile())
        self.assertIn("role", readonly)
        self.assertIn("role_history", readonly)
        self.assertIn("role_version", readonly)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request, self.profile()))
        request.user = self.admin
        self.assertFalse(model_admin.has_change_permission(request, self.profile()))

    def test_membership_promotion_records_original_reviewer_without_duplicate_on_retry(self):
        self.target.is_active = False
        self.target.save(update_fields=["is_active"])
        application = MembershipApplication.objects.create(user=self.target, statement="Join")
        original = User.save

        def fail_activation(user, *args, **kwargs):
            if user.pk == self.target.pk and "is_active" in (kwargs.get("update_fields") or ()):
                raise DatabaseError("Activation failed after promotion")
            return original(user, *args, **kwargs)

        with patch.object(User, "save", autospec=True, side_effect=fail_activation):
            with self.assertRaises(DatabaseError):
                application.review(self.officer, True, "Welcome")
        application.refresh_from_db()
        self.assertTrue(application.access_update_pending)
        first = self.profile()
        self.assertEqual(first.role, Role.MEMBER)
        self.assertEqual(len(first.role_history), 1)
        self.assertEqual(first.role_history[0]["actor_id"], str(self.officer.pk))
        self.assertEqual(first.role_history[0]["source"], f"membership_review:{application.pk}")
        application.complete_access_update()
        self.assertEqual(self.profile().role_history, first.role_history)
        self.assertEqual(self.profile().role_version, 1)
        self.assertFalse(application.access_update_pending)

    def test_membership_approval_never_demotes_newer_officer_assignment(self):
        set_role(self.target, Role.OFFICER, actor=self.admin, source="newer_assignment")
        application = MembershipApplication.objects.create(user=self.target, statement="Old application")
        application.review(self.officer, True)
        current = self.profile()
        self.assertEqual(current.role, Role.OFFICER)
        self.assertEqual(len(current.role_history), 1)
        self.assertEqual(current.role_history[0]["source"], "newer_assignment")

    def test_suspension_interleaving_prevents_membership_role_write(self):
        original = QuerySet.update
        changed = False

        def suspend_then_update(queryset, **values):
            nonlocal changed
            if queryset.model is Profile and values.get("role") == Role.MEMBER and not changed:
                changed = True
                original(Profile.objects.filter(user=self.target), is_suspended=True)
            return original(queryset, **values)

        with patch.object(QuerySet, "update", autospec=True, side_effect=suspend_then_update):
            with self.assertRaises(RoleChangeConflict):
                set_role(self.target, Role.MEMBER, actor=self.officer,
                         expected_role=Role.APPLICANT, require_unsuspended=True)
        current = self.profile()
        self.assertTrue(current.is_suspended)
        self.assertEqual(current.role, Role.APPLICANT)
        self.assertEqual(current.role_history, [])

    def test_pending_application_cannot_be_promoted_by_admin_http(self):
        application = MembershipApplication.objects.create(user=self.target, statement="Awaiting review")
        self.client.force_login(self.admin)
        response = self.client.post(self.url(), {"role": Role.OFFICER, "version": 0}, follow=True)
        self.assertContains(response, "Finish this account&#x27;s membership review", html=False)
        self.assertEqual(self.profile().role, Role.APPLICANT)
        self.assertEqual(self.profile().role_history, [])
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.PENDING)

    def test_unfinished_approved_access_cannot_be_promoted_by_admin_http(self):
        MembershipApplication.objects.create(
            user=self.target, statement="Recorded decision", status=ApplicationStatus.APPROVED,
            reviewed_by=self.officer, access_update_pending=True,
        )
        self.client.force_login(self.admin)
        self.client.post(self.url(), {"role": Role.ADMIN, "version": 0})
        self.assertEqual(self.profile().role, Role.APPLICANT)
        self.assertEqual(self.profile().role_history, [])

    def test_source_string_cannot_bypass_membership_review(self):
        application = MembershipApplication.objects.create(user=self.target, statement="Awaiting review")
        with self.assertRaises(RoleChangeBlocked):
            set_role(self.target, Role.OFFICER, actor=self.admin, source=f"membership_review:{application.pk}")
        self.assertEqual(self.profile().role_history, [])

    def test_internal_membership_contract_requires_approved_decision_and_original_reviewer(self):
        application = MembershipApplication.objects.create(user=self.target, statement="Awaiting review")
        contract = {"expected_role": Role.APPLICANT, "require_unsuspended": True, "membership_review": application}
        with self.assertRaises(RoleChangeBlocked):
            set_role(self.target, Role.MEMBER, actor=self.officer, **contract)
        MembershipApplication.objects.filter(pk=application.pk).update(
            status=ApplicationStatus.APPROVED, access_update_pending=True, reviewed_by=self.officer,
        )
        with self.assertRaises(RoleChangeBlocked):
            set_role(self.target, Role.MEMBER, actor=self.admin, **contract)
        with self.assertRaises(RoleChangeBlocked):
            set_role(self.target, Role.ADMIN, actor=self.officer, **contract)
        self.assertEqual(self.profile().role_history, [])

    def test_approved_promotion_cannot_ignore_another_pending_application(self):
        application = MembershipApplication.objects.create(
            user=self.target, statement="Approved", status=ApplicationStatus.APPROVED,
            access_update_pending=True, reviewed_by=self.officer,
        )
        MembershipApplication.objects.create(user=self.target, statement="Conflicting pending application")
        with self.assertRaises(RoleChangeBlocked):
            application.complete_access_update()
        self.assertEqual(self.profile().role_history, [])
        application.refresh_from_db()
        self.assertTrue(application.access_update_pending)

    def test_rejected_elevated_account_stays_blocked_until_audited_admin_repair(self):
        set_role(self.target, Role.OFFICER, actor=self.admin)
        self.target.is_active = False
        self.target.save(update_fields=["is_active"])
        application = MembershipApplication.objects.create(user=self.target, statement="Legacy pending application")
        with self.assertRaisesMessage(ValueError, "administrator must restore Applicant"):
            application.review(self.officer, False, "Not approved")
        application.refresh_from_db()
        decision = (application.status, application.reviewed_by_id, application.reviewed_at, application.review_note)
        self.assertEqual(application.status, ApplicationStatus.REJECTED)
        self.assertTrue(application.access_update_pending)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        with self.assertRaises(RoleChangeBlocked):
            set_role(self.target, Role.APPLICANT, actor=self.officer, reconcile_rejected=True)
        self.client.force_login(self.admin)
        self.client.post(self.url(), {"role": Role.APPLICANT, "version": 1})
        corrected = self.profile()
        self.assertEqual(corrected.role, Role.APPLICANT)
        self.assertEqual(corrected.role_history[-1]["source"], "rejected_membership_reconciliation")
        self.assertEqual(corrected.role_history[-1]["actor_id"], str(self.admin.pk))
        application.refresh_from_db()
        self.assertTrue(application.access_update_pending)
        self.assertEqual((application.status, application.reviewed_by_id, application.reviewed_at, application.review_note), decision)
        application.complete_access_update()
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertFalse(application.access_update_pending)
        self.assertEqual(len(self.profile().role_history), 2)

    def test_rejected_reconciliation_cannot_grant_a_role_or_change_another_pending_state(self):
        set_role(self.target, Role.OFFICER, actor=self.admin)
        application = MembershipApplication.objects.create(
            user=self.target, statement="Rejected", status=ApplicationStatus.REJECTED,
            access_update_pending=True, reviewed_by=self.officer,
        )
        with self.assertRaises(RoleChangeBlocked):
            set_role(self.target, Role.ADMIN, actor=self.admin, reconcile_rejected=True)
        MembershipApplication.objects.create(user=self.target, statement="Unreviewed")
        with self.assertRaises(RoleChangeBlocked):
            set_role(self.target, Role.APPLICANT, actor=self.admin, reconcile_rejected=True)
        self.assertEqual(self.profile().role, Role.OFFICER)
        self.assertEqual(len(self.profile().role_history), 1)

    def test_rejected_reconciliation_cannot_change_self_or_superuser(self):
        MembershipApplication.objects.create(
            user=self.admin, statement="Legacy own application", status=ApplicationStatus.REJECTED,
            access_update_pending=True, reviewed_by=self.officer,
        )
        with self.assertRaises(RoleChangeBlocked):
            set_role(self.admin, Role.APPLICANT, actor=self.admin, reconcile_rejected=True)
        root = User.objects.create_superuser("audit-root", "audit-root@example.com", "unused-password")
        MembershipApplication.objects.create(
            user=root, statement="Legacy root application", status=ApplicationStatus.REJECTED,
            access_update_pending=True, reviewed_by=self.officer,
        )
        with self.assertRaisesMessage(ValueError, "Superusers must remain admins"):
            set_role(root, Role.APPLICANT, actor=self.admin, reconcile_rejected=True)
        self.assertEqual(Profile.objects.get(user=root).role, Role.ADMIN)

    def make_legacy_profile(self, role=Role.APPLICANT):
        Profile.objects.filter(user=self.target).delete()
        state = MigrationLoader(connection).project_state([("accounts", "0004_profile_is_suspended")])
        LegacyProfile = state.apps.get_model("accounts", "Profile")
        LegacyProfile.objects.create(user_id=self.target.pk, role=role, is_suspended=False)
        return state

    def test_initial_audit_migration_preserves_legacy_roles_and_does_not_invent_history(self):
        state = self.make_legacy_profile(Role.OFFICER)
        migration = import_module("accounts.migrations.0005_profile_role_audit").Migration("0005_profile_role_audit", "accounts")
        with connection.schema_editor() as editor:
            for operation in migration.operations:
                old_state = state.clone()
                operation.state_forwards("accounts", state)
                operation.database_forwards("accounts", editor, old_state, state)
        current = self.profile()
        self.assertEqual(current.role, Role.OFFICER)
        self.assertEqual(current.role_version, 0)
        self.assertEqual(current.role_history, [])
        changed = set_role(self.target, Role.ADMIN, actor=self.admin)
        self.assertEqual(changed.role_version, 1)
        self.assertEqual(changed.role_history[0]["old_role"], Role.OFFICER)

    def test_legacy_missing_audit_fields_can_be_conditionally_upgraded(self):
        self.make_legacy_profile()
        changed = set_role(self.target, Role.MEMBER, actor=self.admin)
        self.assertEqual(changed.role_version, 1)
        self.assertEqual(len(changed.role_history), 1)
        self.assertEqual(changed.role_history[0]["old_role"], Role.APPLICANT)
