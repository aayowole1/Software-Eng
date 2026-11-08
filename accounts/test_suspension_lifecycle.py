"""Shared Accounts integration around TJ's suspension and membership flow."""

from datetime import timedelta
from importlib import import_module
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import DatabaseError, connection
from django.db.migrations.loader import MigrationLoader
from django.db.models.query import QuerySet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from membership.models import ApplicationStatus, MembershipApplication, purge_old_rejected_applications

from .backends import EmailOrUsernameBackend
from .google_auth import GoogleSignInError, _existing_identity_user
from .lifecycle import SuspensionConflict, apply_suspension
from .models import GoogleIdentity, Profile, Role, set_role
from .testing import make_user

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SuspensionLifecycleTests(TestCase):
    def setUp(self):
        self.admin = make_user("lifecycle-admin@example.com", Role.ADMIN)
        self.officer = make_user("lifecycle-officer@example.com", Role.OFFICER)
        self.target = make_user("lifecycle-target@example.com", Role.MEMBER)
        self.client.force_login(self.admin)

    def change(self, action, **extra):
        return self.client.post(
            reverse("accounts:change_suspension", args=[self.target.pk]),
            {"action": action, **extra},
        )

    def profile(self):
        return Profile.objects.get(user=self.target)

    def test_previously_active_account_without_application_is_restored(self):
        self.assertFalse(MembershipApplication.objects.filter(user=self.target).exists())
        self.change("suspend")
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_rejected_application_purge_does_not_erase_previous_activation(self):
        MembershipApplication.objects.create(
            user=self.target, statement="Historical rejection", status=ApplicationStatus.REJECTED,
            reviewed_by=self.officer, reviewed_at=timezone.now() - timedelta(days=8),
        )
        self.change("suspend")
        self.assertEqual(purge_old_rejected_applications(), 1)
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_deliberately_inactive_account_is_not_activated_by_old_completed_review(self):
        MembershipApplication.objects.create(
            user=self.target, statement="Old approval", status=ApplicationStatus.APPROVED,
            reviewed_by=self.officer,
        )
        self.target.is_active = False
        self.target.save(update_fields=["is_active"])
        self.change("suspend")
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_reinstatement_finishes_recorded_review_using_original_reviewer(self):
        Profile.objects.filter(user=self.target).update(role=Role.APPLICANT, role_history=[], role_version=0)
        self.target.is_active = False
        self.target.save(update_fields=["is_active"])
        application = MembershipApplication.objects.create(
            user=self.target, statement="Approved before suspension", status=ApplicationStatus.APPROVED,
            reviewed_by=self.officer, reviewed_at=timezone.now(), access_update_pending=True,
        )
        self.change("suspend")
        self.change("reinstate")
        application.refresh_from_db()
        self.assertFalse(application.access_update_pending)
        self.assertEqual(self.profile().role, Role.MEMBER)
        self.assertEqual(self.profile().role_history[0]["actor_id"], str(self.officer.pk))

    def fail_activation(self):
        original = User.save

        def save(user, *args, **kwargs):
            if user.pk == self.target.pk and "is_active" in (kwargs.get("update_fields") or ()):
                raise DatabaseError("Injected activation failure")
            return original(user, *args, **kwargs)
        return patch.object(User, "save", autospec=True, side_effect=save)

    def fail_final_stamp(self):
        original = QuerySet.update

        def update(queryset, **values):
            if queryset.model is Profile and values == {"suspension_update_pending": False}:
                raise DatabaseError("Injected final lifecycle stamp failure")
            return original(queryset, **values)
        return patch.object(QuerySet, "update", autospec=True, side_effect=update)

    def test_first_suspend_records_activation_and_repeat_preserves_it(self):
        apply_suspension(self.target, True, expected_version=0)
        first = self.profile()
        self.assertTrue(first.suspension_was_active)
        self.assertTrue(first.suspension_restore_active)
        self.assertFalse(first.suspension_update_pending)
        apply_suspension(self.target, True, expected_version=0)
        self.assertEqual(self.profile().suspension_version, first.suspension_version)
        apply_suspension(self.target, False, expected_version=first.suspension_version)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_inactive_no_application_account_remains_inactive(self):
        self.target.is_active = False
        self.target.save(update_fields=["is_active"])
        self.change("suspend")
        self.assertFalse(self.profile().suspension_was_active)
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_repeated_completed_reinstatement_does_not_undo_later_inactivation(self):
        self.change("suspend")
        self.change("reinstate")
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_new_suspension_cycle_captures_later_deliberate_inactivation(self):
        self.change("suspend")
        self.change("reinstate")
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        self.change("suspend")
        self.assertFalse(self.profile().suspension_was_active)
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_suspend_user_write_failure_keeps_snapshot_and_retry_is_safe(self):
        with self.fail_activation():
            response = self.change("suspend")
        notices = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("could not be confirmed", notices)
        self.assertNotIn("suspended.", notices)
        self.assertTrue(self.profile().is_suspended)
        self.assertTrue(self.profile().suspension_was_active)
        self.assertTrue(self.profile().suspension_update_pending)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertFalse(EmailOrUsernameBackend().user_can_authenticate(self.target))
        self.change("suspend")
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertFalse(self.profile().suspension_update_pending)

    def test_reinstatement_user_write_failure_leaves_retry_visible(self):
        self.change("suspend")
        with self.fail_activation():
            self.change("reinstate")
        self.assertFalse(self.profile().is_suspended)
        self.assertTrue(self.profile().suspension_update_pending)
        self.assertContains(self.client.get(reverse("accounts:user_list")), "Finish reinstatement")
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertFalse(self.profile().suspension_update_pending)

    def test_final_stamp_failure_blocks_password_google_and_task_access_until_retry(self):
        from tasks.models import active_role, eligible_assignees

        GoogleIdentity.objects.create(subject="lifecycle-subject", user=self.target)
        self.change("suspend")
        with self.fail_final_stamp():
            self.change("reinstate")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertTrue(self.profile().suspension_update_pending)
        self.assertFalse(EmailOrUsernameBackend().user_can_authenticate(self.target))
        with self.assertRaisesMessage(GoogleSignInError, "account access is still being updated"):
            _existing_identity_user("lifecycle-subject")
        self.assertIsNone(active_role(self.target))
        self.assertFalse(eligible_assignees().filter(pk=self.target.pk).exists())
        self.change("reinstate")
        self.assertTrue(EmailOrUsernameBackend().user_can_authenticate(self.target))
        self.assertEqual(active_role(self.target), Role.MEMBER)

    def test_completed_review_activation_intent_survives_failed_lifecycle_final_stamp(self):
        Profile.objects.filter(user=self.target).update(role=Role.APPLICANT, role_history=[], role_version=0)
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        application = MembershipApplication.objects.create(
            user=self.target, statement="Approved", status=ApplicationStatus.APPROVED,
            reviewed_by=self.officer, access_update_pending=True,
        )
        self.change("suspend")
        with self.fail_final_stamp():
            self.change("reinstate")
        application.refresh_from_db()
        self.assertFalse(application.access_update_pending)
        self.assertFalse(self.profile().suspension_was_active)
        self.assertTrue(self.profile().suspension_restore_active)
        self.assertTrue(self.profile().suspension_update_pending)
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertEqual(len(self.profile().role_history), 1)

    def test_recorded_rejection_can_finish_without_changing_original_reviewer(self):
        Profile.objects.filter(user=self.target).update(role=Role.APPLICANT)
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        application = MembershipApplication.objects.create(
            user=self.target, statement="Rejected", status=ApplicationStatus.REJECTED,
            reviewed_by=self.officer, review_note="Original reason", access_update_pending=True,
        )
        self.change("suspend")
        self.change("reinstate")
        application.refresh_from_db()
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertFalse(application.access_update_pending)
        self.assertEqual(application.reviewed_by_id, self.officer.pk)
        self.assertEqual(application.review_note, "Original reason")
        self.assertEqual(self.profile().role, Role.APPLICANT)

    def test_failed_membership_completion_stays_blocked_and_retries_original_decision(self):
        Profile.objects.filter(user=self.target).update(role=Role.APPLICANT, role_history=[], role_version=0)
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        application = MembershipApplication.objects.create(
            user=self.target, statement="Approved", status=ApplicationStatus.APPROVED,
            reviewed_by=self.officer, access_update_pending=True,
        )
        self.change("suspend")
        with self.fail_activation():
            self.change("reinstate")
        application.refresh_from_db()
        self.assertTrue(application.access_update_pending)
        self.assertTrue(self.profile().suspension_update_pending)
        self.change("reinstate")
        application.refresh_from_db()
        self.assertFalse(application.access_update_pending)
        self.assertEqual(len(self.profile().role_history), 1)
        self.assertEqual(self.profile().role_history[0]["actor_id"], str(self.officer.pk))

    def test_pending_application_never_activates_during_reinstatement(self):
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        MembershipApplication.objects.create(user=self.target, statement="Not reviewed")
        self.change("suspend")
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)

    def test_stale_opposite_action_does_not_overwrite_saved_state(self):
        self.change("suspend", version=0)
        version = self.profile().suspension_version
        response = self.change("reinstate", version=0)
        notices = " ".join(str(message) for message in get_messages(response.wsgi_request))
        self.assertIn("changed while you were editing", notices)
        self.assertTrue(self.profile().is_suspended)
        self.assertEqual(self.profile().suspension_version, version)

    def test_role_audit_write_and_lifecycle_fields_do_not_overwrite_each_other(self):
        role_history = self.profile().role_history
        apply_suspension(self.target, True)
        set_role(self.target, Role.OFFICER, actor=self.admin)
        apply_suspension(self.target, False)
        current = self.profile()
        self.assertEqual(current.role, Role.OFFICER)
        self.assertEqual(len(current.role_history), len(role_history) + 1)
        self.assertTrue(current.suspension_was_active)
        self.assertFalse(current.is_suspended)

    def test_legacy_unknown_snapshot_never_guesses_activation_from_old_review(self):
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        Profile.objects.filter(user=self.target).update(is_suspended=True)
        MembershipApplication.objects.create(
            user=self.target, statement="Old approval", status=ApplicationStatus.APPROVED,
            reviewed_by=self.officer,
        )
        self.change("reinstate")
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertIsNone(self.profile().suspension_was_active)

    def test_snapshot_migration_preserves_legacy_roles_activation_and_unknown_history(self):
        Profile.objects.filter(user=self.target).delete()
        state = MigrationLoader(connection).project_state([("accounts", "0006_canonical_account_identifiers")])
        LegacyProfile = state.apps.get_model("accounts", "Profile")
        LegacyProfile.objects.create(user_id=self.target.pk, role=Role.MEMBER, is_suspended=True)
        migration = import_module("accounts.migrations.0007_suspension_activation_snapshot").Migration(
            "0007_suspension_activation_snapshot", "accounts",
        )
        with connection.schema_editor() as editor:
            for operation in migration.operations:
                old_state = state.clone()
                operation.state_forwards("accounts", state)
                operation.database_forwards("accounts", editor, old_state, state)
        current = self.profile()
        self.assertTrue(current.is_suspended)
        self.assertEqual(current.role, Role.MEMBER)
        self.assertIsNone(current.suspension_was_active)
        self.assertIsNone(current.suspension_restore_active)
        self.assertEqual(current.suspension_version, 0)
        self.assertFalse(current.suspension_update_pending)

    def test_competing_first_suspend_cannot_overwrite_original_snapshot(self):
        original = QuerySet.update
        interleaved = False

        def update(queryset, **values):
            nonlocal interleaved
            if queryset.model is Profile and values.get("is_suspended") is True and not interleaved:
                interleaved = True
                apply_suspension(self.target, True)
            return original(queryset, **values)

        with patch.object(QuerySet, "update", autospec=True, side_effect=update):
            with self.assertRaises(SuspensionConflict):
                apply_suspension(self.target, True)
        current = self.profile()
        self.assertTrue(current.suspension_was_active)
        self.assertTrue(current.is_suspended)
        self.assertEqual(current.suspension_version, 1)
        self.assertFalse(current.suspension_update_pending)

    def test_late_user_write_requires_current_action_retry_without_replacing_snapshot(self):
        original = User.save
        interleaved = False

        def save(user, *args, **kwargs):
            nonlocal interleaved
            if user.pk == self.target.pk and "is_active" in (kwargs.get("update_fields") or ()) and not interleaved:
                interleaved = True
                apply_suspension(self.target, False, expected_version=1)
            return original(user, *args, **kwargs)

        with patch.object(User, "save", autospec=True, side_effect=save):
            with self.assertRaises(SuspensionConflict):
                apply_suspension(self.target, True)
        current = self.profile()
        self.assertFalse(current.is_suspended)
        self.assertTrue(current.suspension_was_active)
        self.assertTrue(current.suspension_update_pending)
        self.target.refresh_from_db()
        self.assertFalse(EmailOrUsernameBackend().user_can_authenticate(self.target))
        apply_suspension(self.target, False, expected_version=current.suspension_version)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        self.assertFalse(self.profile().suspension_update_pending)

    def test_unacknowledged_profile_reservation_retains_first_activation_on_retry(self):
        original = QuerySet.update

        def update(queryset, **values):
            result = original(queryset, **values)
            if queryset.model is Profile and values.get("is_suspended") is True:
                raise DatabaseError("Reservation saved but acknowledgement lost")
            return result

        with patch.object(QuerySet, "update", autospec=True, side_effect=update):
            with self.assertRaises(DatabaseError):
                apply_suspension(self.target, True)
        self.assertIsNone(self.profile().suspension_was_active)
        self.assertTrue(self.profile().suspension_update_pending)
        apply_suspension(self.target, True)
        apply_suspension(self.target, False)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_invalid_versions_and_stale_saved_user_cannot_invent_activation(self):
        for version in (-1, True):
            with self.subTest(version=version), self.assertRaises(ValueError):
                apply_suspension(self.target, True, expected_version=version)
        with self.assertRaises(ValueError):
            apply_suspension(self.target, "suspend")
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        apply_suspension(self.target, True)
        self.assertFalse(self.profile().suspension_was_active)

    def test_review_completed_before_first_suspension_reservation_is_captured(self):
        Profile.objects.filter(user=self.target).update(role=Role.APPLICANT, role_history=[], role_version=0)
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        application = MembershipApplication.objects.create(user=self.target, statement="Pending approval")
        original = QuerySet.update
        interleaved = False

        def update(queryset, **values):
            nonlocal interleaved
            if queryset.model is Profile and values.get("is_suspended") is True and not interleaved:
                interleaved = True
                application.review(self.officer, True)
            return original(queryset, **values)

        with patch.object(QuerySet, "update", autospec=True, side_effect=update):
            apply_suspension(self.target, True)
        self.assertTrue(self.profile().suspension_was_active)
        apply_suspension(self.target, False)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)
        application.refresh_from_db()
        self.assertFalse(application.access_update_pending)

    def test_new_review_is_blocked_during_reinstatement_then_can_finish_normally(self):
        Profile.objects.filter(user=self.target).update(role=Role.APPLICANT, role_history=[], role_version=0)
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        application = MembershipApplication.objects.create(user=self.target, statement="Pending approval")
        apply_suspension(self.target, True)
        from . import lifecycle
        restore = lifecycle._restore_membership_access

        def interleave(profile, user):
            with self.assertRaisesMessage(ValueError, "unfinished suspension update"):
                application.review(self.officer, True)
            return restore(profile, user)

        with patch.object(lifecycle, "_restore_membership_access", side_effect=interleave):
            apply_suspension(self.target, False)
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.PENDING)
        application.review(self.officer, True)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_ordinary_completion_cannot_clear_review_intent_during_lifecycle_update(self):
        Profile.objects.filter(user=self.target).update(
            role=Role.APPLICANT, role_history=[], role_version=0,
            suspension_update_pending=True, suspension_version=5,
        )
        User.objects.filter(pk=self.target.pk).update(is_active=False)
        application = MembershipApplication.objects.create(
            user=self.target, statement="Already approved", status=ApplicationStatus.APPROVED,
            reviewed_by=self.officer, access_update_pending=True,
        )
        for kwargs in ({}, {"suspension_version": 4}, {"suspension_version": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                application.complete_access_update(**kwargs)
        application.refresh_from_db()
        self.assertTrue(application.access_update_pending)
        self.assertEqual(self.profile().role, Role.APPLICANT)
        apply_suspension(self.target, False, expected_version=5)
        application.refresh_from_db()
        self.target.refresh_from_db()
        self.assertFalse(application.access_update_pending)
        self.assertTrue(self.target.is_active)
