from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import get_user_workspace_role
from projects.models import Project, Task
from projects.permissions import require_member, require_write

from .models import ActivityEvent, Notification, TaskComment
from .serializers import ActivityEventSerializer, NotificationSerializer, TaskCommentSerializer
from .services import publish_project_event, record_comment_change


class TaskCommentsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_task(self, request, task_id):
        task = get_object_or_404(Task.objects.select_related("project__workspace"), pk=task_id)
        require_member(request.user, task.project.workspace)
        return task

    def get(self, request, task_id):
        task = self.get_task(request, task_id)
        comments = TaskComment.objects.filter(task=task).select_related("author").prefetch_related("mentions__mentioned_user")
        return Response(TaskCommentSerializer(comments, many=True, context={"task": task}).data)

    def post(self, request, task_id):
        task = self.get_task(request, task_id)
        require_write(request.user, task.project.workspace)
        serializer = TaskCommentSerializer(data=request.data, context={"task": task})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            comment = serializer.save(task=task, author=request.user)
            record_comment_change(comment=comment, event_type="comment_created")
        return Response(TaskCommentSerializer(comment, context={"task": task}).data, status=status.HTTP_201_CREATED)


class TaskCommentDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_comment(self, request, task_id, comment_id):
        task = get_object_or_404(Task.objects.select_related("project__workspace"), pk=task_id)
        require_member(request.user, task.project.workspace)
        return get_object_or_404(
            TaskComment.objects.select_related("author", "task__project__workspace").prefetch_related("mentions__mentioned_user"),
            pk=comment_id, task=task,
        )

    @staticmethod
    def can_manage(user, comment):
        role = get_user_workspace_role(user, comment.task.project.workspace)
        return comment.author_id == user.pk or role in {"Owner", "Admin"}

    def patch(self, request, task_id, comment_id):
        comment = self.get_comment(request, task_id, comment_id)
        if not self.can_manage(request.user, comment):
            return Response({"detail": "Only the author or a workspace Owner/Admin can edit this comment."}, status=403)
        serializer = TaskCommentSerializer(comment, data=request.data, partial=True, context={"task": comment.task})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            comment = serializer.save()
            record_comment_change(comment=comment, event_type="comment_updated")
        return Response(TaskCommentSerializer(comment, context={"task": comment.task}).data)

    def delete(self, request, task_id, comment_id):
        comment = self.get_comment(request, task_id, comment_id)
        if not self.can_manage(request.user, comment):
            return Response({"detail": "Only the author or a workspace Owner/Admin can delete this comment."}, status=403)
        task_id_value = str(comment.task_id)
        project_id = comment.task.project_id
        with transaction.atomic():
            comment.delete()
            publish_project_event(project_id, "comment_deleted", {
                "comment_id": comment_id, "task_id": task_id_value, "actor": request.user.pk,
            })
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectMemberSearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=project_id)
        require_member(request.user, project.workspace)
        query = request.query_params.get("q", "").strip()[:100]
        members = get_user_model().objects.filter(
            Q(workspace_memberships__workspace=project.workspace) | Q(pk=project.workspace.owner_id),
            is_active=True,
        )
        if query:
            members = members.filter(email__icontains=query)
        return Response([{"id": member.pk, "email": member.email}
                         for member in members.order_by("email").distinct()[:20]])


class ActivityPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ProjectActivityView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = ActivityPagination

    def get(self, request, project_id):
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=project_id)
        require_member(request.user, project.workspace)
        events = ActivityEvent.objects.filter(project=project).select_related("actor", "task")
        user_id = request.query_params.get("user")
        event_type = request.query_params.get("type")
        if user_id:
            if not user_id.isdigit():
                return Response({"user": "Use a numeric user ID."}, status=400)
            events = events.filter(actor_id=user_id)
        if event_type:
            events = events.filter(verb=event_type[:40])
        for param, lookup in (("date_from", "created_at__date__gte"), ("date_to", "created_at__date__lte")):
            value = request.query_params.get(param)
            if value:
                parsed = parse_date(value)
                if not parsed:
                    return Response({param: "Use YYYY-MM-DD."}, status=400)
                events = events.filter(**{lookup: parsed})
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(events, request, view=self)
        return paginator.get_paginated_response(ActivityEventSerializer(page, many=True).data)


class ProjectContextView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=project_id)
        require_member(request.user, project.workspace)
        return Response({
            "id": str(project.pk), "name": project.name, "description": project.description,
            "workspace_id": str(project.workspace_id),
        })


class NotificationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user).select_related(
            "activity", "project", "task"
        )
        unread = request.query_params.get("unread")
        if unread not in {None, "true", "false"}:
            return Response({"unread": "Use true or false."}, status=400)
        if unread == "true":
            notifications = notifications.filter(is_read=False)
        elif unread == "false":
            notifications = notifications.filter(is_read=True)
        paginator = ActivityPagination()
        page = paginator.paginate_queryset(notifications, request, view=self)
        return paginator.get_paginated_response(NotificationSerializer(page, many=True).data)


class NotificationReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, notification_id):
        notification = get_object_or_404(Notification, pk=notification_id, recipient=request.user)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at"])
        return Response(NotificationSerializer(notification).data)


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
        return Response({"count": count})
