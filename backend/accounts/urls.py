from django.urls import path
from .views import (
    LoggingTokenRefreshView,
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    WorkspaceListCreateView,
    WorkspaceDetailView,
    WorkspaceInvitationAcceptView,
    WorkspaceInvitationCreateView,
    WorkspaceMemberDetailView,
    WorkspaceMemberListView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("token/refresh/", LoggingTokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("workspaces/", WorkspaceListCreateView.as_view(), name="workspace-list-create"),
    path(
        "workspaces/<uuid:workspace_id>/",
        WorkspaceDetailView.as_view(),
        name="workspace-detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/members/",
        WorkspaceMemberListView.as_view(),
        name="workspace-member-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/members/<int:user_id>/",
        WorkspaceMemberDetailView.as_view(),
        name="workspace-member-detail",
    ),
    path(
        "workspaces/<uuid:workspace_id>/invitations/",
        WorkspaceInvitationCreateView.as_view(),
        name="workspace-invitation-create",
    ),
    path(
        "invitations/<str:token>/accept/",
        WorkspaceInvitationAcceptView.as_view(),
        name="workspace-invitation-accept",
    ),
]
