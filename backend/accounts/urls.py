from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    LoginView,
    MeView,
    RegisterView,
    WorkspaceCreateView,
    WorkspaceDetailView,
    WorkspaceInvitationAcceptView,
    WorkspaceInvitationCreateView,
    WorkspaceMemberDetailView,
    WorkspaceMemberListView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("workspaces/", WorkspaceCreateView.as_view(), name="workspace-create"),
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
