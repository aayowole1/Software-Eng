"""Seed only a new orgflow_perf_* database with representative synthetic data."""

import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts-output", type=Path, default=ROOT / ".validation/performance-accounts.json")
    parser.add_argument("--dataset-output", type=Path, default=ROOT / ".validation/performance-dataset.json")
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orgflow_project.settings")
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.hashers import make_password
    from django.utils import timezone
    from accounts.models import Profile, Role
    from announcements.models import Announcement, Resource
    from committees.models import Committee, CommitteeMember
    from events.models import Attendance, Event, RSVP
    from meetings.models import MeetingDraft
    from tasks.models import Task

    if not settings.DATABASES["default"]["NAME"].startswith("orgflow_perf_"):
        raise RuntimeError("Use a dedicated database whose name begins orgflow_perf_.")
    User = get_user_model()
    models = (User, Profile, Committee, CommitteeMember, Event, RSVP, Attendance, Task, Announcement, Resource, MeetingDraft)
    if any(model.objects.exists() for model in models):
        raise RuntimeError("Benchmark seeding requires an empty synthetic application database.")
    password = secrets.token_urlsafe(24)
    encoded = make_password(password)
    users = User.objects.bulk_create([
        User(username=f"perf-{i:03}", email=f"perf-{i:03}@example.com", password=encoded, is_active=True)
        for i in range(500)
    ])
    Profile.objects.bulk_create([
        Profile(user=user, role=Role.OFFICER if i < 5 else Role.MEMBER) for i, user in enumerate(users)
    ])
    committees = Committee.objects.bulk_create([
        Committee(name=f"Committee {i}", created_by=users[0]) for i in range(10)
    ])
    CommitteeMember.objects.bulk_create([
        CommitteeMember(committee=committees[i % 10], user=user) for i, user in enumerate(users)
    ])
    events = Event.objects.bulk_create([
        Event(title=f"Organization event {i}", location="Campus demo room",
              starts_at=timezone.now() + timedelta(days=i - 50), created_by=users[0]) for i in range(100)
    ])
    Task.objects.bulk_create([
        Task(title=f"Committee task {i}", description="Synthetic representative task",
             committee=committees[i % 10], assignee=users[i % 500], created_by=users[0],
             due_date=timezone.localdate() + timedelta(days=i % 30 - 15),
             status=["todo", "in_progress", "done"][i % 3], priority=["low", "medium", "high"][i % 3])
        for i in range(1000)
    ])
    RSVP.objects.bulk_create([
        RSVP(event=event, user=users[(i * 25 + j) % 500], response="going")
        for i, event in enumerate(events) for j in range(25)
    ])
    Attendance.objects.bulk_create([
        Attendance(event=event, user=users[(i * 25 + j) % 500], marked_by=users[0])
        for i, event in enumerate(events[:50]) for j in range(25)
    ])
    Announcement.objects.bulk_create([
        Announcement(title=f"Organization announcement {i}", content="Synthetic page benchmark announcement.",
                     author=users[0], status="published" if i < 40 else "draft", is_pinned=i == 0)
        for i in range(50)
    ])
    Resource.objects.bulk_create([
        Resource(title=f"Organization resource {i}", description="Synthetic page benchmark resource.",
                 category="Guides", url="https://example.org/", created_by=users[0]) for i in range(50)
    ])
    MeetingDraft.objects.bulk_create([
        MeetingDraft(title=f"Pending meeting {i}", notes="Synthetic notes", created_by=users[0]) for i in range(20)
    ])
    paths = ["/dashboard/", "/membership/roster/", "/committees/", "/tasks/", "/events/",
             "/announcements/", "/resources/", "/accounts/me/"]
    accounts = [
        {"username": user.username, "password": password,
         "paths": paths + (["/membership/applications/", "/meetings/"] if i < 5 else [])}
        for i, user in enumerate(users[:25])
    ]
    counts = {
        "active_members": Profile.objects.count(), "events": Event.objects.count(), "tasks": Task.objects.count(),
        "committees": Committee.objects.count(), "rsvps": RSVP.objects.count(),
        "attendance_records": Attendance.objects.count(), "announcements": Announcement.objects.count(),
        "resources": Resource.objects.count(), "meeting_drafts": MeetingDraft.objects.count(),
    }
    args.accounts_output.parent.mkdir(parents=True, exist_ok=True)
    args.accounts_output.write_text(json.dumps(accounts), encoding="utf-8")
    args.dataset_output.parent.mkdir(parents=True, exist_ok=True)
    args.dataset_output.write_text(json.dumps(counts, indent=2), encoding="utf-8")
    print(json.dumps(counts), flush=True)


if __name__ == "__main__":
    main()
