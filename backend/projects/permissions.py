from rest_framework.exceptions import PermissionDenied

from accounts.permissions import get_user_workspace_role

NOT_A_MEMBER = "You are not a member of this workspace."
READ_ONLY = "Viewers have read-only access and cannot create, edit, or delete content."


def require_member(user, workspace):
    """Returns the caller's role, or 403 if they are not in the workspace."""
    role = get_user_workspace_role(user, workspace)
    if role is None:
        raise PermissionDenied(NOT_A_MEMBER)
    return role


def require_write(user, workspace):
    """Returns the caller's role, or 403 if they cannot modify workspace content."""
    role = require_member(user, workspace)
    if role == "Viewer":
        raise PermissionDenied(READ_ONLY)
    return role
