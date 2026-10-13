from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

from accounts.models import Role, get_role
from accounts.testing import make_user

from .models import (
    REAPPLY_WAIT,
    REJECTED_RETENTION,
    ApplicationStatus,
    MembershipApplication,
    next_application_allowed_at,
    purge_old_rejected_applications,
)


class ApplyTests(TestCase):
    def setUp(self):
        self.applicant = make_user("ada@example.com")
        self.client.force_login(self.applicant)

    def test_applicant_can_submit_application(self):
        self.client.post(reverse("membership:apply"), {"statement": "I love robotics."})
        application = MembershipApplication.objects.get(user=self.applicant)
        self.assertEqual(application.status, ApplicationStatus.PENDING)

    def test_statement_is_required(self):
        self.client.post(reverse("membership:apply"), {"statement": ""})
        self.assertFalse(MembershipApplication.objects.exists())

    def test_only_one_pending_application(self):
        self.client.post(reverse("membership:apply"), {"statement": "First"})
        self.client.post(reverse("membership:apply"), {"statement": "Second"})
        self.assertEqual(MembershipApplication.objects.count(), 1)

    def test_members_cannot_apply(self):
        self.client.force_login(make_user("member@example.com", Role.MEMBER))
        self.client.post(reverse("membership:apply"), {"statement": "Again"})
        self.assertFalse(MembershipApplication.objects.exists())

    def test_apply_requires_sign_in(self):
        self.client.logout()
        response = self.client.get(reverse("membership:apply"))
        self.assertEqual(response.status_code, 302)


class ReviewTests(TestCase):
    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.applicant = make_user("ada@example.com")
        self.application = MembershipApplication.objects.create(user=self.applicant, statement="Hi")

    def review(self, decision, note=""):
        return self.client.post(
            reverse("membership:review_application", args=[self.application.pk]),
            {"decision": decision, "note": note},
        )

    def test_officer_approval_makes_applicant_a_member(self):
        self.client.force_login(self.officer)
        self.review("approve", "Welcome!")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.APPROVED)
        self.assertEqual(self.application.reviewed_by, self.officer)
        self.assertEqual(self.application.review_note, "Welcome!")
        self.assertEqual(get_role(self.applicant), Role.MEMBER)

    def test_approval_switches_on_an_inactive_account(self):
        self.applicant.is_active = False
        self.applicant.save()
        self.client.force_login(self.officer)
        self.review("approve")
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)
        self.assertEqual(get_role(self.applicant), Role.MEMBER)

    def test_rejection_keeps_the_record_with_reviewer_and_reason(self):
        self.client.force_login(self.officer)
        self.review("reject", "We are full this semester.")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.REJECTED)
        self.assertEqual(self.application.reviewed_by, self.officer)
        self.assertIsNotNone(self.application.reviewed_at)
        self.assertEqual(self.application.review_note, "We are full this semester.")
        self.assertEqual(self.application.statement, "Hi")
        reviewed = self.client.get(reverse("membership:application_list"))
        self.assertContains(reviewed, "We are full this semester.")
        self.assertContains(reviewed, "officer@example.com")

    def test_rejection_requires_a_reason(self):
        self.client.force_login(self.officer)
        for note in ["", "   "]:
            with self.subTest(note=note):
                self.review("reject", note)
                self.application.refresh_from_db()
                self.assertEqual(self.application.status, ApplicationStatus.PENDING)
        with self.assertRaises(ValueError):
            self.application.review(self.officer, approve=False, note="")

    def test_rejection_switches_on_a_never_approved_account_as_applicant(self):
        self.applicant.is_active = False
        self.applicant.save()
        self.client.force_login(self.officer)
        self.review("reject", "Not this time.")
        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)
        self.assertEqual(get_role(self.applicant), Role.APPLICANT)

    def age_rejection(self, by):
        MembershipApplication.objects.filter(pk=self.application.pk).update(
            reviewed_at=timezone.now() - by
        )

    def test_rejected_applicant_must_wait_a_day_to_reapply(self):
        self.client.force_login(self.officer)
        self.review("reject", "Not this time.")
        self.client.force_login(self.applicant)
        page = self.client.get(reverse("membership:apply"))
        self.assertContains(page, "You can apply again after")
        self.assertNotContains(page, "Apply again</button>")
        self.assertContains(self.client.get(reverse("core:dashboard")), "You can apply again after")
        self.client.post(reverse("membership:apply"), {"statement": "Too soon"})
        self.assertEqual(MembershipApplication.objects.filter(user=self.applicant).count(), 1)

    def test_wait_ends_after_one_day(self):
        self.client.force_login(self.officer)
        self.review("reject", "Not this time.")
        self.age_rejection(REAPPLY_WAIT - timedelta(minutes=1))
        self.assertIsNotNone(next_application_allowed_at(self.applicant))
        self.age_rejection(REAPPLY_WAIT + timedelta(minutes=1))
        self.assertIsNone(next_application_allowed_at(self.applicant))

    def test_rejected_applicant_sees_reason_and_can_reapply(self):
        self.client.force_login(self.officer)
        self.review("reject", "Please come to one meeting first.")
        self.age_rejection(REAPPLY_WAIT + timedelta(minutes=1))
        self.client.force_login(self.applicant)
        page = self.client.get(reverse("membership:apply"))
        self.assertContains(page, "Not approved")
        self.assertContains(page, "Please come to one meeting first.")
        self.assertContains(page, "Apply again")
        dashboard = self.client.get(reverse("core:dashboard"))
        self.assertContains(dashboard, "Please come to one meeting first.")
        self.client.post(reverse("membership:apply"), {"statement": "Second try"})
        self.assertEqual(MembershipApplication.objects.filter(user=self.applicant).count(), 2)
        newest = MembershipApplication.objects.filter(user=self.applicant).first()
        self.assertEqual(newest.statement, "Second try")
        self.assertEqual(newest.status, ApplicationStatus.PENDING)

    def test_rejected_applicant_still_cannot_see_member_pages(self):
        self.client.force_login(self.officer)
        self.review("reject", "Not this time.")
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(reverse("membership:roster")).status_code, 403)

    def test_application_cannot_be_reviewed_twice(self):
        self.client.force_login(self.officer)
        self.review("reject", "Not this time.")
        self.review("approve")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.REJECTED)
        self.assertEqual(get_role(self.applicant), Role.APPLICANT)

    def test_approval_never_demotes_an_officer(self):
        self.client.force_login(self.officer)
        officer_app = MembershipApplication.objects.create(user=self.officer, statement="Testing")
        officer_app.review(self.officer, approve=True)
        self.assertEqual(get_role(self.officer), Role.OFFICER)

    def test_invalid_decision_does_nothing(self):
        self.client.force_login(self.officer)
        self.review("maybe")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.PENDING)

    def test_members_cannot_review(self):
        self.client.force_login(make_user("member@example.com", Role.MEMBER))
        self.assertEqual(self.review("approve").status_code, 403)
        self.assertEqual(self.client.get(reverse("membership:application_list")).status_code, 403)
        self.assertEqual(get_role(self.applicant), Role.APPLICANT)

    def test_officer_sees_pending_applications(self):
        self.client.force_login(self.officer)
        self.assertContains(self.client.get(reverse("membership:application_list")), "ada@example.com")


class RosterTests(TestCase):
    def test_roster_lists_members_but_not_applicants(self):
        member = make_user("member@example.com", Role.MEMBER)
        make_user("officer@example.com", Role.OFFICER)
        make_user("applicant@example.com")
        self.client.force_login(member)
        response = self.client.get(reverse("membership:roster"))
        self.assertContains(response, "member@example.com")
        self.assertContains(response, "officer@example.com")
        self.assertNotContains(response, "applicant@example.com")

    def test_applicants_cannot_see_roster(self):
        self.client.force_login(make_user("applicant@example.com"))
        self.assertEqual(self.client.get(reverse("membership:roster")).status_code, 403)


class PurgeRejectedApplicationsTests(TestCase):
    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)

    def application(self, email, status, reviewed_days_ago):
        user = make_user(email)
        return MembershipApplication.objects.create(
            user=user,
            statement="Hi",
            status=status,
            reviewed_by=self.officer if status != ApplicationStatus.PENDING else None,
            reviewed_at=timezone.now() - timedelta(days=reviewed_days_ago) if reviewed_days_ago is not None else None,
            review_note="Reason" if status == ApplicationStatus.REJECTED else "",
        )

    def test_only_rejected_applications_older_than_seven_days_are_deleted(self):
        old_rejected = self.application("old@example.com", ApplicationStatus.REJECTED, REJECTED_RETENTION.days + 1)
        new_rejected = self.application("new@example.com", ApplicationStatus.REJECTED, REJECTED_RETENTION.days - 1)
        old_approved = self.application("member@example.com", ApplicationStatus.APPROVED, 30)
        pending = self.application("pending@example.com", ApplicationStatus.PENDING, None)

        self.assertEqual(purge_old_rejected_applications(), 1)
        remaining = set(MembershipApplication.objects.values_list("pk", flat=True))
        self.assertNotIn(old_rejected.pk, remaining)
        self.assertEqual(remaining, {new_rejected.pk, old_approved.pk, pending.pk})
        # The person's account stays; they can still sign in and apply.
        self.assertTrue(old_rejected.user.__class__.objects.filter(pk=old_rejected.user_id).exists())

    def test_management_command_reports_count(self):
        self.application("old@example.com", ApplicationStatus.REJECTED, REJECTED_RETENTION.days + 1)
        out = StringIO()
        call_command("purge_rejected_applications", stdout=out)
        self.assertIn("Deleted 1 rejected application(s)", out.getvalue())
        self.assertFalse(MembershipApplication.objects.exists())

    def test_purged_applicant_can_apply_again(self):
        app = self.application("old@example.com", ApplicationStatus.REJECTED, REJECTED_RETENTION.days + 1)
        purge_old_rejected_applications()
        self.client.force_login(app.user)
        self.client.post(reverse("membership:apply"), {"statement": "Fresh start"})
        self.assertEqual(MembershipApplication.objects.get(user=app.user).statement, "Fresh start")
