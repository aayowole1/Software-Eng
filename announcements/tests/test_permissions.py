"""Exercise organization roles and current-account access across announcements."""

from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.models import Profile, Role
from membership.models import MembershipApplication

from announcements.models import AnnouncementAttachment, AnnouncementReadReceipt
from announcements.views import announcement_create

from .test_support import AnnouncementTestDataMixin


class AnnouncementPermissionTests(AnnouncementTestDataMixin, TestCase):
    def setUp(self):
        self.officer = self.make_officer()
        self.member = self.make_user()
        self.notice = self.make_announcement(author=self.officer, status="draft")
        self.detail = reverse("announcements:detail", args=[self.notice.pk])
        self.edit = reverse("announcements:edit", args=[self.notice.pk])
        self.read = reverse("announcements:mark_read", args=[self.notice.pk])
        self.create = reverse("announcements:create")
        self.attachment = AnnouncementAttachment.objects.create(
            announcement=self.notice,
            file=SimpleUploadedFile("private.txt", b"private minutes"),
            name="Private minutes.txt",
        )
        self.download = reverse("announcements:attachment_download", args=[self.attachment.pk])

    def test_profile_officer_without_staff_or_group_can_publish(self):
        self.assertFalse(self.officer.is_staff)
        self.assertFalse(self.officer.groups.exists())
        self.login(self.officer)
        self.assertEqual(self.client.get(self.create).status_code, 200)

    def test_staff_or_group_members_do_not_gain_organization_authority(self):
        for kwargs in ({"is_staff": True}, {}):
            with self.subTest(kwargs=kwargs):
                user = self.make_user(**kwargs)
                if not kwargs:
                    user.groups.add(Group.objects.get_or_create(name="Officer")[0])
                self.login(user)
                for url in (self.create, self.edit, self.detail, self.download):
                    self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(self.read).status_code, 403)
                self.assertFalse(AnnouncementReadReceipt.objects.filter(user=user).exists())

    def test_organization_admin_can_edit_another_authors_notice(self):
        admin = self.make_user(role=Role.ADMIN)
        self.login(admin)
        response = self.client.get(self.edit)
        self.assertEqual(response.status_code, 200)
        response = self.client.get(self.detail)
        self.assertTrue(response.context["can_edit"])

    def test_applicant_cannot_read_published_announcements_or_files(self):
        self.notice.status = "published"
        self.notice.save(update_fields=["status"])
        self.login(self.make_user(role=Role.APPLICANT))
        for url in (reverse("announcements:list"), self.detail, self.download):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_member_downloads_published_attachment_as_private_download(self):
        self.notice.status = "published"
        self.notice.save(update_fields=["status"])
        self.login(self.member)
        response = self.client.get(self.download)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"private minutes")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        response.close()

    def test_read_endpoint_requires_post(self):
        self.login(self.officer)
        self.assertEqual(self.client.get(self.read).status_code, 405)

    def test_role_change_after_request_loaded_is_respected(self):
        request = RequestFactory().get(self.create)
        request.user = self.officer
        Profile.objects.filter(user=self.officer).update(role=Role.MEMBER)
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            announcement_create(request)

    def test_current_account_safety_markers_block_direct_requests(self):
        from django.core.exceptions import PermissionDenied
        request = RequestFactory().get(self.create)
        request.user = self.officer
        for changes in ({"is_suspended": True}, {"suspension_update_pending": True}):
            with self.subTest(changes=changes):
                Profile.objects.filter(user=self.officer).update(**changes)
                with self.assertRaises(PermissionDenied):
                    announcement_create(request)
                Profile.objects.filter(user=self.officer).update(
                    is_suspended=False, suspension_update_pending=False,
                )
        self.officer.is_active = False
        self.officer.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            announcement_create(request)

    def test_pending_membership_access_blocks_direct_request(self):
        from django.core.exceptions import PermissionDenied
        MembershipApplication.objects.create(user=self.officer, statement="Join", access_update_pending=True)
        request = RequestFactory().get(self.create)
        request.user = self.officer
        with self.assertRaises(PermissionDenied):
            announcement_create(request)

    def test_download_requires_login(self):
        response = self.client.get(self.download)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_member_page_keeps_real_admin_navigation_hidden(self):
        self.login(self.officer)
        response = self.client.get(reverse("announcements:list"))
        self.assertContains(response, "Create announcement")
        self.assertNotContains(response, reverse("accounts:user_list"))

    def test_upload_limit_rejects_before_saving(self):
        self.login(self.officer)
        files = [SimpleUploadedFile(f"{i}.txt", b"test") for i in range(6)]
        response = self.client.post(self.create, {
            "title": "Too many files", "content": "Notice", "status": "published",
            "category": self.notice.category_id, "target_reach": 20, "attachments": files,
        })
        self.assertContains(response, "Upload up to 5 files")
        self.assertFalse(type(self.notice).objects.filter(title="Too many files").exists())
