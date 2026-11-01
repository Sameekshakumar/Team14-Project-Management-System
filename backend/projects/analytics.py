from datetime import timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import WorkspaceMembership
from accounts.permissions import get_user_workspace_role
from collaboration.models import ActivityEvent, TaskComment
from .models import Project, Task


def grouped_counts(queryset, date_field, start, end):
    return {
        row["day"].isoformat(): row["count"]
        for row in queryset.filter(**{f"{date_field}__date__range": (start, end)})
        .annotate(day=TruncDate(date_field)).values("day").annotate(count=Count("id"))
    }


class ProjectAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=project_id)
        if get_user_workspace_role(request.user, project.workspace) is None:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You are not a member of this workspace.")

        today = timezone.localdate()
        date_to_raw = request.query_params.get("date_to")
        date_from_raw = request.query_params.get("date_from")
        date_to = parse_date(date_to_raw) if date_to_raw else today
        date_from = parse_date(date_from_raw) if date_from_raw else date_to - timedelta(days=29)
        if not date_to:
            return Response({"date_to": "Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        if not date_from:
            return Response({"date_from": "Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        if date_from > date_to or (date_to - date_from).days > 365:
            return Response({"date_range": "Choose a valid date range of at most 366 days."}, status=400)

        tasks = Task.objects.filter(project=project)
        totals = tasks.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=Task.STATUS_DONE)),
            overdue=Count("id", filter=Q(due_date__lt=today) & ~Q(status=Task.STATUS_DONE)),
            unassigned_active=Count("id", filter=Q(assignee__isnull=True) & ~Q(status=Task.STATUS_DONE)),
        )
        by_status = {row["status"]: row["count"] for row in tasks.values("status").annotate(count=Count("id"))}
        by_priority = {row["priority"]: row["count"] for row in tasks.values("priority").annotate(count=Count("id"))}
        by_assignee = list(tasks.values("assignee_id", "assignee__email").annotate(count=Count("id")).order_by("-count", "assignee__email"))

        User = get_user_model()
        members = User.objects.filter(
            Q(workspace_memberships__workspace=project.workspace) | Q(pk=project.workspace.owner_id),
            is_active=True,
        ).distinct().annotate(
            active_tasks=Count("assigned_tasks", filter=Q(assigned_tasks__project=project) & ~Q(assigned_tasks__status=Task.STATUS_DONE), distinct=True),
            completed_tasks=Count("assigned_tasks", filter=Q(assigned_tasks__project=project, assigned_tasks__status=Task.STATUS_DONE), distinct=True),
            overdue_tasks=Count("assigned_tasks", filter=Q(assigned_tasks__project=project, assigned_tasks__due_date__lt=today) & ~Q(assigned_tasks__status=Task.STATUS_DONE), distinct=True),
        ).order_by("email")

        created = grouped_counts(tasks, "created_at", date_from, date_to)
        completed = grouped_counts(tasks, "completed_at", date_from, date_to)
        comments = grouped_counts(TaskComment.objects.filter(task__project=project), "created_at", date_from, date_to)
        activity = grouped_counts(ActivityEvent.objects.filter(project=project), "created_at", date_from, date_to)
        time_series = [{
            "date": (date_from + timedelta(days=index)).isoformat(),
            "created": created.get((date_from + timedelta(days=index)).isoformat(), 0),
            "completed": completed.get((date_from + timedelta(days=index)).isoformat(), 0),
            "comments": comments.get((date_from + timedelta(days=index)).isoformat(), 0),
            "activity": activity.get((date_from + timedelta(days=index)).isoformat(), 0),
        } for index in range((date_to - date_from).days + 1)]
        contributors = ActivityEvent.objects.filter(project=project, actor__isnull=False).values(
            "actor_id", "actor__email"
        ).annotate(contributions=Count("id")).order_by("-contributions", "actor__email")[:5]

        sprint_progress = None
        if apps.is_installed("sprints"):
            Sprint = apps.get_model("sprints", "Sprint")
            sprint_progress = list(Sprint.objects.filter(project=project).annotate(
                total_tasks=Count("items", distinct=True),
                completed_tasks=Count("items", filter=Q(items__status=Task.STATUS_DONE), distinct=True),
            ).values("id", "name", "status", "total_tasks", "completed_tasks"))

        return Response({
            "project_id": str(project.pk), "as_of": today.isoformat(),
            "date_from": date_from.isoformat(), "date_to": date_to.isoformat(),
            "total_tasks": totals["total"], "completed_tasks": totals["completed"],
            "completion_percent": round(totals["completed"] * 100 / totals["total"], 1) if totals["total"] else 0,
            "overdue_tasks": totals["overdue"], "unassigned_active_tasks": totals["unassigned_active"],
            "tasks_by_status": [{"status": key, "count": by_status.get(key, 0)} for key, _ in Task.STATUS_CHOICES],
            "tasks_by_priority": [{"priority": key, "count": by_priority.get(key, 0)} for key, _ in Task.PRIORITY_CHOICES],
            "tasks_by_assignee": [{"assignee_id": row["assignee_id"], "email": row["assignee__email"] or "Unassigned", "count": row["count"]} for row in by_assignee],
            "workload_distribution": [{"user_id": member.pk, "email": member.email, "active_tasks": member.active_tasks,
                "completed_tasks": member.completed_tasks, "overdue_tasks": member.overdue_tasks} for member in members],
            "time_series": time_series,
            "top_contributors": [{"user_id": row["actor_id"], "email": row["actor__email"], "contributions": row["contributions"]} for row in contributors],
            "sprint_progress": sprint_progress,
        })
