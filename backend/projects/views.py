from django.shortcuts import get_object_or_404
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from accounts.models import Workspace

from .models import Project, Task, TaskDependency
from .permissions import require_member, require_write
from .serializers import ProjectSerializer, TaskDependencySerializer, TaskSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    """
    FR-TASK-01: projects live inside a workspace, so every action is scoped to
    the workspace in the URL and gated on the caller's role in that workspace.
    """
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_url_kwarg = "project_id"

    def get_workspace(self):
        return get_object_or_404(Workspace, id=self.kwargs["workspace_id"])

    def get_queryset(self):
        workspace = self.get_workspace()
        require_member(self.request.user, workspace)
        return Project.objects.filter(workspace=workspace).select_related(
            "workspace", "created_by"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if "workspace_id" in self.kwargs:
            context["workspace"] = self.get_workspace()
        return context

    def perform_create(self, serializer):
        workspace = self.get_workspace()
        require_write(self.request.user, workspace)
        serializer.save(workspace=workspace, created_by=self.request.user)

    def perform_update(self, serializer):
        require_write(self.request.user, self.get_workspace())
        serializer.save()

    def perform_destroy(self, instance):
        workspace = self.get_workspace()
        role = require_member(self.request.user, workspace)
        if role not in ["Owner", "Admin"]:
            raise PermissionDenied(
                "Only workspace Owners and Admins can delete a project."
            )
        instance.delete()


class TaskListCreateViewSet(viewsets.ModelViewSet):
    """
    FR-TASK-02: list and create tasks inside a project. Nested under the
    project so the project is never taken from client-supplied data.
    """
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_project(self):
        project = get_object_or_404(Project, id=self.kwargs["project_id"])
        require_member(self.request.user, project.workspace)
        return project

    def get_queryset(self):
        return Task.objects.filter(project=self.get_project()).select_related(
            "assignee", "created_by", "project"
        ).prefetch_related("subtasks", "dependencies__depends_on")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["project"] = self.get_project()
        return context

    def perform_create(self, serializer):
        project = self.get_project()
        require_write(self.request.user, project.workspace)
        serializer.save(project=project, created_by=self.request.user)


class TaskDetailViewSet(viewsets.ModelViewSet):
    """Retrieve, update or delete a single task, addressed by its own id."""

    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_url_kwarg = "task_id"
    http_method_names = ["get", "patch", "put", "delete", "head", "options"]

    def get_queryset(self):
        return Task.objects.select_related(
            "assignee", "created_by", "project", "project__workspace"
        ).prefetch_related("subtasks", "dependencies__depends_on")

    def get_object(self):
        task = super().get_object()
        require_member(self.request.user, task.project.workspace)
        return task

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if self.lookup_url_kwarg in self.kwargs:
            context["project"] = self.get_object().project
        return context

    def perform_update(self, serializer):
        require_write(self.request.user, serializer.instance.project.workspace)
        serializer.save()

    def perform_destroy(self, instance):
        require_write(self.request.user, instance.project.workspace)
        instance.delete()


class TaskDependencyViewSet(viewsets.ModelViewSet):
    """FR-TASK-04: manage dependencies declared on a single task."""

    serializer_class = TaskDependencySerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_url_kwarg = "dependency_id"
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_task(self):
        task = get_object_or_404(
            Task.objects.select_related("project__workspace"),
            id=self.kwargs["task_id"],
        )
        require_member(self.request.user, task.project.workspace)
        return task

    def get_queryset(self):
        return TaskDependency.objects.filter(task=self.get_task()).select_related(
            "depends_on"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["task"] = self.get_task()
        return context

    def perform_create(self, serializer):
        task = self.get_task()
        require_write(self.request.user, task.project.workspace)
        serializer.save(task=task)

    def perform_destroy(self, instance):
        require_write(self.request.user, instance.task.project.workspace)
        instance.delete()
