from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Workspace, WorkspaceMembership
from collaboration.models import ActivityEvent, TaskComment
from .models import Project, Task

User = get_user_model()


@override_settings(ROOT_URLCONF="config.urls")
class ProjectAnalyticsTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@analytics.test", password="StrongPass!234")
        self.member = User.objects.create_user(email="member@analytics.test", password="StrongPass!234")
        self.outsider = User.objects.create_user(email="outsider@analytics.test", password="StrongPass!234")
        self.workspace = Workspace.objects.create(name="Analytics", owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.member)
        self.project = Project.objects.create(workspace=self.workspace, name="Metrics")
        self.client.force_authenticate(self.owner)

    def url(self):
        return reverse("project-analytics", args=[self.project.pk])

    def test_aggregates_counts_distribution_and_activity_timeseries(self):
        today = timezone.localdate()
        completed = Task.objects.create(
            project=self.project, title="Completed", status=Task.STATUS_DONE,
            priority="High", assignee=self.member, completed_at=timezone.now(),
        )
        Task.objects.create(
            project=self.project, title="Late", status=Task.STATUS_IN_PROGRESS,
            priority="Critical", assignee=self.member, due_date=today - timedelta(days=1),
        )
        TaskComment.objects.create(task=completed, author=self.member, body="done")
        ActivityEvent.objects.create(
            project=self.project, actor=self.member, task=completed, verb="task_created",
            target_type="task", target_id=str(completed.pk),
        )

        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_tasks"], 2)
        self.assertEqual(response.data["completed_tasks"], 1)
        self.assertEqual(response.data["overdue_tasks"], 1)
        self.assertEqual(response.data["completion_percent"], 50.0)
        self.assertEqual({row["priority"]: row["count"] for row in response.data["tasks_by_priority"]}["High"], 1)
        self.assertEqual(response.data["time_series"][-1]["comments"], 1)
        self.assertEqual(response.data["time_series"][-1]["activity"], 1)
        self.assertEqual(response.data["top_contributors"][0]["email"], self.member.email)
        member_load = next(row for row in response.data["workload_distribution"] if row["email"] == self.member.email)
        self.assertEqual(member_load["active_tasks"], 1)

    def test_non_member_cannot_read_analytics_and_date_range_is_validated(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.client.force_authenticate(self.owner)
        response = self.client.get(self.url(), {"date_from": "2025-01-02", "date_to": "2025-01-01"})
        self.assertEqual(response.status_code, 400)

