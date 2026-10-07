from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user

from .ai import summarize_meeting
from .models import ActionItem, DraftStatus, MeetingDraft

NOTES = """Weekly officer meeting.
We discussed the spring hackathon. Attendance last month was strong.
Action: Book the engineering atrium for March 3
TODO - Email sponsors about prizes
- [ ] Draft the volunteer sign-up form
Budget is still pending approval from the department.
"""


class SummarizerTests(SimpleTestCase):
    def test_extracts_marked_action_items(self):
        result = summarize_meeting(NOTES)
        self.assertEqual(
            result.action_items,
            [
                "Book the engineering atrium for March 3",
                "Email sponsors about prizes",
                "Draft the volunteer sign-up form",
            ],
        )

    def test_summary_uses_non_action_text(self):
        result = summarize_meeting(NOTES)
        self.assertIn("spring hackathon", result.summary)
        self.assertNotIn("Book the engineering atrium", result.summary)

    def test_empty_notes(self):
        result = summarize_meeting("")
        self.assertEqual(result.summary, "")
        self.assertEqual(result.action_items, [])


class MeetingDraftTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@example.com", Role.ADMIN)
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("member@example.com", Role.MEMBER)

    def create_draft(self):
        self.client.force_login(self.officer)
        self.client.post(reverse("meetings:create"), {"title": "Week 2", "notes": NOTES})
        return MeetingDraft.objects.get(title="Week 2")

    def review(self, draft, decision, **extra):
        data = {"decision": decision, "note": "", "new_items": ""}
        data.update(extra)
        return self.client.post(reverse("meetings:review", args=[draft.pk]), data)

    def test_officer_submits_notes_and_gets_ai_draft(self):
        draft = self.create_draft()
        self.assertEqual(draft.status, DraftStatus.PENDING_REVIEW)
        self.assertEqual(draft.created_by, self.officer)
        self.assertIn("spring hackathon", draft.summary)
        self.assertEqual(draft.action_items.count(), 3)

    def test_title_and_notes_required(self):
        self.client.force_login(self.officer)
        self.client.post(reverse("meetings:create"), {"title": "", "notes": ""})
        self.assertFalse(MeetingDraft.objects.exists())

    def test_members_cannot_see_or_create_drafts(self):
        draft = self.create_draft()
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("meetings:list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("meetings:detail", args=[draft.pk])).status_code, 403)
        response = self.client.post(reverse("meetings:create"), {"title": "X", "notes": "Y"})
        self.assertEqual(response.status_code, 403)

    def test_approve_with_edits_untick_and_new_items(self):
        draft = self.create_draft()
        first, second, third = draft.action_items.all()
        self.review(
            draft,
            DraftStatus.APPROVED,
            note="Looks good",
            new_items="Order pizza\n\n",
            **{
                f"item-{first.pk}-accepted": "on",
                f"item-{first.pk}-description": "Book the atrium for March 3 (2-6pm)",
                f"item-{second.pk}-description": second.description,  # unticked -> rejected
                f"item-{third.pk}-accepted": "on",
                f"item-{third.pk}-description": third.description,
            },
        )
        draft.refresh_from_db()
        self.assertEqual(draft.status, DraftStatus.APPROVED)
        self.assertEqual(draft.reviewed_by, self.officer)
        self.assertEqual(draft.review_note, "Looks good")
        accepted = list(draft.action_items.filter(accepted=True).values_list("description", flat=True))
        self.assertEqual(
            accepted,
            ["Book the atrium for March 3 (2-6pm)", "Draft the volunteer sign-up form", "Order pizza"],
        )
        self.assertFalse(ActionItem.objects.get(pk=second.pk).accepted)

    def test_reject(self):
        draft = self.create_draft()
        self.review(draft, DraftStatus.REJECTED)
        draft.refresh_from_db()
        self.assertEqual(draft.status, DraftStatus.REJECTED)

    def test_invalid_decision_does_nothing(self):
        draft = self.create_draft()
        self.review(draft, "pending_review")
        draft.refresh_from_db()
        self.assertEqual(draft.status, DraftStatus.PENDING_REVIEW)
        self.assertIsNone(draft.reviewed_by)

    def test_cannot_review_twice(self):
        draft = self.create_draft()
        self.review(draft, DraftStatus.REJECTED)
        self.review(draft, DraftStatus.APPROVED)
        draft.refresh_from_db()
        self.assertEqual(draft.status, DraftStatus.REJECTED)

    def test_revision_cycle_regenerates_draft(self):
        draft = self.create_draft()
        self.review(draft, DraftStatus.REVISION_REQUESTED, note="Add the budget item")
        self.client.post(
            reverse("meetings:revise", args=[draft.pk]),
            {"title": "Week 2 (revised)", "notes": NOTES + "Action: Follow up on budget\n"},
        )
        draft.refresh_from_db()
        self.assertEqual(draft.title, "Week 2 (revised)")
        self.assertEqual(draft.status, DraftStatus.PENDING_REVIEW)
        self.assertIsNone(draft.reviewed_by)
        self.assertEqual(draft.action_items.count(), 4)

    def test_cannot_revise_unless_revision_requested(self):
        draft = self.create_draft()
        self.client.post(reverse("meetings:revise", args=[draft.pk]), {"title": "New", "notes": "New"})
        draft.refresh_from_db()
        self.assertEqual(draft.title, "Week 2")

    def test_only_admin_can_delete(self):
        draft = self.create_draft()
        self.assertEqual(self.client.post(reverse("meetings:delete", args=[draft.pk])).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(reverse("meetings:delete", args=[draft.pk]))
        self.assertFalse(MeetingDraft.objects.exists())
        self.assertFalse(ActionItem.objects.exists())
