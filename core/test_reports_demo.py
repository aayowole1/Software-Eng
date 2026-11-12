"""SCRUM-40: the reports/dashboard demo seed matches the numbers in the demo script."""

import io
import os
import time
import zipfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.testing import make_user
from committees.models import Committee
from core.management.commands.seed_reports_demo import (
    DEMO_EXPECTED, PEOPLE, expected_numbers_markdown,
)
from reports.views import _build_chart_data, _build_report, _default_dates


DOC_PATH = Path(settings.BASE_DIR) / "docs" / "reports-dashboard-demo.md"
README_PATH = Path(settings.BASE_DIR) / "README.md"
FAST_HASHER = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


def seed(*args):
    out = io.StringIO()
    call_command("seed_reports_demo", *args, stdout=out)
    return out.getvalue()


def demo_user(username):
    return get_user_model().objects.get(username=username)


def report_rows(data):
    return {
        "events": [(i["event"].title, i["rsvps_going"], i["attended"]) for i in data["per_event"]],
        "members": [
            (
                i["user"].get_full_name(), i["attended"], i["events_held"], i["attendance_pct"],
                i["tasks_assigned"], i["tasks_completed"], i["tasks_overdue"],
            )
            for i in data["per_member"]
        ],
        "committees": [
            (
                i["committee"].name, i["num_members"], i["attendance_pct"],
                i["tasks_total"], i["tasks_completed"], i["tasks_overdue"],
            )
            for i in data["per_committee"]
        ],
    }


@FAST_HASHER
class DemoNumbersTests(TestCase):
    """The seeded data produces exactly the numbers the demo script states."""

    @classmethod
    def setUpTestData(cls):
        cls.output = seed()

    def test_officer_dashboard_cards(self):
        expected = DEMO_EXPECTED["dashboard"]
        for username in ("demo_officer", "demo_admin"):
            with self.subTest(username=username):
                self.client.force_login(demo_user(username))
                response = self.client.get(reverse("core:home"))
                self.assertEqual(response.status_code, 200)
                ctx = response.context
                self.assertEqual(ctx["summary_active_members"], expected["active_members"])
                self.assertEqual(ctx["summary_upcoming_events"], expected["upcoming_events"])
                self.assertEqual(ctx["summary_open_tasks"], expected["open_tasks"])
                self.assertEqual(ctx["summary_pending_approvals"], expected["pending_approvals"])
                self.assertEqual(ctx["pending_applications"], expected["pending_applications"])
                self.assertEqual(ctx["pending_drafts"], expected["pending_drafts"])
                self.assertContains(response, "Active members")

    def test_member_dashboard_and_my_account(self):
        for username, expected in DEMO_EXPECTED["member_views"].items():
            with self.subTest(username=username):
                self.client.force_login(demo_user(username))
                ctx = self.client.get(reverse("core:home")).context
                self.assertNotIn("summary_active_members", ctx)
                self.assertEqual(ctx["my_task_counts"], {
                    "total": expected["tasks_assigned"],
                    "completed": expected["tasks_completed"],
                    "overdue": expected["tasks_overdue"],
                })
                self.assertEqual([t.title for t in ctx["my_tasks"]], expected["open_tasks"])
                summary = ctx["attendance_summary"]
                self.assertEqual(
                    (summary["attended"], summary["total"], summary["rate"]),
                    (expected["attended"], expected["events"], expected["rate"]),
                )

                profile = self.client.get(reverse("accounts:profile"))
                self.assertEqual(profile.status_code, 200)
                self.assertEqual(
                    (profile.context["attendance_count"], profile.context["attendance_total"],
                     profile.context["attendance_rate"]),
                    (expected["attended"], expected["events"], expected["rate"]),
                )
                self.assertContains(
                    profile,
                    f"Attended {expected['attended']} of {expected['events']} event",
                )

    def test_report_default_range(self):
        expected = DEMO_EXPECTED["report"]
        data = _build_report(*_default_dates())
        self.assertEqual(data["events_held"], expected["events_held"])
        rows = report_rows(data)
        self.assertEqual(rows["events"], expected["events"])
        self.assertEqual(rows["members"], expected["members"])
        self.assertEqual(rows["committees"], expected["committees"])

    def test_report_page_and_charts(self):
        self.client.force_login(demo_user("demo_officer"))
        response = self.client.get(reverse("reports:report"))
        self.assertEqual(response.status_code, 200)
        data = response.context["data"]
        start, end = _default_dates()
        self.assertEqual((data["start_date"], data["end_date"]), (start, end))
        self.assertEqual(report_rows(data), {k: DEMO_EXPECTED["report"][k] for k in ("events", "members", "committees")})
        self.assertContains(response, "Events held (non-cancelled): <strong>4</strong>", html=False)
        self.assertContains(response, "<td>76.9%</td>", html=True)
        self.assertNotContains(response, "Bowling Night")

        charts = _build_chart_data(data)
        self.assertEqual(
            [(c["name"], c["attendance_pct"]) for c in charts["per_committee"]],
            [(name, pct) for name, _, pct, *_ in DEMO_EXPECTED["report"]["committees"]],
        )

    def test_csv_downloads(self):
        self.client.force_login(demo_user("demo_officer"))
        start, end = _default_dates()
        response = self.client.get(reverse("reports:download"))
        self.assertEqual(response["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(sorted(archive.namelist()), sorted(
                f"orgflow-report-{name}-{start}_{end}.csv" for name in ("events", "members", "committees")
            ))
            members_csv = archive.read(f"orgflow-report-members-{start}_{end}.csv").decode("utf-8-sig")
        lines = members_csv.strip().splitlines()
        self.assertEqual(len(lines), 1 + len(DEMO_EXPECTED["report"]["members"]))
        drew = next(line for line in lines if line.startswith("Drew Kim"))
        self.assertIn(",suspended,", drew)

        single = self.client.get(reverse("reports:download"), {"report": "committees"})
        self.assertEqual(single["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(f"orgflow-report-committees-{start}_{end}.csv", single["Content-Disposition"])
        self.assertIn("Outreach,4,76.9,6,2,1", single.content.decode("utf-8-sig"))

    def test_demo_script_states_the_same_numbers(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        self.assertIn(expected_numbers_markdown(), doc)
        call_out = io.StringIO()
        call_command("seed_reports_demo", "--show-expected", stdout=call_out)
        self.assertEqual(call_out.getvalue(), expected_numbers_markdown())
        for username in PEOPLE:
            self.assertIn(username, doc)
        self.assertIn("docs/reports-dashboard-demo.md", README_PATH.read_text(encoding="utf-8"))


@FAST_HASHER
class DemoSafetyTests(TestCase):
    def test_refuses_when_users_exist(self):
        make_user("someone@example.com")
        with self.assertRaisesMessage(CommandError, "already has 1 user account"):
            seed()
        self.assertFalse(get_user_model().objects.filter(username__startswith="demo_").exists())
        self.assertFalse(Committee.objects.exists())

    def test_force_adds_demo_alongside_existing_users(self):
        make_user("someone@example.com")
        seed("--force")
        self.assertEqual(
            get_user_model().objects.filter(username__in=list(PEOPLE)).count(), len(PEOPLE),
        )
        self.assertTrue(get_user_model().objects.filter(username="someone@example.com").exists())

    def test_never_seeds_twice(self):
        seed()
        with self.assertRaisesMessage(CommandError, "already been added"):
            seed("--force")
        self.assertEqual(Committee.objects.count(), 2)

    def test_refuses_production_settings(self):
        with mock.patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "orgflow_project.settings_production"}):
            with self.assertRaisesMessage(CommandError, "development settings"):
                seed()
        self.assertFalse(get_user_model().objects.exists())

    def test_show_expected_changes_nothing(self):
        seed("--show-expected")
        self.assertFalse(get_user_model().objects.exists())

    def test_prints_working_logins_once_and_saves_no_password_file(self):
        started = time.time() - 1
        output = seed()
        passwords = {}
        for line in output.splitlines():
            parts = line.split()
            if parts and parts[0] in PEOPLE:
                passwords[parts[0]] = parts[1]
        self.assertEqual(set(passwords), set(PEOPLE))
        self.assertEqual(len(set(passwords.values())), len(PEOPLE))
        for username, password in passwords.items():
            self.assertEqual(output.count(password), 1)
            user = demo_user(username)
            self.assertNotEqual(user.password, password)
            self.assertTrue(user.check_password(password))
            self.assertTrue(user.email.endswith("@example.com"))
        self.assertEqual(authenticate(username="demo_officer", password=passwords["demo_officer"]), demo_user("demo_officer"))
        self.assertIsNone(authenticate(username="demo_suspended", password=passwords["demo_suspended"]))
        self.assertIsNone(authenticate(username="demo_applicant", password=passwords["demo_applicant"]))

        # No file in the project was written during the run, so nothing holds the passwords.
        written = []
        for root, dirs, files in os.walk(settings.BASE_DIR):
            dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules", "media"}]
            for name in files:
                path = os.path.join(root, name)
                try:
                    if os.path.getmtime(path) >= started:
                        written.append(path)
                except OSError:
                    continue
        for path in written:
            with open(path, "rb") as handle:
                content = handle.read()
            for password in passwords.values():
                self.assertNotIn(password.encode(), content, path)
