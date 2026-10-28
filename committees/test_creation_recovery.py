"""Creation fault/retry regressions; continuation never overwrites later intent."""

from contextlib import contextmanager
from html.parser import HTMLParser
import time
from unittest.mock import patch

from bson import ObjectId
from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.db.models.query import QuerySet
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile, Role
from accounts.testing import make_user
from membership.models import ApplicationStatus, MembershipApplication
from tasks.models import Task
from tasks.services import create_task

from .models import Committee, CommitteeMember, CommitteeRole


class FormFields(HTMLParser):
    def __init__(self, response):
        super().__init__(convert_charrefs=True)
        self.fields = {}
        self.attributes = {}
        self.form_actions = []
        self.textarea = None
        self.feed(response.content.decode())

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "form":
            self.form_actions.append(attrs.get("action", ""))
        elif tag == "input" and attrs.get("name"):
            self.fields[attrs["name"]] = attrs.get("value", "")
            self.attributes[attrs["name"]] = attrs
        elif tag == "textarea" and attrs.get("name"):
            self.textarea = attrs["name"]
            self.fields[self.textarea] = ""

    def handle_data(self, data):
        if self.textarea is not None:
            self.fields[self.textarea] += data

    def handle_endtag(self, tag):
        if tag == "textarea":
            self.textarea = None


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CommitteeCreationRecoveryTests(TestCase):
    marker = "synthetic-database-secret-must-not-be-shown"

    def setUp(self):
        self.officer = make_user("create-recovery-officer@example.invalid", Role.OFFICER)
        self.admin = make_user("create-recovery-admin@example.invalid", Role.ADMIN)
        self.client.force_login(self.officer)

    def payload(self, client=None, **changes):
        response = (client or self.client).get(reverse("committees:create"))
        self.assertEqual(response.status_code, 200)
        data = {
            "name": "Recovery committee", "description": "Keep the original description",
            "creation_intent": FormFields(response).fields["creation_intent"],
        }
        data.update(changes)
        return data

    def recovery_url(self, committee):
        return reverse("committees:recover_creation", args=[committee.pk])

    def recovery_form(self, committee, data, client=None):
        response = (client or self.client).get(self.recovery_url(committee), {
            "creation_intent": data["creation_intent"],
        })
        self.assertEqual(response.status_code, 200)
        parsed = FormFields(response)
        return response, {
            "creation_intent": data["creation_intent"], "revision": parsed.fields["revision"],
            "confirm_add_creator": "1",
        }

    @contextmanager
    def insert_fault(self, model, *, after_write=False):
        original = model.save
        state = {"raised": False}

        def failed_save(instance, *args, **kwargs):
            if state["raised"]:
                return original(instance, *args, **kwargs)
            state["raised"] = True
            if after_write:
                original(instance, *args, **kwargs)
            raise OperationalError(self.marker)

        with patch.object(model, "save", failed_save), patch.object(
            QuerySet, "delete", side_effect=AssertionError("Creation recovery must never delete records"),
        ) as deleting:
            yield state
            deleting.assert_not_called()
        self.assertTrue(state["raised"], "The intended insert fault was not reached")

    def partial_creation(self, data=None):
        data = data or self.payload()
        with self.insert_fault(CommitteeMember):
            response = self.client.post(reverse("committees:create"), data)
        self.assertEqual(response.status_code, 503)
        committee = Committee.objects.get(name=data["name"])
        self.assertFalse(CommitteeMember.objects.filter(committee=committee, user=self.officer).exists())
        return committee, data

    def test_normal_officer_and_admin_creation_and_same_ticket_retry_are_idempotent(self):
        for index, actor in enumerate((self.officer, self.admin)):
            with self.subTest(actor=actor.username):
                self.client.force_login(actor)
                history = Profile.objects.get(user=actor).role_history
                data = self.payload(name=f"Normal committee {index}")
                self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 302)
                committee = Committee.objects.get(name=data["name"])
                self.assertEqual(committee.created_by_id, actor.pk)
                member = CommitteeMember.objects.get(committee=committee, user=actor)
                self.assertEqual(member.role, CommitteeRole.CHAIR)
                self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 302)
                self.assertEqual(Committee.objects.filter(pk=committee.pk).count(), 1)
                self.assertEqual(CommitteeMember.objects.filter(committee=committee, user=actor).count(), 1)
                self.assertEqual(Profile.objects.get(user=actor).role_history, history)

    def test_legacy_post_without_ticket_still_creates_once(self):
        response = self.client.post(reverse("committees:create"), {"name": "Legacy client", "description": ""})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CommitteeMember.objects.get(committee__name="Legacy client", user=self.officer).role, CommitteeRole.CHAIR)

    def test_explicit_empty_tampered_cross_actor_and_expired_tickets_do_not_fall_back(self):
        data = self.payload()
        for ticket in ("", "tampered-ticket"):
            with self.subTest(ticket=ticket):
                self.assertEqual(self.client.post(reverse("committees:create"), {**data, "creation_intent": ticket}).status_code, 400)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 400)
        self.client.force_login(self.officer)
        with patch("django.core.signing.time.time", return_value=time.time() + 86401):
            self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 400)
        self.assertFalse(Committee.objects.exists())
        self.assertFalse(CommitteeMember.objects.exists())

    def test_before_committee_insert_failure_preserves_input_and_retry_identity(self):
        data = self.payload(name='Preserve "name" <text>', description="Keep <script>text</script> & punctuation")
        with self.insert_fault(Committee):
            response = self.client.post(reverse("committees:create"), data)
        self.assertEqual(response.status_code, 503)
        fields = FormFields(response).fields
        self.assertEqual({key: fields[key] for key in data}, data)
        self.assertNotContains(response, self.marker, status_code=503)
        self.assertNotContains(response, "<script>text</script>", status_code=503)
        self.assertFalse(Committee.objects.exists())
        self.assertEqual(self.client.post(reverse("committees:create"), fields).status_code, 302)
        self.assertEqual(Committee.objects.filter(name=data["name"]).count(), 1)
        self.assertEqual(CommitteeMember.objects.get(committee__name=data["name"], user=self.officer).role, CommitteeRole.CHAIR)

    def test_committee_insert_lost_ack_preserves_exact_record_and_needs_explicit_chair_confirmation(self):
        data = self.payload()
        with self.insert_fault(Committee, after_write=True):
            response = self.client.post(reverse("committees:create"), data)
        self.assertEqual(response.status_code, 503)
        committee = Committee.objects.get(name=data["name"])
        saved = (committee.pk, committee.name, committee.description, committee.created_by_id, committee.created_at)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
        replay = self.client.post(reverse("committees:create"), {**data, "name": "Do not rename on replay"})
        self.assertEqual(replay.status_code, 200)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
        _, confirmation = self.recovery_form(committee, data)
        self.assertEqual(self.client.post(self.recovery_url(committee), confirmation).status_code, 302)
        committee.refresh_from_db()
        self.assertEqual((committee.pk, committee.name, committee.description, committee.created_by_id, committee.created_at), saved)
        self.assertEqual(Committee.objects.count(), 1)
        self.assertEqual(CommitteeMember.objects.get(committee=committee, user=self.officer).role, CommitteeRole.CHAIR)

    def test_creator_insert_failure_preserves_committee_and_replay_does_not_auto_add(self):
        committee, data = self.partial_creation()
        self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 200)
        self.assertEqual(Committee.objects.filter(pk=committee.pk).count(), 1)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
        _, confirmation = self.recovery_form(committee, data)
        self.assertEqual(self.client.post(self.recovery_url(committee), confirmation).status_code, 302)
        self.assertEqual(self.client.post(self.recovery_url(committee), confirmation).status_code, 302)
        self.assertEqual(CommitteeMember.objects.filter(committee=committee, user=self.officer).count(), 1)

    def test_creator_insert_lost_ack_is_confirmed_without_duplicate_or_compensation(self):
        data = self.payload()
        with self.insert_fault(CommitteeMember, after_write=True):
            response = self.client.post(reverse("committees:create"), data)
        self.assertEqual(response.status_code, 302)
        committee = Committee.objects.get(name=data["name"])
        row = CommitteeMember.objects.get(committee=committee, user=self.officer)
        self.assertEqual(row.role, CommitteeRole.CHAIR)
        self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 302)
        self.assertEqual(CommitteeMember.objects.get(committee=committee, user=self.officer).pk, row.pk)

    def test_recovery_get_is_read_only_with_visible_unchecked_explicit_confirmation(self):
        committee, data = self.partial_creation()
        response, _ = self.recovery_form(committee, data)
        parsed = FormFields(response)
        checkbox = parsed.attributes["confirm_add_creator"]
        self.assertEqual(checkbox["type"], "checkbox")
        self.assertEqual(checkbox["value"], "1")
        self.assertNotIn("checked", checkbox)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
        self.assertEqual(Committee.objects.count(), 1)

    def test_missing_or_nonexact_confirmation_and_invalid_revision_cannot_add(self):
        committee, data = self.partial_creation()
        _, confirmation = self.recovery_form(committee, data)
        for value in (None, "", "0", "on", "true"):
            with self.subTest(value=value):
                submitted = {**confirmation, "confirm_add_creator": value or ""}
                if value is None:
                    submitted.pop("confirm_add_creator")
                self.assertEqual(self.client.post(self.recovery_url(committee), submitted).status_code, 400)
                self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
        self.assertEqual(self.client.post(self.recovery_url(committee), {**confirmation, "revision": "tampered"}).status_code, 400)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())

    def test_changed_metadata_rejects_old_confirmation_without_changing_tasks(self):
        committee, data = self.partial_creation()
        task = create_task(self.officer, title="Preserve related work", committee=committee)
        before = Task.objects.filter(pk=task.pk).values().get()
        _, confirmation = self.recovery_form(committee, data)
        Committee.objects.filter(pk=committee.pk).update(name="Later name", description="Later description")
        self.assertEqual(self.client.post(self.recovery_url(committee), confirmation).status_code, 409)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
        self.assertEqual(Task.objects.filter(pk=task.pk).values().get(), before)
        committee.refresh_from_db()
        self.assertEqual((committee.name, committee.description), ("Later name", "Later description"))
        _, fresh = self.recovery_form(committee, data)
        self.assertEqual(self.client.post(self.recovery_url(committee), fresh).status_code, 302)

    def test_later_member_role_is_not_promoted_by_creation_replay_or_recovery(self):
        committee, data = self.partial_creation()
        _, confirmation = self.recovery_form(committee, data)
        row = CommitteeMember.objects.create(committee=committee, user=self.officer, role=CommitteeRole.MEMBER)
        self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 409)
        self.assertEqual(self.client.post(self.recovery_url(committee), confirmation).status_code, 409)
        row.refresh_from_db()
        self.assertEqual(row.role, CommitteeRole.MEMBER)
        self.assertEqual(CommitteeMember.objects.filter(committee=committee).count(), 1)

    def test_replay_after_intentional_removal_never_readds_without_fresh_confirmation(self):
        data = self.payload()
        self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 302)
        committee = Committee.objects.get(name=data["name"])
        CommitteeMember.objects.filter(committee=committee, user=self.officer).delete()
        self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 200)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
        _, confirmation = self.recovery_form(committee, data)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
        self.assertEqual(self.client.post(self.recovery_url(committee), {**confirmation, "confirm_add_creator": ""}).status_code, 400)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())

    def test_completed_replay_preserves_later_metadata(self):
        data = self.payload()
        self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 302)
        committee = Committee.objects.get(name=data["name"])
        Committee.objects.filter(pk=committee.pk).update(name="Intentional rename", description="New details")
        self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 302)
        committee.refresh_from_db()
        self.assertEqual((committee.name, committee.description), ("Intentional rename", "New details"))

    def test_recovery_never_recreates_a_deleted_committee_and_rejects_wrong_id(self):
        committee, data = self.partial_creation()
        url = self.recovery_url(committee)
        _, confirmation = self.recovery_form(committee, data)
        wrong = reverse("committees:recover_creation", args=[ObjectId()])
        self.assertEqual(self.client.get(wrong, {"creation_intent": data["creation_intent"]}).status_code, 400)
        committee.delete()
        self.assertEqual(self.client.get(url, {"creation_intent": data["creation_intent"]}).status_code, 404)
        self.assertEqual(self.client.post(url, confirmation).status_code, 404)
        self.assertFalse(Committee.objects.exists())
        self.assertFalse(CommitteeMember.objects.exists())

    def test_foreign_actor_or_changed_saved_owner_cannot_adopt_attempt(self):
        committee, data = self.partial_creation()
        _, confirmation = self.recovery_form(committee, data)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.recovery_url(committee), {"creation_intent": data["creation_intent"]}).status_code, 400)
        self.assertEqual(self.client.post(self.recovery_url(committee), confirmation).status_code, 400)
        self.client.force_login(self.officer)
        Committee.objects.filter(pk=committee.pk).update(created_by=self.admin)
        self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 403)
        self.assertEqual(self.client.post(self.recovery_url(committee), confirmation).status_code, 403)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())

    def test_changed_actor_permission_or_access_blocks_original_and_recovery_posts(self):
        committee, data = self.partial_creation()
        _, confirmation = self.recovery_form(committee, data)
        for state in ("member", "suspended", "inactive", "review_pending", "lifecycle_pending"):
            with self.subTest(state=state):
                get_user_model().objects.filter(pk=self.officer.pk).update(is_active=True)
                Profile.objects.filter(user=self.officer).update(role=Role.OFFICER, is_suspended=False, suspension_update_pending=False)
                MembershipApplication.objects.filter(user=self.officer).delete()
                self.client.force_login(self.officer)
                if state == "member":
                    Profile.objects.filter(user=self.officer).update(role=Role.MEMBER)
                elif state == "inactive":
                    get_user_model().objects.filter(pk=self.officer.pk).update(is_active=False)
                elif state == "review_pending":
                    MembershipApplication.objects.create(user=self.officer, statement="Interrupted access", status=ApplicationStatus.APPROVED, access_update_pending=True)
                else:
                    Profile.objects.filter(user=self.officer).update(**{"is_suspended" if state == "suspended" else "suspension_update_pending": True})
                expected = 403 if state == "member" else 302
                self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, expected)
                self.assertEqual(self.client.post(self.recovery_url(committee), confirmation).status_code, expected)
                self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())

    def test_profileless_superuser_can_explicitly_recover_own_committee(self):
        admin = get_user_model().objects.create_superuser(
            username="profileless-creation-admin", email="profileless-creation-admin@example.invalid", password="synthetic-password",
        )
        Profile.objects.filter(user=admin).delete()
        self.client.force_login(admin)
        data = self.payload(name="Superuser creation")
        with self.insert_fault(CommitteeMember):
            self.assertEqual(self.client.post(reverse("committees:create"), data).status_code, 503)
        committee = Committee.objects.get(name=data["name"])
        _, confirmation = self.recovery_form(committee, data)
        self.assertEqual(self.client.post(self.recovery_url(committee), confirmation).status_code, 302)
        self.assertEqual(CommitteeMember.objects.get(committee=committee, user=admin).role, CommitteeRole.CHAIR)

    def test_csrf_and_methods_protect_new_creation_and_explicit_confirmation(self):
        data = self.payload()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.officer)
        self.assertEqual(strict.post(reverse("committees:create"), data).status_code, 403)
        committee, data = self.partial_creation(data)
        response, confirmation = self.recovery_form(committee, data, client=strict)
        self.assertEqual(strict.post(self.recovery_url(committee), confirmation).status_code, 403)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
        for url in (reverse("committees:create"), self.recovery_url(committee)):
            self.assertEqual(self.client.put(url, {}).status_code, 405)
        confirmation["csrfmiddlewaretoken"] = FormFields(response).fields["csrfmiddlewaretoken"]
        self.assertEqual(strict.post(self.recovery_url(committee), confirmation).status_code, 302)

    def test_validation_and_another_committee_name_never_adopt_or_delete_existing_record(self):
        other = Committee.objects.create(name="Existing name", description="Must preserve", created_by=self.admin)
        data = self.payload(name="existing NAME")
        response = self.client.post(reverse("committees:create"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        self.assertEqual(Committee.objects.count(), 1)
        other.refresh_from_db()
        self.assertEqual((other.name, other.description, other.created_by_id), ("Existing name", "Must preserve", self.admin.pk))
        self.assertFalse(CommitteeMember.objects.filter(committee=other).exists())
        for name in ("", "   ", "x" * 101):
            response = self.client.post(reverse("committees:create"), {**data, "name": name})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(Committee.objects.count(), 1)

    def test_recovery_insert_before_failure_and_lost_ack_keep_same_committee_and_one_row(self):
        committee, data = self.partial_creation()
        _, confirmation = self.recovery_form(committee, data)
        with self.insert_fault(CommitteeMember):
            response = self.client.post(self.recovery_url(committee), confirmation)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Committee.objects.filter(pk=committee.pk).count(), 1)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
        with self.insert_fault(CommitteeMember, after_write=True):
            response = self.client.post(self.recovery_url(committee), confirmation)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CommitteeMember.objects.filter(committee=committee, user=self.officer).count(), 1)

    def test_unavailable_readback_uses_db_free_feedback_and_recovery_cannot_resubmit_create(self):
        committee, data = self.partial_creation()
        _, confirmation = self.recovery_form(committee, data)
        state = {"failed": False}
        original_first, original_get = QuerySet.first, QuerySet.get

        def failed_save(instance, *args, **kwargs):
            state["failed"] = True
            raise OperationalError(self.marker)

        def failed_first(queryset, *args, **kwargs):
            if state["failed"] and queryset.model in (Committee, CommitteeMember, Profile):
                raise OperationalError(self.marker)
            return original_first(queryset, *args, **kwargs)

        def failed_get(queryset, *args, **kwargs):
            if state["failed"] and queryset.model in (Committee, CommitteeMember, Profile):
                raise OperationalError(self.marker)
            return original_get(queryset, *args, **kwargs)

        with patch.object(CommitteeMember, "save", failed_save), patch.object(QuerySet, "first", failed_first), patch.object(QuerySet, "get", failed_get):
            response = self.client.post(self.recovery_url(committee), confirmation)
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, self.marker, status_code=503)
        self.assertNotIn(reverse("committees:create"), FormFields(response).form_actions)
        self.assertEqual(Committee.objects.filter(pk=committee.pk).count(), 1)
        self.assertFalse(CommitteeMember.objects.filter(committee=committee).exists())
