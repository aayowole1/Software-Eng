"""FR-4.4: each committee page shows a task board with workloads and deadlines."""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from accounts.testing import make_user
from committees.models import Committee, CommitteeMember
from tasks.models import Task, TaskPriority, TaskStatus


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CommitteeTaskBoardTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.officer = make_user("board-officer@example.com", Role.OFFICER)
        self.mia = make_user("board-mia@example.com", Role.MEMBER)
        self.mia.first_name, self.mia.last_name = "Mia", "Okafor"
        self.mia.save()
        self.leo = make_user("board-leo@example.com", Role.MEMBER)
        self.outsider = make_user("board-outsider@example.com", Role.MEMBER)
        self.committee = Committee.objects.create(name="Events", created_by=self.officer)
        other = Committee.objects.create(name="Finance", created_by=self.officer)
        for user in (self.mia, self.leo):
            CommitteeMember.objects.create(committee=self.committee, user=user)
        CommitteeMember.objects.create(committee=other, user=self.outsider)
        self.url = reverse("committees:detail", args=[self.committee.pk])

        def task(title, assignee=None, due=None, priority=TaskPriority.MEDIUM, status=TaskStatus.TODO, committee=None):
            return Task.objects.create(
                title=title, committee=committee or self.committee, assignee=assignee, created_by=self.officer,
                due_date=self.today + timedelta(days=due) if due is not None else None, priority=priority, status=status,
            )

        task("Book the venue", self.mia, due=-2, priority=TaskPriority.HIGH)        # overdue
        task("Design the flyer", self.mia, due=5)
        task("Order snacks", self.leo, due=1, priority=TaskPriority.URGENT)
        task("Same-day low", self.leo, due=1, priority=TaskPriority.LOW)
        task("Collect sign-ups", None, due=-1)                                      # unassigned, overdue
        task("Someday idea", None)                                                  # no due date
        task("Already done", self.mia, due=-5, status=TaskStatus.DONE)
        task("Finance only", self.outsider, due=2, committee=other)

    def board(self, user):
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response

    def test_open_tasks_are_sorted_by_deadline_then_priority(self):
        board = self.board(self.mia).context["task_board"]
        self.assertEqual(
            [task.title for task in board["open_tasks"]],
            ["Book the venue", "Collect sign-ups", "Order snacks", "Same-day low", "Design the flyer", "Someday idea"],
        )
        self.assertEqual(board["open_count"], 6)

    def test_workload_counts_open_and_overdue_tasks_per_person(self):
        board = self.board(self.officer).context["task_board"]
        rows = {row["user"].email: (row["open"], row["overdue"], row["next_due"]) for row in board["workload"]}
        self.assertEqual(rows, {
            "board-mia@example.com": (2, 1, self.today - timedelta(days=2)),
            "board-leo@example.com": (2, 0, self.today + timedelta(days=1)),
        })
        self.assertEqual(board["workload"][0]["user"], self.mia)  # people with overdue work first
        self.assertEqual(board["unassigned"], {"open": 2, "overdue": 1})

    def test_page_shows_board_with_names_links_and_overdue_flags(self):
        response = self.board(self.mia)
        self.assertContains(response, "Task board")
        self.assertContains(response, "Mia Okafor")
        self.assertContains(response, "Unassigned")
        self.assertContains(response, "Overdue")
        self.assertContains(response, "Urgent")
        task = Task.objects.get(title="Order snacks")
        self.assertContains(response, reverse("tasks:detail", args=[task.pk]))
        self.assertNotContains(response, "Already done")
        self.assertNotContains(response, "Finance only")

    def test_people_outside_the_committee_do_not_see_the_board(self):
        response = self.board(self.outsider)
        self.assertNotContains(response, "Task board")
        self.assertIsNone(response.context["task_board"])

    def test_empty_board_explains_there_is_nothing_open(self):
        Task.objects.filter(committee=self.committee).update(status=TaskStatus.DONE)
        response = self.board(self.mia)
        self.assertContains(response, "No open tasks.")

    def test_board_is_limited_with_a_link_to_the_rest(self):
        for number in range(20):
            Task.objects.create(title=f"Extra {number}", committee=self.committee, created_by=self.officer)
        response = self.board(self.officer)
        board = response.context["task_board"]
        self.assertEqual(len(board["open_tasks"]), 20)
        self.assertEqual(board["more_count"], 6)
        self.assertContains(response, "See 6 more open tasks")
