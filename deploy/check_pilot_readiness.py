"""Synthetic local HTTP workflow checks; never a human usability result."""
import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def csrf(page):
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text)
    if not match:
        raise RuntimeError("The form did not provide a CSRF token.")
    return match.group(1)


def login(base, account):
    session = requests.Session()
    session.trust_env = False
    page = session.get(base + "/accounts/login/", timeout=10)
    response = session.post(base + "/accounts/login/", data={
        "username": account["username"], "password": account["password"],
        "csrfmiddlewaretoken": csrf(page),
    }, headers={"Referer": base + "/accounts/login/"}, timeout=15)
    if response.status_code != 200 or "Sign out" not in response.text:
        raise RuntimeError("Synthetic review-account login failed.")
    return session


def submit(session, base, path, page, data):
    return session.post(base + path, data={**data, "csrfmiddlewaretoken": csrf(page)},
                        headers={"Referer": page.url}, timeout=15)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orgflow_project.settings")
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.core.files.base import ContentFile
    from django.utils import timezone
    from accounts.models import Role
    from announcements.models import Resource
    from announcements.permissions import effective_role
    from events.models import Event, RSVP
    from tasks.models import Task

    if settings.DATABASES["default"]["NAME"] != "orgflow_local_review":
        raise RuntimeError("This fixture-writing check is restricted to orgflow_local_review.")
    accounts = json.loads(args.accounts_file.read_text(encoding="utf-8"))
    User = get_user_model()
    member = User.objects.get(username=accounts["member"]["username"])
    officer = User.objects.get(username=accounts["officer"]["username"])
    if effective_role(member) != Role.MEMBER or effective_role(officer) not in {Role.OFFICER, Role.ADMIN}:
        raise RuntimeError("Use active synthetic Member/Officer review accounts.")

    run = uuid4().hex[:8]
    title = f"SCRUM83 readiness {run}"
    event = Event.objects.create(title=title + " meeting", location="Local demo room",
        description="Synthetic readiness fixture; not a human pilot result.",
        starts_at=timezone.now() + timedelta(days=7), created_by=officer)
    task = Task.objects.create(title=title + " task", assignee=member, created_by=officer)
    resource = Resource(title=title + " handbook", created_by=officer)
    resource.file.save("pilot-handbook.txt", ContentFile(b"Synthetic pilot-readiness handbook.\n"))
    base = "http://127.0.0.1:8000"
    checks = {}
    with login(base, accounts["member"]) as member_session, login(base, accounts["officer"]) as officer_session:
        page = member_session.get(base + "/dashboard/", timeout=10)
        checks["member_login_and_dashboard"] = page.status_code == 200 and "Events" in page.text

        listing = member_session.get(base + "/events/", timeout=10)
        detail = member_session.get(base + f"/events/{event.pk}/", timeout=10)
        saved = submit(member_session, base, f"/events/{event.pk}/rsvp/", detail, {"response": "going"})
        checks["find_event_and_save_rsvp"] = (event.title in listing.text and saved.status_code == 200
            and "RSVP saved: Going" in saved.text and RSVP.objects.filter(event=event, user=member, response="going").exists())

        listing = member_session.get(base + "/resources/", params={"q": resource.title}, timeout=10)
        download = member_session.get(base + f"/resources/{resource.pk}/open/", timeout=10)
        checks["search_resource_and_download"] = (resource.title in listing.text and download.status_code == 200
            and download.content == b"Synthetic pilot-readiness handbook.\n"
            and download.headers.get("Cache-Control") == "private, no-store")

        detail = member_session.get(base + f"/tasks/{task.pk}/", timeout=10)
        version = re.search(r'name="version"[^>]*value="(\d+)"', detail.text)
        if not version:
            raise RuntimeError("Task progress form did not provide its version.")
        saved = submit(member_session, base, f"/tasks/{task.pk}/status/", detail,
                       {"status": "in_progress", "version": version.group(1)})
        task.refresh_from_db()
        checks["member_updates_assigned_task"] = saved.status_code == 200 and task.status == "in_progress"

        form = officer_session.get(base + "/announcements/create/", timeout=10)
        saved = submit(officer_session, base, "/announcements/create/", form, {
            "title": title + " notice", "content": "Synthetic readiness announcement.",
            "status": "published", "target_reach": 5,
        })
        feed = member_session.get(base + "/announcements/", params={"q": title + " notice"}, timeout=10)
        checks["officer_publishes_member_reads_notice"] = saved.status_code == 200 and title + " notice" in feed.text

    result = {
        "mode": "automated_http_readiness", "human_participants": 0,
        "counts_towards_scrum83": False, "human_acceptance": "NOT EVALUATED",
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "checks": checks, "all_checks_passed": all(checks.values()),
        "limitations": ["No human timing or unaided completion measured", "No visual/browser/accessibility inspection"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
