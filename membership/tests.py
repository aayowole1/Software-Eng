from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, get_role
from accounts.testing import make_user

from .models import ApplicationStatus, MembershipApplication


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

    def test_rejection_leaves_an_inactive_account_off(self):
        self.applicant.is_active = False
        self.applicant.save()
        self.client.force_login(self.officer)
        self.review("reject")
        self.applicant.refresh_from_db()
        self.assertFalse(self.applicant.is_active)

    def test_officer_rejection_keeps_applicant_role(self):
        self.client.force_login(self.officer)
        self.review("reject")
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, ApplicationStatus.REJECTED)
        self.assertEqual(get_role(self.applicant), Role.APPLICANT)

    def test_rejected_applicant_can_reapply(self):
        self.client.force_login(self.officer)
        self.review("reject")
        self.client.force_login(self.applicant)
        self.client.post(reverse("membership:apply"), {"statement": "Second try"})
        self.assertEqual(MembershipApplication.objects.filter(user=self.applicant).count(), 2)

    def test_application_cannot_be_reviewed_twice(self):
        self.client.force_login(self.officer)
        self.review("reject")
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
