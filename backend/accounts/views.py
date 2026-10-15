from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    WorkspaceSerializer,
)
from datetime import timedelta
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from .models import Workspace, WorkspaceInvitation
from .serializers import WorkspaceInvitationSerializer
from django.db import transaction
from .models import WorkspaceMembership

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "anon"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": UserSerializer(user).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "anon"

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class WorkspaceCreateView(generics.CreateAPIView):
    serializer_class = WorkspaceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class WorkspaceInvitationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace,
            id=workspace_id,
        )

        if workspace.owner_id != request.user.id:
            raise PermissionDenied(
                "Only the workspace Owner can create invitations."
            )

        invitation = WorkspaceInvitation.objects.create(
            workspace=workspace,
            created_by=request.user,
            expires_at=timezone.now() + timedelta(days=7),
        )

        return Response(
            WorkspaceInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )

class WorkspaceInvitationAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, token):
        invitation = get_object_or_404(
            WorkspaceInvitation,
            token=token,
        )

        if invitation.is_expired():
            return Response(
                {"detail": "This invitation has expired."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invitation.accepted_at is not None:
            return Response(
                {"detail": "This invitation has already been used."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            invitation = WorkspaceInvitation.objects.select_for_update().get(
                pk=invitation.pk
            )

            if invitation.is_expired():
                return Response(
                    {"detail": "This invitation has expired."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if invitation.accepted_at is not None:
                return Response(
                    {"detail": "This invitation has already been used."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            membership, created = WorkspaceMembership.objects.get_or_create(
                workspace=invitation.workspace,
                user=request.user,
                defaults={"role": "Member"},
            )

            if not created:
                return Response(
                    {"detail": "You are already a member of this workspace."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            invitation.accepted_by = request.user
            invitation.accepted_at = timezone.now()
            invitation.save(
                update_fields=["accepted_by", "accepted_at"]
            )

        return Response(
            {
                "detail": "Invitation accepted successfully.",
                "workspace_id": str(invitation.workspace_id),
                "role": membership.role,
            },
            status=status.HTTP_200_OK,
        )
