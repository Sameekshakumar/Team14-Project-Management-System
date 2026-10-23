from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, LoginView, MeView,WorkspaceCreateView,WorkspaceInvitationCreateView,WorkspaceInvitationAcceptView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("workspaces/", WorkspaceCreateView.as_view(), name="workspace-create"),
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
