"""Tests for in-app notifications (SCRUM-99 / US-21)."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember

from announcements.models import Announcement, Category
from tasks.services import create_task, update_task

from notifications.models import Notification, NotificationKind
from notifications.services import notify_announcement_published, notify_task_assigned

User = get_user_model()


def _make_announcement(author, status="published", title="Test announcement"):
    cat, _ = Category.objects.get_or_create(name="General", slug="general")
    return Announcement.objects.create(
        title=title,
        content="Some content.",
        status=status,
        author=author,
        category=cat,
        author_role="Officer",
    )


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AnnouncementNotificationTests(TestCase):
    def setUp(self):
        self.officer = make_user("notif-officer@example.com", Role.OFFICER)
        self.member1 = make_user("notif-member1@example.com", Role.MEMBER)
        self.member2 = make_user("notif-member2@example.com", Role.MEMBER)
        self.applicant = make_user("notif-applicant@example.com")

    def test_publishing_notifies_all_members_and_officers(self):
        announcement = _make_announcement(self.officer, status="published")
        notify_announcement_published(announcement)
        # Officer and both members get notified; applicant is excluded.
        recipients = set(Notification.objects.filter(
            kind=NotificationKind.ANNOUNCEMENT,
            object_id=str(announcement.pk),
        ).values_list("user_id", flat=True))
        self.assertIn(self.member1.pk, recipients)
        self.assertIn(self.member2.pk, recipients)
        self.assertIn(self.officer.pk, recipients)
        self.assertNotIn(self.applicant.pk, recipients)

    def test_publishing_via_view_creates_notifications(self):
        self.client.force_login(self.officer)
        cat, _ = Category.objects.get_or_create(name="General", slug="general")
        response = self.client.post(reverse("announcements:create"), {
            "title": "Big news",
            "content": "Details here.",
            "status": "published",
            "category": str(cat.pk),
            "target_reach": "50",
        })
        self.assertEqual(response.status_code, 302)
        ann = Announcement.objects.get(title="Big news")
        count = Notification.objects.filter(
            kind=NotificationKind.ANNOUNCEMENT,
            object_id=str(ann.pk),
        ).count()
        self.assertGreater(count, 0)

    def test_editing_already_published_announcement_does_not_re_notify(self):
        self.client.force_login(self.officer)
        announcement = _make_announcement(self.officer, status="published", title="Existing news")
        # Trigger the initial notification manually (simulating initial publish)
        notify_announcement_published(announcement)
        initial_count = Notification.objects.filter(
            kind=NotificationKind.ANNOUNCEMENT,
            object_id=str(announcement.pk),
        ).count()

        # Edit while keeping status=published — should not create more notifications.
        cat, _ = Category.objects.get_or_create(name="General", slug="general")
        self.client.post(reverse("announcements:edit", args=[announcement.pk]), {
            "title": "Existing news (updated)",
            "content": "More details.",
            "status": "published",
            "category": str(cat.pk),
            "target_reach": "50",
        })
        after_count = Notification.objects.filter(
            kind=NotificationKind.ANNOUNCEMENT,
            object_id=str(announcement.pk),
        ).count()
        self.assertEqual(after_count, initial_count)

    def test_draft_to_published_via_edit_notifies(self):
        self.client.force_login(self.officer)
        announcement = _make_announcement(self.officer, status="draft", title="Draft post")
        before = Notification.objects.filter(
            kind=NotificationKind.ANNOUNCEMENT,
            object_id=str(announcement.pk),
        ).count()
        self.assertEqual(before, 0)

        cat, _ = Category.objects.get_or_create(name="General", slug="general")
        self.client.post(reverse("announcements:edit", args=[announcement.pk]), {
            "title": "Draft post",
            "content": "Now published.",
            "status": "published",
            "category": str(cat.pk),
            "target_reach": "50",
        })
        after = Notification.objects.filter(
            kind=NotificationKind.ANNOUNCEMENT,
            object_id=str(announcement.pk),
        ).count()
        self.assertGreater(after, 0)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaskNotificationTests(TestCase):
    def setUp(self):
        self.officer = make_user("task-notif-officer@example.com", Role.OFFICER)
        self.member = make_user("task-notif-member@example.com", Role.MEMBER)
        self.other = make_user("task-notif-other@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Outreach", created_by=self.officer)
        CommitteeMember.objects.create(committee=self.committee, user=self.member)
        CommitteeMember.objects.create(committee=self.committee, user=self.other)

    def _task(self, **kw):
        return create_task(self.officer, title="Do the thing", committee=self.committee, **kw)

    def test_creating_task_with_assignee_notifies_assignee(self):
        task = self._task(assignee=self.member)
        notifs = Notification.objects.filter(
            user=self.member,
            kind=NotificationKind.TASK,
            object_id=str(task.pk),
        )
        self.assertEqual(notifs.count(), 1)

    def test_creating_task_without_assignee_creates_no_notification(self):
        task = self._task()
        self.assertEqual(Notification.objects.filter(kind=NotificationKind.TASK, object_id=str(task.pk)).count(), 0)

    def test_reassigning_task_notifies_new_assignee(self):
        task = self._task(assignee=self.member)
        Notification.objects.all().delete()
        task.refresh_from_db()
        update_task(self.officer, task, {"assignee": self.other}, task.version)
        self.assertEqual(
            Notification.objects.filter(user=self.other, kind=NotificationKind.TASK, object_id=str(task.pk)).count(),
            1,
        )

    def test_reassigning_to_same_assignee_creates_no_duplicate(self):
        task = self._task(assignee=self.member)
        Notification.objects.all().delete()
        task.refresh_from_db()
        # Update a field other than assignee; assignee stays the same.
        update_task(self.officer, task, {"title": "Updated title"}, task.version)
        self.assertEqual(
            Notification.objects.filter(user=self.member, kind=NotificationKind.TASK, object_id=str(task.pk)).count(),
            0,
        )

    def test_claiming_task_does_not_notify(self):
        from tasks.services import claim_task
        task = self._task()  # no assignee
        task.refresh_from_db()
        self.client.force_login(self.member)
        claim_task(self.member, task, task.version)
        self.assertEqual(Notification.objects.filter(kind=NotificationKind.TASK).count(), 0)

    def test_unassigning_task_creates_no_notification(self):
        task = self._task(assignee=self.member)
        Notification.objects.all().delete()
        task.refresh_from_db()
        update_task(self.officer, task, {"assignee": None}, task.version)
        self.assertEqual(Notification.objects.filter(kind=NotificationKind.TASK).count(), 0)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NotificationVisibilityTests(TestCase):
    def setUp(self):
        self.user_a = make_user("vis-a@example.com", Role.MEMBER)
        self.user_b = make_user("vis-b@example.com", Role.MEMBER)
        self.officer = make_user("vis-officer@example.com", Role.OFFICER)

    def _notif(self, user, headline="Hello"):
        ann = _make_announcement(self.officer, status="published", title=headline)
        return Notification.objects.create(
            user=user,
            kind=NotificationKind.ANNOUNCEMENT,
            object_id=str(ann.pk),
            headline=headline,
        )

    def test_user_only_sees_own_notifications(self):
        n_a = self._notif(self.user_a, "For A")
        n_b = self._notif(self.user_b, "For B")
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "For A")
        self.assertNotContains(response, "For B")

    def test_cannot_follow_another_users_notification(self):
        n_b = self._notif(self.user_b, "Secret B")
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("notifications:read", args=[n_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_redirected_from_list(self):
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.status_code, 302)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UnreadCountAndMarkReadTests(TestCase):
    def setUp(self):
        self.user = make_user("read-user@example.com", Role.MEMBER)
        self.officer = make_user("read-officer@example.com", Role.OFFICER)

    def _notif(self):
        ann = _make_announcement(self.officer, status="published")
        return Notification.objects.create(
            user=self.user,
            kind=NotificationKind.ANNOUNCEMENT,
            object_id=str(ann.pk),
            headline="Test headline",
        )

    def test_unread_count_shown_in_sidebar(self):
        self._notif()
        self._notif()
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "2")
        self.assertContains(response, "sidebar-notification-dot")

    def test_following_notification_link_marks_it_read(self):
        n = self._notif()
        self.assertFalse(n.is_read)
        self.client.force_login(self.user)
        # Visiting the read view should mark it read and redirect.
        response = self.client.get(reverse("notifications:read", args=[n.pk]))
        self.assertEqual(response.status_code, 302)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_mark_all_as_read_clears_unread_count(self):
        self._notif()
        self._notif()
        self.client.force_login(self.user)
        self.client.post(reverse("notifications:mark_all_read"))
        self.assertEqual(
            Notification.objects.filter(user=self.user, is_read=False).count(), 0
        )

    def test_unread_count_zero_after_mark_all(self):
        self._notif()
        self.client.force_login(self.user)
        self.client.post(reverse("notifications:mark_all_read"))
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.context["unread_count"], 0)
        self.assertNotContains(response, "sidebar-notification-dot")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReviewFollowUpTests(TestCase):
    """Chau's review on #32: lookup failure, concurrent reassignment, demoted members."""

    def setUp(self):
        self.officer = make_user("review-officer@example.com", Role.OFFICER)
        self.member = make_user("review-member@example.com", Role.MEMBER)
        self.other = make_user("review-other@example.com", Role.MEMBER)
        self.third = make_user("review-third@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Logistics", created_by=self.officer)
        for user in (self.member, self.other, self.third):
            CommitteeMember.objects.create(committee=self.committee, user=user)

    def test_publish_still_succeeds_when_recipient_lookup_fails(self):
        from unittest import mock
        from django.db import DatabaseError

        self.client.force_login(self.officer)
        cat, _ = Category.objects.get_or_create(name="General", slug="general")
        with mock.patch("tasks.models.eligible_assignees", side_effect=DatabaseError("lookup down")), \
                self.assertLogs("notifications.services", level="ERROR"):
            response = self.client.post(reverse("announcements:create"), {
                "title": "Still published", "content": "Body.", "status": "published",
                "category": str(cat.pk), "target_reach": "50",
            })
        self.assertEqual(response.status_code, 302)
        ann = Announcement.objects.get(title="Still published")
        self.assertEqual(ann.status, "published")
        self.assertFalse(Notification.objects.filter(object_id=str(ann.pk)).exists())

    def test_concurrent_reassignment_alerts_only_the_assignee_this_write_stored(self):
        from unittest import mock
        from django.db.models import F
        from tasks.models import Task

        task = create_task(self.officer, title="Book the room", committee=self.committee, assignee=self.member)
        Notification.objects.all().delete()
        task.refresh_from_db()
        original_refresh = Task.refresh_from_db

        def refresh_after_another_reassignment(instance, *args, **kwargs):
            # Another officer's save lands between this write and its re-read.
            Task.objects.filter(pk=instance.pk).update(assignee_id=self.third.pk, version=F("version") + 1)
            return original_refresh(instance, *args, **kwargs)

        with mock.patch.object(Task, "refresh_from_db", autospec=True, side_effect=refresh_after_another_reassignment):
            update_task(self.officer, task, {"assignee": self.other}, task.version)

        alerts = list(Notification.objects.filter(kind=NotificationKind.TASK).values_list("user_id", "headline"))
        self.assertEqual(alerts, [(self.other.pk, "You have been assigned a task: Book the room")])

    def test_demoted_applicant_no_longer_sees_task_or_announcement_headlines(self):
        from accounts.models import set_role

        task = create_task(self.officer, title="Secret budget review", committee=self.committee, assignee=self.member)
        notify_announcement_published(_make_announcement(self.officer, title="Members-only news"))
        task_note = Notification.objects.get(user=self.member, kind=NotificationKind.TASK, object_id=str(task.pk))
        set_role(self.member, Role.APPLICANT)

        self.client.force_login(self.member)
        response = self.client.get(reverse("notifications:list"))
        self.assertNotContains(response, "Secret budget review")
        self.assertNotContains(response, "Members-only news")
        self.assertEqual(response.context["unread_notification_count"], 0)
        self.assertEqual(self.client.get(reverse("notifications:read", args=[task_note.pk])).status_code, 404)
        # Kept, not deleted: they come back if membership is restored.
        self.assertTrue(Notification.objects.filter(pk=task_note.pk).exists())
        set_role(self.member, Role.MEMBER)
        self.assertContains(self.client.get(reverse("notifications:list")), "Secret budget review")

    def test_member_moved_off_committee_no_longer_sees_its_task_headline(self):
        create_task(self.officer, title="Committee-only task", committee=self.committee, assignee=self.member)
        CommitteeMember.objects.filter(committee=self.committee, user=self.member).delete()
        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(reverse("notifications:list")), "Committee-only task")


def _has_committee_audience():
    return any(field.name == "committee" for field in Announcement._meta.get_fields())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AnnouncementAudienceNotificationTests(TestCase):
    """Announcement notifications follow who can open the announcement."""

    def setUp(self):
        self.officer = make_user("aud-officer@example.com", Role.OFFICER)
        self.insider = make_user("aud-insider@example.com", Role.MEMBER)
        self.outsider = make_user("aud-outsider@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Budget", created_by=self.officer)
        CommitteeMember.objects.create(committee=self.committee, user=self.insider)

    def _headline_shown_to(self, user, text):
        self.client.force_login(user)
        return text in self.client.get(reverse("notifications:list")).content.decode()

    def test_unpublished_announcement_notification_is_hidden_from_members(self):
        announcement = _make_announcement(self.officer, title="Withdrawn notice")
        notify_announcement_published(announcement)
        Announcement.objects.filter(pk=announcement.pk).update(status="draft")
        self.assertFalse(self._headline_shown_to(self.insider, "Withdrawn notice"))
        self.assertTrue(self._headline_shown_to(self.officer, "Withdrawn notice"))

    def test_committee_announcement_notifies_only_that_committee(self):
        if not _has_committee_audience():
            self.skipTest("Committee audiences arrive with SCRUM-95 (#30).")
        announcement = _make_announcement(self.officer, title="Budget-only notice")
        Announcement.objects.filter(pk=announcement.pk).update(committee=self.committee)
        announcement.refresh_from_db()
        notify_announcement_published(announcement)
        recipients = set(Notification.objects.filter(object_id=str(announcement.pk)).values_list("user_id", flat=True))
        self.assertEqual(recipients, {self.insider.pk})
        self.assertTrue(self._headline_shown_to(self.insider, "Budget-only notice"))

    def test_announcement_retargeted_to_a_committee_hides_old_notifications_from_outsiders(self):
        if not _has_committee_audience():
            self.skipTest("Committee audiences arrive with SCRUM-95 (#30).")
        announcement = _make_announcement(self.officer, title="Narrowed notice")
        notify_announcement_published(announcement)
        Announcement.objects.filter(pk=announcement.pk).update(committee=self.committee)
        self.assertFalse(self._headline_shown_to(self.outsider, "Narrowed notice"))
        self.assertTrue(self._headline_shown_to(self.insider, "Narrowed notice"))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ScheduledAnnouncementNotificationTests(TestCase):
    def test_scheduled_announcement_notifies_once_when_it_goes_live(self):
        from datetime import timedelta
        from django.utils import timezone
        from announcements.views import publish_due_announcements

        officer = make_user("sched-officer@example.com", Role.OFFICER)
        member = make_user("sched-member@example.com", Role.MEMBER)
        announcement = _make_announcement(officer, status="scheduled", title="Scheduled notice")
        Announcement.objects.filter(pk=announcement.pk).update(scheduled_for=timezone.now() - timedelta(minutes=1))
        self.assertEqual(publish_due_announcements(), 1)
        self.assertEqual(publish_due_announcements(), 0)
        self.assertEqual(
            Notification.objects.filter(user=member, object_id=str(announcement.pk)).count(), 1,
        )
