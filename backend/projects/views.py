from django.shortcuts import get_object_or_404
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from accounts.models import Workspace
from accounts.permissions import get_user_workspace_role

from .models import Project
from .serializers import ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    """
    FR-TASK-01: projects live inside a workspace, so every action is scoped to
    the workspace in the URL and gated on the caller's role in that workspace.
    """
    serializer_class = ProjectSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_url_kwarg = "project_id"

    def get_workspace(self):
        workspace = get_object_or_404(Workspace, id=self.kwargs["workspace_id"])
        role = get_user_workspace_role(self.request.user, workspace)
        if role is None:
            raise PermissionDenied("You are not a member of this workspace.")
        return workspace, role

    def get_queryset(self):
        workspace, _role = self.get_workspace()
        return Project.objects.filter(workspace=workspace).select_related(
            "workspace", "created_by"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if "workspace_id" in self.kwargs:
            context["workspace"] = get_object_or_404(
                Workspace, id=self.kwargs["workspace_id"]
            )
        return context

    def perform_create(self, serializer):
        workspace, role = self.get_workspace()
        if role == "Viewer":
            raise PermissionDenied(
                "Viewers have read-only access and cannot create, edit, or delete content."
            )
        serializer.save(workspace=workspace, created_by=self.request.user)

    def perform_update(self, serializer):
        _workspace, role = self.get_workspace()
        if role == "Viewer":
            raise PermissionDenied(
                "Viewers have read-only access and cannot create, edit, or delete content."
            )
        serializer.save()

    def perform_destroy(self, instance):
        _workspace, role = self.get_workspace()
        if role not in ["Owner", "Admin"]:
            raise PermissionDenied(
                "Only workspace Owners and Admins can delete a project."
            )
        instance.delete()
