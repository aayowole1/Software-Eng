from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role
from committees.models import Committee, CommitteeMember

from announcements.models import Announcement, AnnouncementAttachment, AnnouncementReadReceipt, Resource

from .test_support import AnnouncementTestDataMixin


class AnnouncementAudienceTests(AnnouncementTestDataMixin, TestCase):
    def setUp(self):
        self.officer = self.make_officer()
        self.admin = self.make_user(role=Role.ADMIN)
        self.member = self.make_user()
        self.outsider = self.make_user()
        self.committee = Committee.objects.create(name="Outreach")
        other_committee = Committee.objects.create(name="Finance")
        self.membership = CommitteeMember.objects.create(committee=self.committee, user=self.member)
        CommitteeMember.objects.create(committee=other_committee, user=self.outsider)
        self.public = self.make_announcement(author=self.officer, title="Organization bulletin")
        self.notice = self.make_announcement(
            author=self.officer, title="Restricted outreach briefing", committee=self.committee,
            category=self.public.category, tags=["outreach"],
        )
        self.detail = reverse("announcements:detail", args=[self.notice.pk])
        self.read = reverse("announcements:mark_read", args=[self.notice.pk])
        attachment = AnnouncementAttachment.objects.create(
            announcement=self.notice, name="Briefing.txt",
            file=SimpleUploadedFile("briefing.txt", b"committee-only briefing"),
        )
        self.download = reverse("announcements:attachment_download", args=[attachment.pk])

    def test_audience_applies_to_every_read_surface(self):
        public_detail = reverse("announcements:detail", args=[self.public.pk])
        for user in (self.member, self.officer, self.admin, self.outsider):
            with self.subTest(user=user.username):
                self.login(user)
                allowed = user != self.outsider
                check_title = self.assertContains if allowed else self.assertNotContains
                for url in (reverse("announcements:list"), reverse("core:dashboard"), public_detail):
                    check_title(self.client.get(url), self.notice.title)
                tagged = self.client.get(reverse("announcements:list"), {"tag": "outreach"})
                check_title(tagged, self.notice.title)
                self.assertEqual(self.client.get(self.detail).status_code, 200 if allowed else 403)
                download = self.client.get(self.download)
                self.assertEqual(download.status_code, 200 if allowed else 403)
                if allowed:
                    self.assertEqual(b"".join(download.streaming_content), b"committee-only briefing")
                download.close()
                # Authors cannot mark their own announcement as read (#39).
                can_mark = allowed and user != self.officer
                self.assertEqual(self.client.post(self.read).status_code, 302 if can_mark else 403)
                self.assertEqual(
                    AnnouncementReadReceipt.objects.filter(user=user, announcement=self.notice).exists(), can_mark,
                )

    def test_membership_removal_and_unpublished_status_revoke_access(self):
        self.login(self.member)
        Announcement.objects.filter(pk=self.notice.pk).update(status="draft")
        self.assertEqual(self.client.get(self.detail).status_code, 403)
        Announcement.objects.filter(pk=self.notice.pk).update(status="published")
        self.assertEqual(self.client.get(self.detail).status_code, 200)
        self.membership.delete()
        self.assertEqual(self.client.get(self.download).status_code, 403)

    def test_targeted_notice_prevents_committee_deletion(self):
        self.login(self.admin)
        self.client.post(reverse("committees:delete", args=[self.committee.pk]))
        self.notice.refresh_from_db()
        self.assertEqual(self.notice.committee_id, self.committee.pk)
        self.assertTrue(CommitteeMember.objects.filter(pk=self.membership.pk).exists())

    def test_officer_can_set_audience_and_tags_and_explicitly_clear_audience(self):
        # Officers can only target committees they belong to (#39).
        CommitteeMember.objects.create(committee=self.committee, user=self.officer)
        self.login(self.officer)
        data = {
            "title": "New workshop",
            "content": "Bring ideas.",
            "status": "published",
            "target_reach": 165,
            "committee": str(self.committee.pk),
            "tags": " Workshop, planning, WORKSHOP ",
        }
        response = self.client.post(reverse("announcements:create"), data)
        notice = Announcement.objects.get(title=data["title"])
        detail = reverse("announcements:detail", args=[notice.pk])
        self.assertRedirects(response, detail)
        self.assertEqual(notice.committee_id, self.committee.pk)
        self.assertEqual(notice.tags, ["workshop", "planning"])
        edit = reverse("announcements:edit", args=[notice.pk])
        self.assertContains(self.client.get(edit), "workshop, planning")
        data.pop("committee")
        self.assertRedirects(self.client.post(edit, data), detail)
        notice.refresh_from_db()
        self.assertEqual(notice.committee_id, self.committee.pk)
        self.assertRedirects(self.client.post(edit, {**data, "committee": ""}), detail)
        notice.refresh_from_db()
        self.assertIsNone(notice.committee_id)


    def test_officer_cannot_target_a_committee_they_are_not_in(self):
        self.login(self.officer)
        response = self.client.post(reverse("announcements:create"), {
            "title": "Outside notice", "content": "Body.", "committee": str(self.committee.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("committee", response.context["form"].errors)
        self.assertFalse(Announcement.objects.filter(title="Outside notice").exists())


class TagFilterTests(AnnouncementTestDataMixin, TestCase):
    def test_announcement_tags_combine_with_category_and_keyword(self):
        category = self.make_category()
        self.make_announcement(title="Workshop agenda", category=category, tags=["planning"])
        self.make_announcement(title="Workshop outline", category=category, tags=["preplanning"])
        self.make_announcement(title="Workshop packet", tags=["planning"])
        self.make_announcement(title="Retreat agenda", category=category, tags=["planning"])
        self.login(self.make_user())
        response = self.client.get(reverse("announcements:list"), {
            "tag": " Planning ", "category": category.slug, "q": "workshop",
        })
        self.assertEqual([notice.title for notice in response.context["announcements"]], ["Workshop agenda"])

    def test_officer_can_save_resource_tags_and_member_can_combine_filters(self):
        self.login(self.make_officer())
        url = reverse("resources:create")
        data = {"title": "Workshop handbook", "category": "Guides", "url": "https://example.com/"}
        response = self.client.post(url, {**data, "tags": "x" * 33})
        self.assertIn("tags", response.context["form"].errors)
        self.assertRedirects(self.client.post(url, {**data, "tags": "Planning, PLANNING"}), reverse("resources:list"))
        self.assertEqual(Resource.objects.get(title=data["title"]).tags, ["planning"])
        Resource.objects.create(title="Workshop minutes", category="Guides", tags=["preplanning"])
        Resource.objects.create(title="Workshop notes", category="Meeting", tags=["planning"])
        Resource.objects.create(title="Retreat handbook", category="Guides", tags=["planning"])
        self.login(self.make_user())
        response = self.client.get(reverse("resources:list"), {"tag": "PLANNING", "category": "Guides", "q": "workshop"})
        self.assertEqual([resource.title for resource in response.context["resources"]], ["Workshop handbook"])
