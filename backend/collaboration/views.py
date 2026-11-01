from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.db.models.functions import TruncDate
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.models import Project, Task
from projects.permissions import require_member, require_write

from .models import ActivityEvent, Mention, Notification, TaskComment
from .serializers import ActivityEventSerializer, NotificationSerializer, TaskCommentSerializer
from .services import record_comment, record_comment_update


def _limit(request):
    try:
        return min(max(int(request.query_params.get("limit", "50")), 1), 100)
    except ValueError:
        return 50


class TaskCommentListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_task(self, request, task_id):
        task = get_object_or_404(Task.objects.select_related("project__workspace"), pk=task_id)
        require_member(request.user, task.project.workspace)
        return task

    def get(self, request, task_id):
        task = self.get_task(request, task_id)
        comments = TaskComment.objects.filter(task=task).select_related("author").prefetch_related("mentioned_users")
        return Response(TaskCommentSerializer(comments, many=True).data)

    def post(self, request, task_id):
        task = self.get_task(request, task_id)
        require_write(request.user, task.project.workspace)
        serializer = TaskCommentSerializer(data=request.data, context={"task": task})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            comment = serializer.save(task=task, author=request.user)
            comment_data = TaskCommentSerializer(comment).data
            record_comment(comment=comment, actor=request.user, comment_data=comment_data)
        return Response(comment_data, status=status.HTTP_201_CREATED)


class TaskCommentDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_comment(self, request, task_id, comment_id):
        task = get_object_or_404(Task.objects.select_related("project__workspace"), pk=task_id)
        require_member(request.user, task.project.workspace)
        return get_object_or_404(
            TaskComment.objects.select_related("author").prefetch_related("mentioned_users"),
            pk=comment_id,
            task=task,
        )

    def can_manage(self, user, comment):
        from accounts.permissions import get_user_workspace_role
        role = get_user_workspace_role(user, comment.task.project.workspace)
        return comment.author_id == user.pk or role in {"Owner", "Admin"}

    def patch(self, request, task_id, comment_id):
        comment = self.get_comment(request, task_id, comment_id)
        if not self.can_manage(request.user, comment):
            return Response({"detail": "Only the comment author or a workspace Owner/Admin can edit it."}, status=403)
        previous_mentions = set(comment.mentioned_users.values_list("id", flat=True))
        serializer = TaskCommentSerializer(comment, data=request.data, partial=True, context={"task": comment.task})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            comment = serializer.save()
            data = TaskCommentSerializer(comment).data
            record_comment_update(comment=comment, actor=request.user, comment_data=data, previous_mentions=previous_mentions)
        return Response(data)

    def delete(self, request, task_id, comment_id):
        comment = self.get_comment(request, task_id, comment_id)
        if not self.can_manage(request.user, comment):
            return Response({"detail": "Only the comment author or a workspace Owner/Admin can delete it."}, status=403)
        project = comment.task.project
        task_id_value = str(comment.task_id)
        comment_id_value = comment.pk
        with transaction.atomic():
            event = ActivityEvent.objects.create(
                project=project,
                task=comment.task,
                actor=request.user,
                event_type="comment_deleted",
                payload={"comment_id": comment_id_value, "task_id": task_id_value, "actor_id": request.user.pk},
            )
            from .services import activity_payload, publish_project_event
            comment.delete()
            publish_project_event(project.id, "comment_deleted", {"comment_id": comment_id_value, "task_id": task_id_value})
            publish_project_event(project.id, "activity_created", activity_payload(event))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectMemberSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=project_id)
        require_member(request.user, project.workspace)
        query = request.query_params.get("q", "").strip()[:100]
        user_model = get_user_model()
        members = user_model.objects.filter(
            Q(workspace_memberships__workspace=project.workspace) | Q(pk=project.workspace.owner_id),
            is_active=True,
        )
        if query:
            members = members.filter(email__icontains=query)
        return Response([{"id": member.pk, "email": member.email} for member in members.order_by("email")[:20]])


class ProjectContextView(APIView):
    """Return the workspace context needed to open a notification's project."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=project_id)
        require_member(request.user, project.workspace)
        return Response({
            "id": str(project.id), "name": project.name,
            "description": project.description,
            "workspace_id": str(project.workspace_id),
        })


class ProjectActivityListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=project_id)
        require_member(request.user, project.workspace)
        events = ActivityEvent.objects.filter(project=project).select_related("actor", "task")
        actor = request.query_params.get("user")
        event_type = request.query_params.get("type")
        date_from = parse_date(request.query_params.get("date_from", ""))
        date_to = parse_date(request.query_params.get("date_to", ""))
        if request.query_params.get("date_from") and not date_from:
            return Response({"date_from": "Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        if request.query_params.get("date_to") and not date_to:
            return Response({"date_to": "Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        if actor:
            events = events.filter(actor_id=actor)
        if event_type:
            events = events.filter(event_type=event_type)
        if date_from:
            events = events.filter(created_at__date__gte=date_from)
        if date_to:
            events = events.filter(created_at__date__lte=date_to)
        pager = PageNumberPagination()
        pager.page_size = 25
        pager.page_size_query_param = "limit"
        pager.max_page_size = 100
        page = pager.paginate_queryset(events, request, view=self)
        return pager.get_paginated_response(ActivityEventSerializer(page, many=True).data)


class ProjectAnalyticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project.objects.select_related("workspace", "workspace__owner"), pk=project_id)
        require_member(request.user, project.workspace)
        today = timezone.localdate()
        raw_from, raw_to = request.query_params.get("from", ""), request.query_params.get("to", "")
        date_from = parse_date(raw_from) if raw_from else today - timezone.timedelta(days=29)
        date_to = parse_date(raw_to) if raw_to else today
        if date_from is None or date_to is None:
            return Response({"date_range": "Use YYYY-MM-DD for from and to."}, status=400)
        if date_from > date_to:
            return Response({"date_range": "The from date must be on or before the to date."}, status=400)
        if (date_to - date_from).days > 365:
            return Response({"date_range": "Date ranges may not exceed 366 days."}, status=400)
        tasks = Task.objects.filter(project=project)
        metrics = tasks.aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=Task.STATUS_DONE)),
            overdue=Count("id", filter=Q(due_date__lt=today) & ~Q(status=Task.STATUS_DONE)),
            unassigned=Count("id", filter=Q(assignee__isnull=True) & ~Q(status=Task.STATUS_DONE)),
        )
        user_model = get_user_model()
        members = user_model.objects.filter(
            Q(workspace_memberships__workspace=project.workspace) | Q(pk=project.workspace.owner_id)
        ).distinct().annotate(
            active_tasks=Count(
                "assigned_tasks",
                filter=Q(assigned_tasks__project=project) & ~Q(assigned_tasks__status=Task.STATUS_DONE),
                distinct=True,
            ),
            completed_tasks=Count(
                "assigned_tasks",
                filter=Q(assigned_tasks__project=project, assigned_tasks__status=Task.STATUS_DONE),
                distinct=True,
            ),
            overdue_tasks=Count(
                "assigned_tasks",
                filter=Q(assigned_tasks__project=project, assigned_tasks__due_date__lt=today)
                & ~Q(assigned_tasks__status=Task.STATUS_DONE),
                distinct=True,
            ),
        ).order_by("email")

        status_counts = {
            row["status"]: row["count"]
            for row in tasks.values("status").annotate(count=Count("id"))
        }
        priority_counts = {
            row["priority"]: row["count"]
            for row in tasks.values("priority").annotate(count=Count("id"))
        }
        assignee_counts = list(tasks.values("assignee_id", "assignee__email").annotate(
            count=Count("id")
        ).order_by("-count", "assignee__email"))

        created_by_day = {
            row["day"].isoformat(): row["count"]
            for row in tasks.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
            .annotate(day=TruncDate("created_at")).values("day").annotate(count=Count("id"))
        }
        completed_by_day = {
            row["day"].isoformat(): row["count"]
            for row in tasks.filter(
                completed_at__date__gte=date_from, completed_at__date__lte=date_to
            ).annotate(day=TruncDate("completed_at")).values("day").annotate(count=Count("id"))
        }
        comment_by_day = {
            row["day"].isoformat(): row["count"]
            for row in TaskComment.objects.filter(
                task__project=project, created_at__date__gte=date_from, created_at__date__lte=date_to
            ).annotate(day=TruncDate("created_at")).values("day").annotate(count=Count("id"))
        }
        activity_by_day = {
            row["day"].isoformat(): row["count"]
            for row in ActivityEvent.objects.filter(
                project=project, created_at__date__gte=date_from, created_at__date__lte=date_to
            ).annotate(day=TruncDate("created_at")).values("day").annotate(count=Count("id"))
        }
        days = [date_from + timezone.timedelta(days=index) for index in range((date_to - date_from).days + 1)]
        time_series = [{
            "date": day.isoformat(),
            "created": created_by_day.get(day.isoformat(), 0),
            "completed": completed_by_day.get(day.isoformat(), 0),
            "comments": comment_by_day.get(day.isoformat(), 0),
            "activity": activity_by_day.get(day.isoformat(), 0),
        } for day in days]
        top_contributors = list(ActivityEvent.objects.filter(
            project=project, actor__isnull=False
        ).values("actor_id", "actor__email").annotate(contributions=Count("id"))
         .order_by("-contributions", "actor__email")[:5])
        return Response({
            "project_id": str(project.id),
            "as_of": today.isoformat(),
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "total_tasks": metrics["total"],
            "completed_tasks": metrics["completed"],
            "completion_percent": round(metrics["completed"] * 100 / metrics["total"], 1) if metrics["total"] else 0,
            "overdue_tasks": metrics["overdue"],
            "unassigned_active_tasks": metrics["unassigned"],
            "tasks_by_status": [{"status": key, "count": status_counts.get(key, 0)} for key, _ in Task.STATUS_CHOICES],
            "tasks_by_priority": [{"priority": key, "count": priority_counts.get(key, 0)} for key, _ in Task.PRIORITY_CHOICES],
            "tasks_by_assignee": [{
                "assignee_id": row["assignee_id"],
                "email": row["assignee__email"] or "Unassigned",
                "count": row["count"],
            } for row in assignee_counts],
            "time_series": time_series,
            "top_contributors": [{
                "user_id": row["actor_id"], "email": row["actor__email"], "contributions": row["contributions"]
            } for row in top_contributors],
            "sprint_progress": None,
            "workload_distribution": [{
                "user_id": member.pk,
                "email": member.email,
                "active_tasks": member.active_tasks,
                "completed_tasks": member.completed_tasks,
                "overdue_tasks": member.overdue_tasks,
            } for member in members],
        })


class NotificationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user).select_related("project", "task")
        if request.query_params.get("unread") in {"1", "true", "yes"}:
            notifications = notifications.filter(is_read=False)
        return Response(NotificationSerializer(notifications[:_limit(request)], many=True).data)


class NotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _read(self, request, notification_id):
        notification = get_object_or_404(Notification, pk=notification_id, recipient=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
        return Response(NotificationSerializer(notification).data)

    def post(self, request, notification_id):
        return self._read(request, notification_id)

    def patch(self, request, notification_id):
        return self._read(request, notification_id)


class NotificationReadAllView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(recipient=request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return Response({"marked_read": True})


class NotificationUnreadCountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return Response({"unread_count": count})
