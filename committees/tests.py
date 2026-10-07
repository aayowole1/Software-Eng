from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user

from .models import Committee, CommitteeMember, CommitteeRole


class CommitteeTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@example.com", Role.ADMIN)
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.applicant = make_user("applicant@example.com")

    def create(self, name="Events", description="Plans events"):
        return self.client.post(reverse("committees:create"), {"name": name, "description": description})

    def make_committee(self):
        committee = Committee.objects.create(name="Events", created_by=self.officer)
        CommitteeMember.objects.create(committee=committee, user=self.officer, role=CommitteeRole.CHAIR)
        return committee

    # Creating
    def test_officer_creates_committee_and_becomes_chair(self):
        self.client.force_login(self.officer)
        self.create()
        committee = Committee.objects.get(name="Events")
        self.assertEqual(committee.created_by, self.officer)
        chair = CommitteeMember.objects.get(committee=committee, user=self.officer)
        self.assertEqual(chair.role, CommitteeRole.CHAIR)

    def test_name_is_required(self):
        self.client.force_login(self.officer)
        self.create(name="  ")
        self.assertFalse(Committee.objects.exists())

    def test_duplicate_name_rejected(self):
        self.client.force_login(self.officer)
        self.create()
        response = self.create(name="events")
        self.assertContains(response, "already exists")
        self.assertEqual(Committee.objects.count(), 1)

    def test_members_cannot_create(self):
        self.client.force_login(self.member)
        self.assertEqual(self.create().status_code, 403)
        self.assertFalse(Committee.objects.exists())

    # Viewing
    def test_members_can_view_list_and_roster(self):
        committee = self.make_committee()
        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("committees:list")), "Events")
        response = self.client.get(reverse("committees:detail", args=[committee.pk]))
        self.assertContains(response, "officer@example.com")
        self.assertContains(response, "Chair")

    def test_applicants_cannot_view(self):
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(reverse("committees:list")).status_code, 403)

    def test_unknown_committee_is_404(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("committees:detail", args=["0123456789abcdef01234567"]))
        self.assertEqual(response.status_code, 404)

    def test_malformed_id_is_404(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get("/committees/not-an-id/").status_code, 404)

    # Membership
    def test_officer_adds_member(self):
        committee = self.make_committee()
        self.client.force_login(self.officer)
        self.client.post(
            reverse("committees:add_member", args=[committee.pk]),
            {"user": str(self.member.pk), "role": CommitteeRole.MEMBER},
        )
        self.assertTrue(CommitteeMember.objects.filter(committee=committee, user=self.member).exists())

    def test_cannot_add_same_member_twice(self):
        committee = self.make_committee()
        self.client.force_login(self.officer)
        url = reverse("committees:add_member", args=[committee.pk])
        self.client.post(url, {"user": str(self.member.pk), "role": CommitteeRole.MEMBER})
        self.client.post(url, {"user": str(self.member.pk), "role": CommitteeRole.MEMBER})
        self.assertEqual(CommitteeMember.objects.filter(committee=committee, user=self.member).count(), 1)

    def test_applicants_cannot_be_added(self):
        committee = self.make_committee()
        self.client.force_login(self.officer)
        self.client.post(
            reverse("committees:add_member", args=[committee.pk]),
            {"user": str(self.applicant.pk), "role": CommitteeRole.MEMBER},
        )
        self.assertFalse(CommitteeMember.objects.filter(user=self.applicant).exists())

    def test_invalid_committee_role_rejected(self):
        committee = self.make_committee()
        self.client.force_login(self.officer)
        self.client.post(
            reverse("committees:add_member", args=[committee.pk]),
            {"user": str(self.member.pk), "role": "emperor"},
        )
        self.assertFalse(CommitteeMember.objects.filter(user=self.member).exists())

    def test_officer_removes_member(self):
        committee = self.make_committee()
        CommitteeMember.objects.create(committee=committee, user=self.member)
        self.client.force_login(self.officer)
        self.client.post(reverse("committees:remove_member", args=[committee.pk, self.member.pk]))
        self.assertFalse(CommitteeMember.objects.filter(committee=committee, user=self.member).exists())

    def test_removing_non_member_is_404(self):
        committee = self.make_committee()
        self.client.force_login(self.officer)
        response = self.client.post(reverse("committees:remove_member", args=[committee.pk, self.member.pk]))
        self.assertEqual(response.status_code, 404)

    def test_members_cannot_change_roster(self):
        committee = self.make_committee()
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("committees:add_member", args=[committee.pk]),
            {"user": str(self.member.pk), "role": CommitteeRole.MEMBER},
        )
        self.assertEqual(response.status_code, 403)

    # Deleting
    def test_admin_deletes_committee_and_roster(self):
        committee = self.make_committee()
        self.client.force_login(self.admin)
        self.client.post(reverse("committees:delete", args=[committee.pk]))
        self.assertFalse(Committee.objects.exists())
        self.assertFalse(CommitteeMember.objects.exists())

    def test_officers_cannot_delete(self):
        committee = self.make_committee()
        self.client.force_login(self.officer)
        self.assertEqual(self.client.post(reverse("committees:delete", args=[committee.pk])).status_code, 403)
        self.assertTrue(Committee.objects.exists())

    def test_profile_lists_users_committees(self):
        self.make_committee()
        self.client.force_login(self.officer)
        self.assertContains(self.client.get(reverse("accounts:profile")), "Events")
