from django.test import TestCase
from django.urls import reverse

from accounts.models import Role, get_role
from accounts.testing import make_user
from membership.models import ApplicationStatus, MembershipApplication


class MembershipIntegrationTests(TestCase):
    def test_approval_grants_roster_access(self):
        # Create the users for this workflow.
        applicant = make_user("tj_applicant@example.com")
        officer = make_user("tj_officer@example.com", Role.OFFICER)

        application = MembershipApplication.objects.create(
            user=applicant,
            statement="I would like to join OrgFlow.",
        )

        roster_url = reverse("membership:roster")
        review_url = reverse(
            "membership:review_application",
            args=[application.pk],
        )

        # An applicant must not see the member roster.
        self.client.force_login(applicant)
        response = self.client.get(roster_url)
        self.assertEqual(response.status_code, 403)

        # The officer approves the application.
        self.client.force_login(officer)
        response = self.client.post(
            review_url,
            {"decision": "approve", "note": "Approved"},
        )
        self.assertEqual(response.status_code, 302)

        application.refresh_from_db()
        self.assertEqual(
            application.status,
            ApplicationStatus.APPROVED,
        )
        self.assertEqual(get_role(applicant), Role.MEMBER)

        # The newly approved member now has roster access.
        self.client.force_login(applicant)
        response = self.client.get(roster_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tj_applicant@example.com")
