"""HTTP regressions for committee metadata and per-committee role changes."""

from unittest.mock import patch

from bson import ObjectId

from django.db import OperationalError
from django.db.models.query import QuerySet
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile, Role
from accounts.testing import make_user
from membership.models import ApplicationStatus, MembershipApplication
from tasks.models import Task, can_manage_tasks
from tasks.services import create_task

from .models import Committee, CommitteeMember, CommitteeRole


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CommitteeUpdateTests(TestCase):
    def setUp(self):
        self.officer = make_user("committee-update-officer@example.invalid", Role.OFFICER)
        self.admin = make_user("committee-update-admin@example.invalid", Role.ADMIN)
        self.member = make_user("committee-update-member@example.invalid", Role.MEMBER)
        self.chair = make_user("committee-update-chair@example.invalid", Role.MEMBER)
        self.applicant = make_user("committee-update-applicant@example.invalid")
        self.committee = Committee.objects.create(
            name="Outreach", description="Original description", created_by=self.officer,
        )
        self.other = Committee.objects.create(name="Finance", created_by=self.admin)
        self.membership = CommitteeMember.objects.create(
            committee=self.committee, user=self.member, role=CommitteeRole.MEMBER,
        )
        CommitteeMember.objects.create(
            committee=self.committee, user=self.chair, role=CommitteeRole.CHAIR,
        )
        self.client.force_login(self.officer)

    def edit_url(self, committee=None):
        return reverse("committees:edit", args=[(committee or self.committee).pk])

    def role_url(self, committee=None, user=None):
        return reverse(
            "committees:update_member_role",
            args=[(committee or self.committee).pk, (user or self.member).pk],
        )

    def edit_payload(self, client=None, committee=None, **changes):
        client = client or self.client
        committee = committee or self.committee
        response = client.get(self.edit_url(committee))
        self.assertEqual(response.status_code, 200)
        data = {
            "name": committee.name,
            "description": committee.description,
            "revision": response.context["form"].initial["revision"],
        }
        data.update(changes)
        return data

    def role_payload(self, client=None, committee=None, user=None, **changes):
        client = client or self.client
        committee = committee or self.committee
        user = user or self.member
        response = client.get(reverse("committees:detail", args=[committee.pk]))
        self.assertEqual(response.status_code, 200)
        row = next(row for row in response.context["roster"] if row.user_id == user.pk)
        data = {"role": row.role, "revision": row.role_form.initial["revision"]}
        data.update(changes)
        return data

    def saved_metadata(self):
        current = Committee.objects.get(pk=self.committee.pk)
        return (current.name, current.description, current.created_by_id, current.created_at)

    def saved_roster(self):
        return list(
            CommitteeMember.objects.filter(committee=self.committee).order_by("pk").values_list(
                "pk", "user_id", "role", "joined_at",
            )
        )

    def task_snapshot(self, task):
        return Task.objects.filter(pk=task.pk).values(
            "title", "description", "committee_id", "assignee_id", "created_by_id",
            "created_at", "updated_at", "due_date", "priority", "status", "version", "history",
        ).get()

    def test_officer_and_admin_can_edit_name_and_description_without_changing_roster_or_task(self):
        task = create_task(
            self.officer, title="Existing outreach work", committee=self.committee,
            assignee=self.member, description="Preserve task and history",
        )
        original_task, original_roster = self.task_snapshot(task), self.saved_roster()
        original_creator = self.saved_metadata()[2:]
        for index, actor in enumerate((self.officer, self.admin)):
            with self.subTest(actor=actor.username):
                self.client.force_login(actor)
                self.committee.refresh_from_db()
                data = self.edit_payload(name=f"Renamed outreach {index}", description=f"New description {index}")
                response = self.client.post(self.edit_url(), data)
                self.assertRedirects(response, reverse("committees:detail", args=[self.committee.pk]))
                self.assertEqual(self.saved_metadata()[:2], (data["name"], data["description"]))
                self.assertEqual(self.saved_metadata()[2:], original_creator)
                self.assertEqual(self.saved_roster(), original_roster)
                self.assertEqual(self.task_snapshot(task), original_task)

    def test_unchanged_name_and_valid_noop_do_not_report_a_duplicate(self):
        before = self.saved_metadata()
        response = self.client.post(self.edit_url(), self.edit_payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.saved_metadata(), before)
        response = self.client.post(self.edit_url(), self.edit_payload(description="Description only"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.saved_metadata()[:2], ("Outreach", "Description only"))

    def test_name_is_trimmed_and_case_insensitive_other_committee_duplicate_is_rejected(self):
        before = self.saved_metadata()
        response = self.client.post(self.edit_url(), self.edit_payload(name="  fINANCE  "))
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.context["form"].errors)
        self.assertEqual(self.saved_metadata(), before)
        response = self.client.post(self.edit_url(), self.edit_payload(name="  Outreach renamed  "))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.saved_metadata()[0], "Outreach renamed")

    def test_invalid_metadata_does_not_change_existing_values(self):
        before = self.saved_metadata()
        for invalid in ("", "   ", "x" * 101):
            with self.subTest(name=invalid):
                response = self.client.post(self.edit_url(), self.edit_payload(name=invalid, description="Must not save"))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.saved_metadata(), before)

    def test_member_chair_and_applicant_cannot_edit_or_change_another_members_role(self):
        edit_data, role_data = self.edit_payload(name="Forbidden"), self.role_payload(role=CommitteeRole.CHAIR)
        metadata, roster = self.saved_metadata(), self.saved_roster()
        for actor in (self.member, self.chair, self.applicant):
            with self.subTest(actor=actor.username):
                self.client.force_login(actor)
                self.assertEqual(self.client.get(self.edit_url()).status_code, 403)
                self.assertEqual(self.client.post(self.edit_url(), edit_data).status_code, 403)
                self.assertEqual(self.client.post(self.role_url(), role_data).status_code, 403)
                self.assertEqual(self.saved_metadata(), metadata)
                self.assertEqual(self.saved_roster(), roster)

    def test_anonymous_requests_require_signin_and_cannot_mutate(self):
        edit_data, role_data = self.edit_payload(name="Anonymous edit"), self.role_payload(role=CommitteeRole.CHAIR)
        metadata, roster = self.saved_metadata(), self.saved_roster()
        self.client.logout()
        for url, data in ((self.edit_url(), edit_data), (self.role_url(), role_data)):
            with self.subTest(url=url):
                response = self.client.post(url, data)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("accounts:login") + "?next="))
        self.assertEqual(self.saved_metadata(), metadata)
        self.assertEqual(self.saved_roster(), roster)

    def test_existing_officer_session_is_denied_after_suspension_or_pending_access(self):
        edit_data, role_data = self.edit_payload(name="Unavailable officer"), self.role_payload(role=CommitteeRole.CHAIR)
        metadata, roster = self.saved_metadata(), self.saved_roster()
        for flag in ("is_suspended", "suspension_update_pending", "access_update_pending"):
            with self.subTest(flag=flag):
                Profile.objects.filter(user=self.officer).update(is_suspended=False, suspension_update_pending=False)
                MembershipApplication.objects.filter(user=self.officer).delete()
                self.client.force_login(self.officer)
                if flag == "access_update_pending":
                    MembershipApplication.objects.create(
                        user=self.officer, statement="Unfinished recorded review",
                        status=ApplicationStatus.APPROVED, access_update_pending=True,
                    )
                else:
                    Profile.objects.filter(user=self.officer).update(**{flag: True})
                for url, data in ((self.edit_url(), edit_data), (self.role_url(), role_data)):
                    response = self.client.post(url, data)
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(response.url.startswith(reverse("accounts:login") + "?next="))
                self.assertEqual(self.saved_metadata(), metadata)
                self.assertEqual(self.saved_roster(), roster)

    def test_edit_rejects_other_methods_and_get_does_not_mutate(self):
        before = self.saved_metadata()
        self.assertEqual(self.client.get(self.edit_url()).status_code, 200)
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.edit_url(), {}).status_code, 405)
        self.assertEqual(self.saved_metadata(), before)

    def test_csrf_protects_both_new_mutations_even_with_valid_revision(self):
        edit_data, role_data = self.edit_payload(name="CSRF edit"), self.role_payload(role=CommitteeRole.CHAIR)
        metadata, roster = self.saved_metadata(), self.saved_roster()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.officer)
        self.assertEqual(strict.post(self.edit_url(), edit_data).status_code, 403)
        self.assertEqual(strict.post(self.role_url(), role_data).status_code, 403)
        self.assertEqual(self.saved_metadata(), metadata)
        self.assertEqual(self.saved_roster(), roster)

    def test_unknown_and_malformed_committee_or_member_are_404(self):
        unknown = str(ObjectId())
        edit_revision = self.edit_payload()["revision"]
        role_data = self.role_payload(role=CommitteeRole.CHAIR)
        for committee_id in (unknown, "not-an-object-id"):
            with self.subTest(committee=committee_id):
                url = f"/committees/{committee_id}/edit/"
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, {"name": "Missing", "description": "", "revision": edit_revision}).status_code, 404)
                self.assertEqual(self.client.post(f"/committees/{committee_id}/members/{self.member.pk}/role/", role_data).status_code, 404)
        for user_id in (unknown, "not-an-object-id"):
            with self.subTest(user=user_id):
                self.assertEqual(self.client.post(f"/committees/{self.committee.pk}/members/{user_id}/role/", role_data).status_code, 404)

    def test_missing_tampered_and_cross_committee_edit_tokens_cannot_write(self):
        original = self.edit_payload(name="Must not save")
        other_token = self.edit_payload(committee=self.other)["revision"]
        before = self.saved_metadata()
        for revision in (None, "tampered-token", other_token):
            with self.subTest(revision=revision):
                data = {**original, "revision": revision or ""}
                response = self.client.post(self.edit_url(), data)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.saved_metadata(), before)

    def test_stale_edit_preserves_newer_metadata_roster_and_task_history(self):
        task = create_task(self.officer, title="Preserve task", committee=self.committee, assignee=self.member)
        task_before, roster_before = self.task_snapshot(task), self.saved_roster()
        stale_data = self.edit_payload(name="Stale name", description="Stale description")
        other_client = Client()
        other_client.force_login(self.admin)
        current_data = self.edit_payload(client=other_client, name="Winning name", description="Winning description")
        self.assertEqual(other_client.post(self.edit_url(), current_data).status_code, 302)
        response = self.client.post(self.edit_url(), stale_data)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.saved_metadata()[:2], ("Winning name", "Winning description"))
        self.assertEqual(self.saved_roster(), roster_before)
        self.assertEqual(self.task_snapshot(task), task_before)

    def test_officer_and_admin_can_change_committee_role_without_global_promotion_or_task_changes(self):
        task = create_task(self.officer, title="Preserve assignment", committee=self.committee, assignee=self.member)
        task_before = self.task_snapshot(task)
        metadata_before = self.saved_metadata()
        self.membership.refresh_from_db()
        original_identity = (self.membership.pk, self.membership.user_id, self.membership.committee_id, self.membership.joined_at)
        for actor, role in ((self.officer, CommitteeRole.CHAIR), (self.admin, CommitteeRole.MEMBER)):
            with self.subTest(actor=actor.username, role=role):
                self.client.force_login(actor)
                response = self.client.post(self.role_url(), self.role_payload(role=role))
                self.assertEqual(response.status_code, 302)
                self.membership.refresh_from_db()
                self.assertEqual(self.membership.role, role)
                self.assertEqual((self.membership.pk, self.membership.user_id, self.membership.committee_id, self.membership.joined_at), original_identity)
                self.assertEqual(Profile.objects.get(user=self.member).role, Role.MEMBER)
                self.assertFalse(can_manage_tasks(self.member))
                self.assertEqual(self.saved_metadata(), metadata_before)
                self.assertEqual(self.task_snapshot(task), task_before)

    def test_role_noop_is_success_without_recreating_membership(self):
        before = self.saved_roster()
        response = self.client.post(self.role_url(), self.role_payload(role=CommitteeRole.MEMBER))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.saved_roster(), before)

    def test_role_change_rejects_get_and_other_methods_without_writes(self):
        before = self.saved_roster()
        for method in ("get", "put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(self.role_url(), {}).status_code, 405)
        self.assertEqual(self.saved_roster(), before)

    def test_invalid_committee_role_never_changes_roster_or_organization_role(self):
        before = self.saved_roster()
        for role in ("", "officer", "admin", "president", "invalid"):
            with self.subTest(role=role):
                response = self.client.post(self.role_url(), self.role_payload(role=role))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.saved_roster(), before)
                self.assertEqual(Profile.objects.get(user=self.member).role, Role.MEMBER)

    def test_membership_from_another_committee_cannot_be_changed_through_this_committee(self):
        outsider = make_user("committee-update-outsider@example.invalid", Role.MEMBER)
        other_membership = CommitteeMember.objects.create(committee=self.other, user=outsider)
        data = self.role_payload(role=CommitteeRole.CHAIR)
        response = self.client.post(self.role_url(user=outsider), data)
        self.assertEqual(response.status_code, 404)
        other_membership.refresh_from_db()
        self.assertEqual(other_membership.role, CommitteeRole.MEMBER)

    def test_role_tokens_are_bound_to_member_and_workflow(self):
        before = self.saved_roster()
        data = self.role_payload(role=CommitteeRole.CHAIR)
        other_member_token = self.role_payload(user=self.chair)["revision"]
        edit_token = self.edit_payload()["revision"]
        for revision in ("", "tampered-token", other_member_token, edit_token):
            with self.subTest(revision=revision):
                response = self.client.post(self.role_url(), {**data, "revision": revision})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.saved_roster(), before)

    def test_stale_role_form_preserves_newer_role_without_changing_task_history(self):
        task = create_task(self.officer, title="Keep progress", committee=self.committee, assignee=self.member)
        task_before = self.task_snapshot(task)
        stale_data = self.role_payload(role=CommitteeRole.MEMBER)
        other_client = Client()
        other_client.force_login(self.admin)
        current_data = self.role_payload(client=other_client, role=CommitteeRole.CHAIR)
        self.assertEqual(other_client.post(self.role_url(), current_data).status_code, 302)
        response = self.client.post(self.role_url(), stale_data)
        self.assertEqual(response.status_code, 409)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, CommitteeRole.CHAIR)
        self.assertEqual(self.task_snapshot(task), task_before)

    def test_target_who_becomes_unavailable_after_form_load_is_not_promoted(self):
        before = self.saved_roster()
        data = self.role_payload(role=CommitteeRole.CHAIR)
        for state in ("inactive", "applicant", "suspended", "lifecycle_pending", "review_pending"):
            with self.subTest(state=state):
                self.member.__class__.objects.filter(pk=self.member.pk).update(is_active=True)
                Profile.objects.filter(user=self.member).update(
                    role=Role.MEMBER, is_suspended=False, suspension_update_pending=False,
                )
                MembershipApplication.objects.filter(user=self.member).delete()
                if state == "inactive":
                    self.member.__class__.objects.filter(pk=self.member.pk).update(is_active=False)
                elif state == "applicant":
                    Profile.objects.filter(user=self.member).update(role=Role.APPLICANT)
                elif state == "suspended":
                    Profile.objects.filter(user=self.member).update(is_suspended=True)
                elif state == "lifecycle_pending":
                    Profile.objects.filter(user=self.member).update(suspension_update_pending=True)
                else:
                    MembershipApplication.objects.create(
                        user=self.member, statement="Unfinished review", status=ApplicationStatus.APPROVED,
                        access_update_pending=True,
                    )
                response = self.client.post(self.role_url(), data)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.saved_roster(), before)

    def test_edit_cas_rejects_a_write_interleaved_after_form_validation(self):
        data = self.edit_payload(name="Losing edit", description="Must not overwrite")
        original_update = QuerySet.update
        interleaved = False

        def competing_update(queryset, **values):
            nonlocal interleaved
            if queryset.model is Committee and not interleaved:
                interleaved = True
                original_update(
                    Committee.objects.filter(pk=self.committee.pk),
                    name="Concurrent winner", description="Saved first",
                )
            return original_update(queryset, **values)

        with patch.object(QuerySet, "update", competing_update):
            response = self.client.post(self.edit_url(), data)
        self.assertTrue(interleaved)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.saved_metadata()[:2], ("Concurrent winner", "Saved first"))

    def test_role_cas_rejects_interleaved_role_change_and_removed_membership(self):
        for removed in (False, True):
            with self.subTest(removed=removed):
                CommitteeMember.objects.filter(pk=self.membership.pk).update(role=CommitteeRole.MEMBER)
                data = self.role_payload(role=CommitteeRole.CHAIR)
                original_update = QuerySet.update
                interleaved = False

                def competing_update(queryset, **values):
                    nonlocal interleaved
                    if queryset.model is CommitteeMember and not interleaved:
                        interleaved = True
                        if removed:
                            CommitteeMember.objects.filter(pk=self.membership.pk).delete()
                        else:
                            original_update(CommitteeMember.objects.filter(pk=self.membership.pk), role=CommitteeRole.CHAIR)
                    return original_update(queryset, **values)

                with patch.object(QuerySet, "update", competing_update):
                    response = self.client.post(self.role_url(), data)
                self.assertTrue(interleaved)
                feedback = "no longer on the committee" if removed else "changed while you were editing"
                self.assertContains(response, feedback, status_code=409)
                if removed:
                    self.assertFalse(CommitteeMember.objects.filter(pk=self.membership.pk).exists())
                else:
                    self.membership.refresh_from_db()
                    self.assertEqual(self.membership.role, CommitteeRole.CHAIR)

    def test_database_failure_or_lost_ack_returns_safe_uncertain_feedback_without_compensation(self):
        secret_marker = "synthetic-database-secret-MUST-NOT-LEAK"
        original_update = QuerySet.update
        for model in (Committee, CommitteeMember):
            for saved_first in (False, True):
                with self.subTest(model=model.__name__, saved_first=saved_first):
                    self.committee.refresh_from_db()
                    metadata_before, roster_before = self.saved_metadata(), self.saved_roster()
                    if model is Committee:
                        data = self.edit_payload(description="Saved despite lost acknowledgement")
                        url = self.edit_url()
                    else:
                        data = self.role_payload(role=CommitteeRole.CHAIR)
                        url = self.role_url()

                    def failed_update(queryset, **values):
                        if queryset.model is model:
                            if saved_first:
                                original_update(queryset, **values)
                            raise OperationalError(secret_marker)
                        return original_update(queryset, **values)

                    with patch.object(QuerySet, "update", failed_update):
                        response = self.client.post(url, data)
                    self.assertContains(response, "could not be confirmed", status_code=503)
                    self.assertNotContains(response, secret_marker, status_code=503)
                    if model is Committee:
                        expected = "Saved despite lost acknowledgement" if saved_first else metadata_before[1]
                        self.assertEqual(self.saved_metadata()[1], expected)
                        self.assertEqual(self.saved_roster(), roster_before)
                    else:
                        self.membership.refresh_from_db()
                        expected = CommitteeRole.CHAIR if saved_first else CommitteeRole.MEMBER
                        self.assertEqual(self.membership.role, expected)
                        self.assertEqual(self.saved_metadata(), metadata_before)
