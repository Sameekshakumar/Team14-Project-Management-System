from django.shortcuts import get_object_or_404
from rest_framework import generics
from projects.models import Project, Task
from projects.permissions import require_member, require_write
from projects.serializers import TaskSerializer
from .exceptions import SprintErrorsMixin


class BacklogListCreateView(SprintErrorsMixin, generics.ListCreateAPIView):
    serializer_class = TaskSerializer

    def get_project(self):
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=self.kwargs["project_id"])
        require_member(self.request.user, project.workspace)
        if self.request.method == "POST":
            require_write(self.request.user, project.workspace)
        return project

    def get_queryset(self):
        return Task.objects.filter(project=self.get_project(), status=Task.STATUS_BACKLOG).select_related(
            "assignee", "created_by", "project").prefetch_related("subtasks", "dependencies__depends_on")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "project": self.get_project()}

    def perform_create(self, serializer):
        serializer.save(project=self.get_project(), created_by=self.request.user, status=Task.STATUS_BACKLOG)
