from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from accounts.models import Profile, Role
from committees.models import Committee, CommitteeMember
from announcements.forms import ResourceForm
from announcements.models import Announcement, AnnouncementAttachment, AnnouncementReadReceipt, Resource
from announcements.resource_views import resource_list
from .test_support import AnnouncementTestDataMixin


class ResourceLibraryTests(AnnouncementTestDataMixin, TestCase):
    def setUp(self):
        self.officer = self.make_officer()
        self.member = self.make_user()
        self.resource = Resource.objects.create(title="Officer handbook", description="Election guidelines",
            category="Guides", url="https://example.org/handbook", created_by=self.officer)
        self.list_url = reverse("resources:list")
        self.create_url = reverse("resources:create")
        self.edit_url = reverse("resources:edit", args=[self.resource.pk])
        self.delete_url = reverse("resources:delete", args=[self.resource.pk])
        self.open_url = reverse("resources:open", args=[self.resource.pk])

    def test_member_browses_and_searches_titles_and_descriptions(self):
        self.login(self.member)
        for query in ("handbook", "Election"):
            response = self.client.get(self.list_url, {"q": query})
            self.assertContains(response, "Officer handbook")
        self.assertNotContains(self.client.get(self.list_url, {"q": "missing"}), "Officer handbook")
        self.assertNotContains(self.client.get(self.list_url), "Add resource")

    def test_category_filter_and_empty_state(self):
        self.login(self.member)
        self.assertContains(self.client.get(self.list_url, {"category": "Guides"}), "Officer handbook")
        self.assertContains(self.client.get(self.list_url, {"category": "Other"}), "No resources match")

    def test_member_opens_valid_external_link(self):
        self.login(self.member)
        response = self.client.get(self.open_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://example.org/handbook")
        self.assertEqual(response["Cache-Control"], "private, no-store")

    def test_member_downloads_private_file(self):
        file_resource = Resource.objects.create(title="Minutes", file=SimpleUploadedFile("minutes.txt", b"Meeting minutes"))
        self.login(self.member)
        response = self.client.get(reverse("resources:open", args=[file_resource.pk]))
        self.assertEqual(b"".join(response.streaming_content), b"Meeting minutes")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        response.close()

    def test_anonymous_and_applicant_cannot_access_library_or_open_resource(self):
        for url in (self.list_url, self.open_url):
            self.assertEqual(self.client.get(url).status_code, 302)
        self.login(self.make_user(role=Role.APPLICANT))
        for url in (self.list_url, self.open_url):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_member_cannot_create_edit_or_remove_resources(self):
        self.login(self.member)
        for url in (self.create_url, self.edit_url, self.delete_url):
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {"title": "Tampered"}).status_code, 403)
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.title, "Officer handbook")

    def test_staff_and_group_flags_do_not_grant_resource_management(self):
        user = self.make_user(is_staff=True)
        user.groups.add(Group.objects.create(name="Officer"))
        self.login(user)
        self.assertEqual(self.client.post(self.delete_url).status_code, 403)

    def test_suspension_after_request_loaded_blocks_library(self):
        from django.core.exceptions import PermissionDenied
        request = RequestFactory().get(self.list_url)
        request.user = self.member
        Profile.objects.filter(user=self.member).update(is_suspended=True)
        with self.assertRaises(PermissionDenied):
            resource_list(request)

    def test_officer_creates_link_and_file_resources(self):
        self.login(self.officer)
        for data in (
            {"title": "Constitution", "url": "https://example.org/constitution"},
            {"title": "Agenda", "file": SimpleUploadedFile("agenda.txt", b"agenda")},
        ):
            response = self.client.post(self.create_url, data)
            self.assertRedirects(response, self.list_url)
            self.assertEqual(Resource.objects.get(title=data["title"]).created_by, self.officer)

    def test_admin_can_update_resource_owned_by_officer(self):
        self.login(self.make_user(role=Role.ADMIN))
        response = self.client.post(self.edit_url, {"title": "Updated handbook", "url": "https://example.org/new"})
        self.assertRedirects(response, self.list_url)
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.title, "Updated handbook")
        self.assertEqual(self.resource.created_by, self.officer)

    def test_delete_get_confirms_post_removes_and_open_becomes_unavailable(self):
        self.login(self.officer)
        self.assertContains(self.client.get(self.delete_url), "Officer handbook")
        self.assertTrue(Resource.objects.filter(pk=self.resource.pk).exists())
        self.assertRedirects(self.client.post(self.delete_url), self.list_url)
        self.login(self.member)
        self.assertEqual(self.client.get(self.open_url).status_code, 404)

    def test_mutations_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.officer)
        for url in (self.create_url, self.edit_url, self.delete_url):
            self.assertEqual(client.post(url).status_code, 403)

    def test_form_rejects_both_or_neither_file_and_link(self):
        for data, files in (({"title": "Neither"}, {}),
            ({"title": "Both", "url": "https://example.org"}, {"file": SimpleUploadedFile("a.txt", b"a")})):
            self.assertFalse(ResourceForm(data=data, files=files).is_valid())

    def test_invalid_schemes_are_rejected_on_save_and_open(self):
        for url in ("javascript:alert(1)", "file:///private.txt", "ftp://example.org/test"):
            self.assertFalse(ResourceForm(data={"title": "Bad link", "url": url}).is_valid())
            Resource.objects.filter(pk=self.resource.pk).update(url=url)
            self.login(self.member)
            self.assertEqual(self.client.get(self.open_url).status_code, 404)

    def test_oversized_upload_is_rejected(self):
        upload = SimpleUploadedFile("large.txt", b"small")
        upload.size = 25 * 1024 * 1024 + 1
        form = ResourceForm(data={"title": "Too large"}, files={"file": upload})
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_file_can_be_replaced_or_switched_to_link_without_public_media_url(self):
        self.resource.url = ""
        self.resource.file.save("old.txt", SimpleUploadedFile("old.txt", b"old"))
        self.login(self.officer)
        response = self.client.get(self.edit_url)
        self.assertNotContains(response, self.resource.file.url)
        response = self.client.post(self.edit_url, {"title": "Replaced", "file": SimpleUploadedFile("new.txt", b"new")})
        self.assertRedirects(response, self.list_url)
        response = self.client.post(self.edit_url, {"title": "Link now", "remove_file": "on", "url": "https://example.org/new"})
        self.assertRedirects(response, self.list_url)
        self.resource.refresh_from_db()
        self.assertFalse(self.resource.file)

    def test_missing_file_returns_404(self):
        self.resource.url = ""
        self.resource.file = "resources/missing.txt"
        self.resource.save()
        self.login(self.member)
        self.assertEqual(self.client.get(self.open_url).status_code, 404)

    def test_missing_stored_file_does_not_block_metadata_repair(self):
        self.resource.url = ""
        self.resource.file = "resources/missing.txt"
        self.resource.save()
        form = ResourceForm(data={"title": "Needs replacement", "url": ""}, instance=self.resource)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.title, "Needs replacement")


class AnnouncementDeletionTests(AnnouncementTestDataMixin, TestCase):
    def setUp(self):
        self.author = self.make_officer()
        self.notice = self.make_announcement(author=self.author)
        self.url = reverse("announcements:delete", args=[self.notice.pk])

    def test_author_confirms_then_deletes_notice_and_dependent_rows(self):
        member = self.make_user()
        AnnouncementReadReceipt.objects.create(user=member, announcement=self.notice)
        attachment = AnnouncementAttachment.objects.create(announcement=self.notice, name="agenda", file=SimpleUploadedFile("agenda.txt", b"a"))
        self.login(self.author)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertTrue(Announcement.objects.filter(pk=self.notice.pk).exists())
        self.assertRedirects(self.client.post(self.url), reverse("announcements:list"))
        self.assertFalse(AnnouncementReadReceipt.objects.filter(announcement=self.notice).exists())
        self.assertFalse(AnnouncementAttachment.objects.filter(pk=attachment.pk).exists())
        self.assertEqual(self.client.get(reverse("announcements:attachment_download", args=[attachment.pk])).status_code, 404)

    def test_member_and_other_officer_cannot_delete(self):
        for user in (self.make_user(), self.make_officer()):
            self.login(user)
            self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertTrue(Announcement.objects.filter(pk=self.notice.pk).exists())

    def test_admin_can_delete_another_authors_notice(self):
        self.login(self.make_user(role=Role.ADMIN))
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.assertFalse(Announcement.objects.filter(pk=self.notice.pk).exists())

    def test_delete_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.author)
        self.assertEqual(client.post(self.url).status_code, 403)
        self.assertTrue(Announcement.objects.filter(pk=self.notice.pk).exists())


class DashboardAnnouncementTests(AnnouncementTestDataMixin, TestCase):
    def setUp(self):
        self.officer = self.make_officer()
        self.make_announcement(author=self.officer, title="Published dashboard notice")
        self.make_announcement(author=self.officer, title="Private dashboard draft", status="draft")
        self.url = reverse("core:dashboard")

    def test_member_and_officer_see_published_not_draft_notices(self):
        for user in (self.make_user(), self.officer):
            self.login(user)
            response = self.client.get(self.url)
            self.assertContains(response, "Published dashboard notice")
            self.assertNotContains(response, "Private dashboard draft")

    def test_anonymous_and_applicant_dashboard_does_not_expose_notices(self):
        self.assertNotContains(self.client.get(self.url), "Published dashboard notice")
        self.login(self.make_user(role=Role.APPLICANT))
        self.assertNotContains(self.client.get(self.url), "Published dashboard notice")

    def test_dashboard_limits_recent_announcements_to_three(self):
        for number in range(4):
            self.make_announcement(author=self.officer, title=f"Recent notice {number}")
        self.login(self.make_user())
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["recent_announcements"]), 3)
        self.assertNotContains(response, "Published dashboard notice")

    def test_dashboard_hides_announcement_for_non_committee_member(self):
        committee = Committee.objects.create(name="Outreach")
        notice = self.make_announcement(
            author=self.officer,
            title="Committee-only dashboard notice",
            committee=committee,
        )
        outsider = self.make_user()
        self.login(outsider)
        self.assertNotContains(self.client.get(self.url), notice.title)

        CommitteeMember.objects.create(committee=committee, user=outsider)
        self.assertContains(self.client.get(self.url), notice.title)
