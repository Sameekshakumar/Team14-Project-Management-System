from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import get_user_workspace_role
from projects.models import Project, Task
from projects.permissions import require_member, require_write

from .models import TaskComment
from .serializers import TaskCommentSerializer
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
