from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from .models import Workspace, WorkspaceMembership


def get_user_workspace_role(user, workspace):
    """
    Returns the role of the user within the specified workspace:
    'Owner', 'Admin', 'Member', 'Viewer', or None if not a member.
    """
    if not user or not user.is_authenticated:
        return None
    if workspace.owner_id == user.id:
        return "Owner"
    membership = WorkspaceMembership.objects.filter(
        workspace=workspace,
        user=user,
    ).first()
    if membership:
        return membership.role
    return None


class IsWorkspaceMember(permissions.BasePermission):
    """
    Allows access only to authenticated users who are members of the workspace.
    """
    message = "You are not a member of this workspace."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        workspace = obj if isinstance(obj, Workspace) else getattr(obj, "workspace", None)
        if not workspace:
            return False
        role = get_user_workspace_role(request.user, workspace)
        return role is not None


class IsWorkspaceAdminOrOwner(permissions.BasePermission):
    """
    Allows access only to workspace Owners and Admins.
    """
    message = "Only workspace Owners and Admins can perform this action."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        workspace = obj if isinstance(obj, Workspace) else getattr(obj, "workspace", None)
        if not workspace:
            return False
        role = get_user_workspace_role(request.user, workspace)
        return role in ["Owner", "Admin"]


class IsWorkspaceOwner(permissions.BasePermission):
    """
    Allows access only to the workspace Owner.
    """
    message = "Only the workspace Owner can perform this action."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        workspace = obj if isinstance(obj, Workspace) else getattr(obj, "workspace", None)
        if not workspace:
            return False
        role = get_user_workspace_role(request.user, workspace)
        return role == "Owner"


class WorkspaceContentPermission(permissions.BasePermission):
    """
    Enforces RBAC on workspace content:
    - Safe methods (GET, HEAD, OPTIONS): Accessible to all workspace members (Owner, Admin, Member, Viewer).
    - Write methods (POST, PUT, PATCH, DELETE): Denied for Viewers and non-members.
    """
    message = "Viewers have read-only access and cannot create, edit, or delete content."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        workspace = obj if isinstance(obj, Workspace) else getattr(obj, "workspace", None)
        if not workspace:
            return False
        role = get_user_workspace_role(request.user, workspace)
        if not role:
            self.message = "You are not a member of this workspace."
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        if role == "Viewer":
            self.message = "Viewers have read-only access and cannot create, edit, or delete content."
            return False
        return True
