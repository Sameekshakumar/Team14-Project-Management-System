from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import Sprint
from .serializers import ItemIdsSerializer, SprintCreateSerializer, SprintSerializer
from .services import assign_items, EmptySprint, SprintConflict

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
        return Task.objects.filter(project=self.get_project(), status=Task.STATUS_BACKLOG, sprint__isnull=True).select_related(
            "assignee", "created_by", "project").prefetch_related("subtasks", "dependencies__depends_on")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "project": self.get_project()}

    def perform_create(self, serializer):
        serializer.save(project=self.get_project(), created_by=self.request.user, status=Task.STATUS_BACKLOG)


def locked_sprint(user, sprint_id):
    # All planning mutations lock the project first, giving consistent lock order.
    sprint = get_object_or_404(Sprint.objects.select_related("project__workspace"), pk=sprint_id)
    require_write(user, sprint.project.workspace)
    Project.objects.select_for_update().get(pk=sprint.project_id)
    return Sprint.objects.select_for_update().get(pk=sprint_id)


class SprintCreateView(SprintErrorsMixin, APIView):
    @transaction.atomic
    def post(self, request):
        serializer = SprintCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=data.pop("project"))
        require_write(request.user, project.workspace)
        Project.objects.select_for_update().get(pk=project.pk)
        ids = data.pop("item_ids")
        sprint = Sprint.objects.create(project=project, created_by=request.user, **data)
        assign_items(sprint, ids)
        return Response(SprintSerializer(sprint).data, status=status.HTTP_201_CREATED)


class SprintListView(SprintErrorsMixin, generics.ListAPIView):
    serializer_class = SprintSerializer

    def get_queryset(self):
        project = get_object_or_404(Project.objects.select_related("workspace"), pk=self.kwargs["project_id"])
        require_member(self.request.user, project.workspace)
        return Sprint.objects.filter(project=project).prefetch_related("items")


class SprintItemsView(SprintErrorsMixin, APIView):
    @transaction.atomic
    def post(self, request, sprint_id):
        sprint = locked_sprint(request.user, sprint_id)
        serializer = ItemIdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assign_items(sprint, serializer.validated_data["item_ids"])
        return Response(SprintSerializer(sprint).data)


class SprintItemRemoveView(SprintErrorsMixin, APIView):
    @transaction.atomic
    def delete(self, request, sprint_id, task_id):
        sprint = locked_sprint(request.user, sprint_id)
        if sprint.status != "Planned":
            raise SprintConflict()
        task = get_object_or_404(Task.objects.select_for_update(), pk=task_id, sprint=sprint)
        if task.status not in [Task.STATUS_BACKLOG, Task.STATUS_TODO]:
            raise SprintConflict("Only unstarted items can be returned to the backlog.")
        task.sprint = None
        task.status = Task.STATUS_BACKLOG
        task.save(update_fields=["sprint", "status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class SprintStartView(SprintErrorsMixin, APIView):
    @transaction.atomic
    def post(self, request, sprint_id):
        sprint = locked_sprint(request.user, sprint_id)
        if sprint.status != "Planned":
            raise SprintConflict()
        if not sprint.items.exists():
            raise EmptySprint()
        from django.utils import timezone
        from .reporting import capture_snapshot, point_totals
        sprint.status = "Active"
        sprint.started_at = timezone.now()
        sprint.committed_story_points = point_totals(sprint)["total_points"]
        sprint.save(update_fields=["status", "started_at", "committed_story_points"])
        capture_snapshot(sprint.pk)
        return Response(SprintSerializer(sprint).data)
