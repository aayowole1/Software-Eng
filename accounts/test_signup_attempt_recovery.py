"""Crash recovery uses durable, exact ownership evidence and never grants access."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from unittest.mock import patch

from bson import ObjectId
from django.contrib.auth import authenticate, get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, connections
from django.db.models.query import QuerySet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from membership.models import ApplicationStatus, MembershipApplication

from .forms import PasswordSignupRetryError, RegisterForm
from .google_auth import GoogleSignupRetryError, create_google_applicant
from .models import GoogleIdentity, Profile, Role
from .provisioning import SignupRecoveryRefused, complete_signup, inspect_signup, repair_signup, reserve_signup
from .signup_attempts import SignupAttempt

User = get_user_model()
PASSWORD = "Strong-signup-recovery!2026"


class ProcessExited(BaseException):
    """Model an abrupt process exit that request exception handlers cannot clean."""


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SignupAttemptRecoveryTests(TestCase):
    def incomplete(self, channel="password", *, missing_profile=False):
        attempt = reserve_signup(
            channel, "recovery_applicant", "recovery@example.com", "Original application statement.",
            "verified-recovery-subject" if channel == "google" else "",
        )
        user = User.objects.create_user(
            pk=attempt.reserved_user_id, username=attempt.username, email=attempt.email,
            password=PASSWORD if channel == "password" else None, is_active=False,
        )
        if missing_profile:
            Profile.objects.filter(user=user).delete()
        return attempt, user

    def command(self, attempt, *flags):
        output = StringIO()
        call_command("repair_signup", str(attempt.pk), *flags, stdout=output)
        return output.getvalue()

    def assert_pending_inactive(self, attempt, user):
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(Profile.objects.get(user=user).role, Role.APPLICANT)
        application = MembershipApplication.objects.get(user=user)
        self.assertEqual(application.pk, attempt.application_id)
        self.assertEqual(application.statement, attempt.statement)
        self.assertEqual(application.status, ApplicationStatus.PENDING)
        self.assertIsNone(application.reviewed_by_id)
        self.assertIsNone(application.reviewed_at)
        self.assertFalse(application.access_update_pending)
        self.assertIsNone(authenticate(username=user.username, password=PASSWORD))

    def test_default_command_is_read_only_and_requires_stopped_workers_to_apply(self):
        attempt, user = self.incomplete(missing_profile=True)
        output = self.command(attempt)
        self.assertIn("DRY RUN", output)
        self.assertIn("create missing Applicant profile", output)
        self.assertFalse(Profile.objects.filter(user=user).exists())
        self.assertFalse(MembershipApplication.objects.exists())
        with self.assertRaisesMessage(CommandError, "Stop registration workers first"):
            self.command(attempt, "--apply")
        attempt.refresh_from_db()
        self.assertEqual(attempt.state, SignupAttempt.State.PENDING)

    def test_password_orphan_restored_once_without_changing_password_or_granting_access(self):
        attempt, user = self.incomplete(missing_profile=True)
        password_hash = user.password
        self.assertIn("completed", self.command(attempt, "--apply", "--workers-stopped"))
        self.assert_pending_inactive(attempt, user)
        self.assertEqual(user.password, password_hash)
        self.assertEqual(MembershipApplication.objects.count(), 1)
        self.command(attempt, "--apply", "--workers-stopped")
        self.assertEqual(MembershipApplication.objects.count(), 1)

    def test_google_orphan_restores_only_recorded_verified_subject_and_pending_application(self):
        attempt, user = self.incomplete("google", missing_profile=True)
        repair_signup(attempt)
        self.assert_pending_inactive(attempt, user)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(GoogleIdentity.objects.get(user=user).subject, attempt.google_subject)
        repair_signup(attempt)
        self.assertEqual(GoogleIdentity.objects.count(), 1)

    def test_process_exit_before_password_application_retains_ownership_and_repair_works(self):
        form = RegisterForm({
            "username": "interrupted", "email": "interrupted@example.com", "password": PASSWORD,
            "confirm_password": PASSWORD, "statement": "Preserve this statement.",
        })
        self.assertTrue(form.is_valid(), form.errors)
        with patch("accounts.forms.MembershipApplication.objects.create", side_effect=ProcessExited):
            with self.assertRaises(ProcessExited):
                form.save()
        attempt = SignupAttempt.objects.get()
        user = User.objects.get(pk=attempt.reserved_user_id)
        self.assertFalse(MembershipApplication.objects.exists())
        repair_signup(attempt)
        self.assert_pending_inactive(attempt, user)

    def test_process_exit_during_google_profile_signal_can_restore_full_original_signup(self):
        with patch("accounts.signals.Profile.objects.get_or_create", side_effect=ProcessExited):
            with self.assertRaises(ProcessExited):
                create_google_applicant("original-verified-subject", "crash@example.com", "Original Google statement.")
        attempt = SignupAttempt.objects.get()
        user = User.objects.get(pk=attempt.reserved_user_id)
        repair_signup(attempt)
        self.assert_pending_inactive(attempt, user)
        self.assertEqual(GoogleIdentity.objects.get(user=user).subject, "original-verified-subject")

    def test_profile_repair_failure_leaves_pending_then_retry_succeeds(self):
        attempt, user = self.incomplete(missing_profile=True)
        with patch("accounts.provisioning.Profile.objects.get_or_create", side_effect=OperationalError("secret")):
            with self.assertRaisesMessage(CommandError, "database could not confirm"):
                self.command(attempt, "--apply", "--workers-stopped")
        self.assertEqual(SignupAttempt.objects.get(pk=attempt.pk).state, "pending")
        self.command(attempt, "--apply", "--workers-stopped")
        self.assert_pending_inactive(attempt, user)

    def test_google_link_repair_failure_is_retryable_without_duplicate_user(self):
        attempt, user = self.incomplete("google")
        with patch("accounts.provisioning.GoogleIdentity.objects.get_or_create", side_effect=OperationalError("secret")):
            with self.assertRaises(OperationalError):
                repair_signup(attempt)
        repair_signup(attempt)
        self.assertEqual(User.objects.count(), 1)
        self.assert_pending_inactive(attempt, user)

    def test_application_repair_failure_and_final_stamp_failure_retry_without_duplicates(self):
        attempt, user = self.incomplete()
        with patch("accounts.provisioning.MembershipApplication.objects.get_or_create", side_effect=OperationalError("secret")):
            with self.assertRaises(OperationalError):
                repair_signup(attempt)
        with patch("accounts.provisioning.complete_signup", side_effect=OperationalError("secret")):
            with self.assertRaises(OperationalError):
                repair_signup(attempt)
        self.assertEqual(MembershipApplication.objects.count(), 1)
        self.assertEqual(SignupAttempt.objects.get(pk=attempt.pk).state, "pending")
        repair_signup(attempt)
        self.assert_pending_inactive(attempt, user)
        self.assertEqual(MembershipApplication.objects.count(), 1)

    def test_existing_inserted_original_application_is_preserved(self):
        attempt, user = self.incomplete()
        application = MembershipApplication.objects.create(
            pk=attempt.application_id, user=user, statement=attempt.statement,
        )
        application.refresh_from_db()  # Compare stored MongoDB millisecond precision.
        submitted_at = application.submitted_at
        repair_signup(attempt)
        application.refresh_from_db()
        self.assertEqual(application.submitted_at, submitted_at)
        self.assert_pending_inactive(attempt, user)

    def test_parallel_repairs_share_reserved_application_key(self):
        attempt, user = self.incomplete()
        barrier = Barrier(2)
        original = Profile.objects.get_or_create

        def synchronized(**kwargs):
            barrier.wait(timeout=10)
            return original(**kwargs)

        def worker():
            try:
                return repair_signup(SignupAttempt.objects.get(pk=attempt.pk))["state"]
            finally:
                connections.close_all()

        with patch("accounts.provisioning.Profile.objects.get_or_create", side_effect=synchronized):
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(list(pool.map(lambda _: worker(), range(2))), ["completed", "completed"])
        self.assertEqual(MembershipApplication.objects.count(), 1)
        self.assert_pending_inactive(attempt, user)

    def test_refuses_active_staff_superuser_elevated_suspended_and_audited_accounts(self):
        attempt, user = self.incomplete()
        for user_field in ("is_active", "is_staff", "is_superuser"):
            with self.subTest(user_field=user_field):
                User.objects.filter(pk=user.pk).update(**{user_field: True})
                with self.assertRaises(SignupRecoveryRefused):
                    inspect_signup(attempt)
                User.objects.filter(pk=user.pk).update(**{user_field: False})
        for values in (
            {"role": Role.MEMBER}, {"is_suspended": True}, {"suspension_update_pending": True},
            {"role_version": 1}, {"role_history": [{"source": "earlier_change"}]},
        ):
            with self.subTest(values=values):
                Profile.objects.filter(user=user).update(**values)
                with self.assertRaises(SignupRecoveryRefused):
                    repair_signup(attempt)
                Profile.objects.filter(user=user).update(
                    role=Role.APPLICANT, is_suspended=False, suspension_update_pending=False,
                    role_version=0, role_history=[],
                )
        self.assertFalse(MembershipApplication.objects.exists())

    def test_refuses_changed_identity_existing_other_application_and_reviewed_decision(self):
        attempt, user = self.incomplete()
        User.objects.filter(pk=user.pk).update(email="changed@example.com")
        with self.assertRaises(SignupRecoveryRefused):
            repair_signup(attempt)
        User.objects.filter(pk=user.pk).update(email=attempt.email)
        other = MembershipApplication.objects.create(user=user, statement=attempt.statement)
        with self.assertRaises(SignupRecoveryRefused):
            repair_signup(attempt)
        other.delete()
        application = MembershipApplication.objects.create(
            pk=attempt.application_id, user=user, statement=attempt.statement,
            status=ApplicationStatus.REJECTED, review_note="Original decision",
        )
        with self.assertRaises(SignupRecoveryRefused):
            repair_signup(attempt)
        application.refresh_from_db()
        self.assertEqual(application.status, ApplicationStatus.REJECTED)
        self.assertEqual(application.review_note, "Original decision")
        self.assertFalse(User.objects.get(pk=user.pk).is_active)

    def test_previous_login_or_finished_suspension_history_refuses_an_otherwise_inactive_applicant(self):
        attempt, user = self.incomplete()
        User.objects.filter(pk=user.pk).update(last_login=timezone.now())
        with self.assertRaises(SignupRecoveryRefused):
            repair_signup(attempt)
        User.objects.filter(pk=user.pk).update(last_login=None)
        for values in (
            {"suspension_version": 2}, {"suspension_was_active": False}, {"suspension_restore_active": False},
        ):
            with self.subTest(values=values):
                Profile.objects.filter(user=user).update(**values)
                with self.assertRaises(SignupRecoveryRefused):
                    repair_signup(attempt)
                Profile.objects.filter(user=user).update(
                    suspension_version=0, suspension_was_active=None, suspension_restore_active=None,
                )
        self.assertFalse(MembershipApplication.objects.exists())
        self.assertEqual(SignupAttempt.objects.get(pk=attempt.pk).state, "pending")

    def test_google_subject_owned_by_other_account_is_never_relinked(self):
        attempt, user = self.incomplete("google")
        other = User.objects.create_user(username="other", email="other@example.com", password=None)
        identity = GoogleIdentity.objects.create(subject=attempt.google_subject, user=other)
        with self.assertRaises(SignupRecoveryRefused):
            repair_signup(attempt)
        identity.refresh_from_db()
        self.assertEqual(identity.user_id, other.pk)
        self.assertFalse(MembershipApplication.objects.exists())

    def test_refuses_group_permissions_and_domain_records(self):
        from django.contrib.auth.models import Group
        from tasks.models import Task

        attempt, user = self.incomplete()
        group = Group.objects.create(name="legacy permissions")
        user.groups.add(group)
        with self.assertRaises(SignupRecoveryRefused):
            repair_signup(attempt)
        user.groups.clear()
        Task.objects.create(title="Existing app activity", created_by=user)
        with self.assertRaises(SignupRecoveryRefused):
            repair_signup(attempt)
        self.assertFalse(MembershipApplication.objects.exists())

    def test_unmarked_missing_and_compensated_attempts_never_create_or_delete_a_user(self):
        with self.assertRaisesMessage(CommandError, "No recorded signup attempt"):
            call_command("repair_signup", str(ObjectId()))
        attempt = reserve_signup("password", "notcreated", "notcreated@example.com", "No user was inserted.")
        with self.assertRaisesMessage(CommandError, "reserved account does not exist"):
            self.command(attempt, "--apply", "--workers-stopped")
        SignupAttempt.objects.filter(pk=attempt.pk).update(state="compensated")
        with self.assertRaisesMessage(CommandError, "was compensated"):
            self.command(attempt, "--apply", "--workers-stopped")
        self.assertFalse(User.objects.exists())

    def test_journal_contains_no_password_or_provider_token_and_command_output_has_no_identity(self):
        attempt, _ = self.incomplete("google")
        fields = {field.name for field in SignupAttempt._meta.fields}
        self.assertFalse(fields & {"password", "credential", "token", "access_token", "id_token"})
        output = self.command(attempt)
        for private in (attempt.username, attempt.email, attempt.statement, attempt.google_subject, PASSWORD):
            self.assertNotIn(private, output)

    def password_form(self):
        form = RegisterForm({
            "username": "new_applicant", "email": "new_applicant@example.com", "password": PASSWORD,
            "confirm_password": PASSWORD, "statement": "Preserve the normal signup statement.",
        })
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def test_normal_password_and_google_attempts_complete_only_with_original_application(self):
        local = self.password_form().save()
        google = create_google_applicant("normal-subject", "normal-google@example.com", "Google statement.")
        for user in (local, google):
            attempt = SignupAttempt.objects.get(reserved_user_id=user.pk)
            self.assertEqual(attempt.state, "completed")
            self.assertIsNotNone(attempt.completed_at)
            self.assertEqual(MembershipApplication.objects.get(user=user).pk, attempt.application_id)
            self.assert_pending_inactive(attempt, user)

    def test_journal_write_failure_creates_no_user_or_other_signup_records(self):
        form = self.password_form()
        with patch("accounts.provisioning.SignupAttempt.objects.create", side_effect=OperationalError("private credentials")):
            with self.assertRaises(PasswordSignupRetryError):
                form.save()
            with self.assertRaises(GoogleSignupRetryError):
                create_google_applicant("not-journaled", "not-journaled@example.com", "Statement")
        self.assertFalse(User.objects.exists())
        self.assertFalse(SignupAttempt.objects.exists())
        self.assertFalse(MembershipApplication.objects.exists())
        self.assertFalse(GoogleIdentity.objects.exists())

    def test_failed_request_compensation_retains_attempt_reference_and_can_be_repaired(self):
        form = self.password_form()
        with (
            patch("accounts.signals.Profile.objects.get_or_create", side_effect=OperationalError("private details")),
            patch("django.db.models.query.QuerySet.delete", side_effect=OperationalError("private credentials")),
            self.assertLogs("accounts.provisioning", level="ERROR") as logs,
        ):
            with self.assertRaises(PasswordSignupRetryError):
                form.save()
        attempt = SignupAttempt.objects.get()
        self.assertIn(str(attempt.pk), logs.output[0])
        self.assertNotIn(attempt.email, logs.output[0])
        self.assertNotIn("private", logs.output[0])
        self.assertEqual(attempt.state, "pending")
        user = User.objects.get(pk=attempt.reserved_user_id)
        repair_signup(attempt)
        self.assert_pending_inactive(attempt, user)

    def test_lost_completion_acknowledgement_preserves_original_complete_inactive_signup(self):
        form = self.password_form()

        def stamped_then_failed(attempt):
            complete_signup(attempt)
            raise OperationalError("private lost acknowledgement")

        with patch("accounts.forms.complete_signup", side_effect=stamped_then_failed):
            with self.assertRaises(PasswordSignupRetryError):
                form.save()
        attempt = SignupAttempt.objects.get()
        user = User.objects.get()
        self.assertEqual(attempt.state, "completed")
        self.assert_pending_inactive(attempt, user)
        self.assertEqual(repair_signup(attempt)["actions"], [])

    def test_google_exit_after_identity_insert_keeps_exact_link_during_repair(self):
        with patch("accounts.google_auth.MembershipApplication.objects.create", side_effect=ProcessExited):
            with self.assertRaises(ProcessExited):
                create_google_applicant("already-linked-subject", "linked@example.com", "Original linked statement.")
        attempt = SignupAttempt.objects.get()
        identity = GoogleIdentity.objects.get()
        self.assertEqual(identity.user_id, attempt.reserved_user_id)
        repair_signup(attempt)
        self.assertEqual(GoogleIdentity.objects.get().pk, identity.pk)
        self.assert_pending_inactive(attempt, User.objects.get(pk=attempt.reserved_user_id))

    def test_real_username_and_email_index_races_show_conflict_feedback_not_outage_retry(self):
        for field in ("username", "email"):
            with self.subTest(field=field):
                payload = {
                    "username": "race_applicant", "email": "race_applicant@example.com",
                    "password": PASSWORD, "confirm_password": PASSWORD, "statement": "Original statement.",
                }
                winner = []

                def concurrent_winner(*args, **kwargs):
                    attempt = reserve_signup(*args, **kwargs)
                    winner.append(User.objects.create_user(
                        username="RACE_APPLICANT" if field == "username" else "other_winner",
                        email="other_winner@example.com" if field == "username" else "RACE_APPLICANT@example.com",
                        password=PASSWORD,
                    ))
                    return attempt

                with patch("accounts.forms.reserve_signup", side_effect=concurrent_winner):
                    response = self.client.post(reverse("accounts:register"), payload)
                self.assertContains(response, "Try a different username or email, or sign in.", status_code=200)
                self.assertNotContains(response, "Please try submitting it again.")
                self.assertNotContains(response, "E11000")
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertEqual(User.objects.get().pk, winner[0].pk)
                self.assertFalse(MembershipApplication.objects.exists())
                self.assertEqual(SignupAttempt.objects.order_by("-created_at").first().state, "compensated")
                winner[0].delete()

    def test_completion_lost_ack_never_runs_partial_child_cleanup_for_either_channel(self):
        original_delete = QuerySet.delete
        deleted_users = []

        def stamped_then_failed(attempt):
            complete_signup(attempt)
            raise OperationalError("private lost completion acknowledgement")

        def children_deleted_then_failed(queryset, *args, **kwargs):
            if queryset.model is User:
                user = queryset.get()
                deleted_users.append(user.pk)
                original_delete(MembershipApplication.objects.filter(user=user))
                raise OperationalError("private failure before User deletion")
            return original_delete(queryset, *args, **kwargs)

        for channel in ("password", "google"):
            with self.subTest(channel=channel):
                target = "accounts.forms.complete_signup" if channel == "password" else "accounts.google_auth.complete_signup"
                with (
                    patch(target, side_effect=stamped_then_failed),
                    patch.object(QuerySet, "delete", new=children_deleted_then_failed),
                ):
                    error = PasswordSignupRetryError if channel == "password" else GoogleSignupRetryError
                    with self.assertRaises(error):
                        if channel == "password":
                            self.password_form().save()
                        else:
                            create_google_applicant("lost-ack-subject", "lost-ack@example.com", "Original Google statement.")
                attempt = SignupAttempt.objects.get(channel=channel)
                user = User.objects.get(pk=attempt.reserved_user_id)
                self.assertEqual(attempt.state, "completed")
                self.assertEqual(deleted_users, [])
                self.assertTrue(MembershipApplication.objects.filter(user=user).exists())
                repair_signup(attempt)
                self.assert_pending_inactive(attempt, user)

    def test_uncertain_early_compensation_intent_never_deletes_reserved_user_for_either_channel(self):
        original_update = QuerySet.update

        for channel in ("password", "google"):
            for intent_committed in (False, True):
                with self.subTest(channel=channel, intent_committed=intent_committed):
                    def uncertain_intent(queryset, **values):
                        if queryset.model is SignupAttempt and values.get("state") == "pending":
                            if intent_committed:
                                original_update(queryset, **values)
                            raise OperationalError("private uncertain compensation intent")
                        return original_update(queryset, **values)

                    with (
                        patch("accounts.signals.Profile.objects.get_or_create", side_effect=OperationalError("private profile failure")),
                        patch.object(QuerySet, "update", new=uncertain_intent),
                        patch.object(QuerySet, "delete", side_effect=AssertionError("cleanup must not run")) as deletion,
                    ):
                        error = PasswordSignupRetryError if channel == "password" else GoogleSignupRetryError
                        with self.assertRaises(error):
                            if channel == "password":
                                self.password_form().save()
                            else:
                                create_google_applicant("uncertain-subject", "uncertain@example.com", "Original Google statement.")
                        deletion.assert_not_called()
                    user = User.objects.get()
                    attempt = SignupAttempt.objects.get(reserved_user_id=user.pk)
                    self.assertEqual(attempt.state, "pending")
                    self.assertFalse(user.is_active)
                    self.assertFalse(MembershipApplication.objects.filter(user=user).exists())
                    repair_signup(attempt)
                    self.assert_pending_inactive(attempt, user)
                    user.delete()

    def test_completed_review_before_lost_ack_is_preserved_for_both_signup_channels(self):
        officer = User.objects.create_user("reviewing_officer", "reviewer@example.com", PASSWORD)
        Profile.objects.filter(user=officer).update(role=Role.OFFICER)

        def stamped_reviewed_then_failed(attempt):
            complete_signup(attempt)
            application = MembershipApplication.objects.get(pk=attempt.application_id)
            application.review(officer, approve=True, note="Original approved decision")
            raise OperationalError("private lost completion acknowledgement")

        for channel in ("password", "google"):
            with self.subTest(channel=channel):
                target = "accounts.forms.complete_signup" if channel == "password" else "accounts.google_auth.complete_signup"
                with (
                    patch(target, side_effect=stamped_reviewed_then_failed),
                    patch.object(QuerySet, "delete", side_effect=AssertionError("reviewed account must be preserved")) as deletion,
                ):
                    error = PasswordSignupRetryError if channel == "password" else GoogleSignupRetryError
                    with self.assertRaises(error):
                        if channel == "password":
                            self.password_form().save()
                        else:
                            create_google_applicant("reviewed-subject", "reviewed@example.com", "Original Google statement.")
                    deletion.assert_not_called()
                attempt = SignupAttempt.objects.get(channel=channel)
                user = User.objects.get(pk=attempt.reserved_user_id)
                application = MembershipApplication.objects.get(pk=attempt.application_id)
                self.assertTrue(user.is_active)
                self.assertEqual(Profile.objects.get(user=user).role, Role.MEMBER)
                self.assertEqual(application.status, ApplicationStatus.APPROVED)
                self.assertEqual(application.reviewed_by_id, officer.pk)
                self.assertEqual(application.review_note, "Original approved decision")
                self.assertIsNotNone(application.reviewed_at)
                self.assertEqual(attempt.state, "completed")
                self.assertEqual(repair_signup(attempt)["actions"], [])

    def test_early_compensation_preserves_observed_admin_activation_or_role_change(self):
        original_profile = Profile.objects.get_or_create
        for changed_field in ("is_active", "role"):
            with self.subTest(changed_field=changed_field):
                def changed_then_failed(**kwargs):
                    profile, created = original_profile(**kwargs)
                    if changed_field == "is_active":
                        User.objects.filter(pk=profile.user_id).update(is_active=True)
                    else:
                        Profile.objects.filter(pk=profile.pk).update(role=Role.MEMBER)
                    raise OperationalError("private error after observed administrative change")

                with (
                    patch("accounts.signals.Profile.objects.get_or_create", side_effect=changed_then_failed),
                    patch.object(QuerySet, "delete", side_effect=AssertionError("changed account must be preserved")) as deletion,
                ):
                    with self.assertRaises(PasswordSignupRetryError):
                        self.password_form().save()
                    deletion.assert_not_called()
                user = User.objects.get()
                self.assertEqual(user.is_active, changed_field == "is_active")
                self.assertEqual(Profile.objects.get(user=user).role, Role.MEMBER if changed_field == "role" else Role.APPLICANT)
                user.delete()
