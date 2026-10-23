from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.testing import make_user

from .models import RSVP, Attendance, Event, RSVPResponse


def in_days(days):
    return timezone.now() + timedelta(days=days)


class EventTests(TestCase):
    def setUp(self):
        self.officer = make_user("officer@example.com", Role.OFFICER)
        self.member = make_user("member@example.com", Role.MEMBER)
        self.member2 = make_user("member2@example.com", Role.MEMBER)
        self.applicant = make_user("applicant@example.com")

    def make_event(self, days=7, **kwargs):
        fields = {"title": "Hackathon kickoff", "location": "Engineering atrium", "starts_at": in_days(days)}
        fields.update(kwargs)
        return Event.objects.create(created_by=self.officer, **fields)

    def post_event(self, **overrides):
        data = {
            "title": "Hackathon kickoff",
            "starts_at": in_days(7).strftime("%Y-%m-%dT%H:%M"),
            "ends_at": "",
            "location": "Engineering atrium",
            "description": "Teams and rules",
        }
        data.update(overrides)
        return self.client.post(reverse("events:create"), data)

    # --- Creating and managing (officers) --------------------------------
    def test_officer_creates_event(self):
        self.client.force_login(self.officer)
        response = self.post_event()
        event = Event.objects.get()
        self.assertRedirects(response, reverse("events:detail", args=[event.pk]))
        self.assertEqual(event.created_by, self.officer)
        self.assertFalse(event.cancelled)

    def test_title_start_and_location_required(self):
        self.client.force_login(self.officer)
        for field in ["title", "starts_at", "location"]:
            with self.subTest(field=field):
                self.post_event(**{field: ""})
                self.assertFalse(Event.objects.exists())

    def test_end_must_be_after_start(self):
        self.client.force_login(self.officer)
        start = in_days(7)
        response = self.post_event(
            starts_at=start.strftime("%Y-%m-%dT%H:%M"),
            ends_at=(start - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        )
        self.assertContains(response, "must be after the start time")
        self.assertFalse(Event.objects.exists())

    def test_members_cannot_create_edit_or_cancel(self):
        event = self.make_event()
        self.client.force_login(self.member)
        self.assertEqual(self.post_event().status_code, 403)
        self.assertEqual(self.client.get(reverse("events:edit", args=[event.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("events:cancel", args=[event.pk])).status_code, 403)
        event.refresh_from_db()
        self.assertFalse(event.cancelled)

    def test_officer_edits_event(self):
        event = self.make_event()
        self.client.force_login(self.officer)
        self.client.post(reverse("events:edit", args=[event.pk]), {
            "title": "Hackathon kickoff (moved)",
            "starts_at": in_days(8).strftime("%Y-%m-%dT%H:%M"),
            "ends_at": "",
            "location": "Library room 2",
            "description": "",
        })
        event.refresh_from_db()
        self.assertEqual(event.title, "Hackathon kickoff (moved)")
        self.assertEqual(event.location, "Library room 2")

    def test_officer_cancels_event(self):
        event = self.make_event()
        self.client.force_login(self.officer)
        self.client.post(reverse("events:cancel", args=[event.pk]))
        event.refresh_from_db()
        self.assertTrue(event.cancelled)

    def test_past_events_cannot_be_cancelled(self):
        event = self.make_event(days=-1)
        self.client.force_login(self.officer)
        self.assertNotContains(self.client.get(reverse("events:detail", args=[event.pk])), "Cancel event")
        self.client.post(reverse("events:cancel", args=[event.pk]))
        event.refresh_from_db()
        self.assertFalse(event.cancelled)

    # --- Viewing ------------------------------------------------------------
    def test_members_see_upcoming_and_past_events(self):
        self.make_event(days=3, title="Upcoming social")
        self.make_event(days=-3, title="Last week's meeting")
        self.client.force_login(self.member)
        response = self.client.get(reverse("events:list"))
        self.assertContains(response, "Upcoming social")
        self.assertContains(response, "Last week&#x27;s meeting")

    def test_applicants_and_visitors_cannot_see_events(self):
        event = self.make_event()
        self.client.force_login(self.applicant)
        self.assertEqual(self.client.get(reverse("events:list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("events:detail", args=[event.pk])).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("events:list")).status_code, 302)

    def test_unknown_event_is_404(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("events:detail", args=["0123456789abcdef01234567"]))
        self.assertEqual(response.status_code, 404)

    # --- RSVP -----------------------------------------------------------------
    def rsvp(self, event, response):
        return self.client.post(reverse("events:rsvp", args=[event.pk]), {"response": response})

    def test_member_rsvps_and_can_change_answer(self):
        event = self.make_event()
        self.client.force_login(self.member)
        self.rsvp(event, RSVPResponse.GOING)
        self.rsvp(event, RSVPResponse.NOT_GOING)
        rsvp = RSVP.objects.get(event=event, user=self.member)
        self.assertEqual(rsvp.response, RSVPResponse.NOT_GOING)
        self.assertEqual(RSVP.objects.count(), 1)

    def test_rsvp_counts_shown(self):
        event = self.make_event()
        RSVP.objects.create(event=event, user=self.member, response=RSVPResponse.GOING)
        RSVP.objects.create(event=event, user=self.member2, response=RSVPResponse.NOT_GOING)
        self.client.force_login(self.member)
        response = self.client.get(reverse("events:detail", args=[event.pk]))
        self.assertContains(response, "1 going · 1 not going")

    def test_invalid_rsvp_response_ignored(self):
        event = self.make_event()
        self.client.force_login(self.member)
        self.rsvp(event, "maybe")
        self.assertFalse(RSVP.objects.exists())

    def test_no_rsvp_for_past_or_cancelled_events(self):
        past = self.make_event(days=-1)
        cancelled = self.make_event(days=5, cancelled=True)
        self.client.force_login(self.member)
        self.rsvp(past, RSVPResponse.GOING)
        self.rsvp(cancelled, RSVPResponse.GOING)
        self.assertFalse(RSVP.objects.exists())

    def test_applicants_cannot_rsvp(self):
        event = self.make_event()
        self.client.force_login(self.applicant)
        self.assertEqual(self.rsvp(event, RSVPResponse.GOING).status_code, 403)
        self.assertFalse(RSVP.objects.exists())

    # --- Attendance -----------------------------------------------------------
    def mark(self, event, users):
        return self.client.post(
            reverse("events:attendance", args=[event.pk]),
            {"attended": [str(u.pk) for u in users]},
        )

    def test_officer_records_attendance(self):
        event = self.make_event(days=-1)
        self.client.force_login(self.officer)
        self.mark(event, [self.member, self.member2])
        self.assertEqual(
            set(Attendance.objects.filter(event=event).values_list("user_id", flat=True)),
            {self.member.pk, self.member2.pk},
        )
        self.assertEqual(Attendance.objects.first().marked_by, self.officer)

    def test_saving_attendance_again_replaces_the_list(self):
        event = self.make_event(days=-1)
        self.client.force_login(self.officer)
        self.mark(event, [self.member, self.member2])
        self.mark(event, [self.member2])
        self.assertEqual(
            list(Attendance.objects.filter(event=event).values_list("user_id", flat=True)),
            [self.member2.pk],
        )

    def test_attendance_ignores_people_not_on_roster(self):
        event = self.make_event(days=-1)
        self.client.force_login(self.officer)
        self.mark(event, [self.applicant, self.member])
        self.assertEqual(
            list(Attendance.objects.filter(event=event).values_list("user_id", flat=True)),
            [self.member.pk],
        )

    def test_no_attendance_for_cancelled_event(self):
        event = self.make_event(days=-1, cancelled=True)
        self.client.force_login(self.officer)
        self.mark(event, [self.member])
        self.assertFalse(Attendance.objects.exists())

    def test_members_cannot_record_attendance(self):
        event = self.make_event(days=-1)
        self.client.force_login(self.member)
        self.assertEqual(self.mark(event, [self.member]).status_code, 403)
        self.assertFalse(Attendance.objects.exists())

    def test_officer_sees_roster_with_rsvp_in_attendance_form(self):
        event = self.make_event()
        RSVP.objects.create(event=event, user=self.member, response=RSVPResponse.GOING)
        self.client.force_login(self.officer)
        response = self.client.get(reverse("events:detail", args=[event.pk]))
        self.assertContains(response, "member2@example.com")
        self.assertContains(response, "Going")
        self.assertNotContains(response, "applicant@example.com")

    def test_members_do_not_see_attendance_form(self):
        event = self.make_event()
        self.client.force_login(self.member)
        response = self.client.get(reverse("events:detail", args=[event.pk]))
        self.assertNotContains(response, "Save attendance")

    # --- Dashboard (FR-08) ------------------------------------------------------
    def test_dashboard_shows_next_upcoming_events_to_members(self):
        self.make_event(days=2, title="Soonest")
        self.make_event(days=-2, title="Already happened")
        self.make_event(days=4, title="Called off", cancelled=True)
        self.client.force_login(self.member)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "Upcoming events")
        self.assertContains(response, "Soonest")
        self.assertNotContains(response, "Already happened")
        self.assertNotContains(response, "Called off")

    def test_public_dashboard_does_not_show_events(self):
        self.make_event(days=2, title="Members-only social")
        response = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(response, "Members-only social")
