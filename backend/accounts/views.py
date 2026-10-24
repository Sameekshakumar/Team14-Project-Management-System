from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions, generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Workspace, WorkspaceInvitation, WorkspaceMembership
from .permissions import get_user_workspace_role
from .serializers import (
    LoginSerializer,
    RegisterSerializer,
    RoleAssignmentSerializer,
    UserSerializer,
    WorkspaceDetailSerializer,
    WorkspaceInvitationSerializer,
    WorkspaceMembershipSerializer,
    WorkspaceSerializer,
)


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


class WorkspaceListCreateView(generics.ListCreateAPIView):
    serializer_class = WorkspaceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Workspaces the caller owns or belongs to; owners normally also hold a
        # membership row, so de-duplicate the union.
        return Workspace.objects.filter(
            Q(owner=self.request.user) | Q(memberships__user=self.request.user)
        ).distinct().order_by("created_at")

    @transaction.atomic
    def perform_create(self, serializer):
        workspace = serializer.save(owner=self.request.user)
        WorkspaceMembership.objects.get_or_create(
            workspace=workspace,
            user=self.request.user,
            defaults={"role": "Owner"},
        )


class WorkspaceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_workspace(self, workspace_id):
        return get_object_or_404(Workspace, id=workspace_id)

    def get(self, request, workspace_id):
        workspace = self.get_workspace(workspace_id)
        role = get_user_workspace_role(request.user, workspace)
        if role is None:
            raise PermissionDenied("You are not a member of this workspace.")
        serializer = WorkspaceDetailSerializer(workspace, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, workspace_id):
        workspace = self.get_workspace(workspace_id)
        role = get_user_workspace_role(request.user, workspace)
        if role is None:
            raise PermissionDenied("You are not a member of this workspace.")
        if role == "Viewer":
            raise PermissionDenied("Viewers have read-only access and cannot create, edit, or delete content.")
        if role == "Member":
            raise PermissionDenied("Members cannot edit workspace settings.")

        serializer = WorkspaceSerializer(workspace, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            WorkspaceDetailSerializer(workspace, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, workspace_id):
        return self.patch(request, workspace_id)

    def delete(self, request, workspace_id):
        workspace = self.get_workspace(workspace_id)
        role = get_user_workspace_role(request.user, workspace)
        if role is None:
            raise PermissionDenied("You are not a member of this workspace.")
        if role != "Owner":
            raise PermissionDenied("Only a workspace Owner can delete a workspace.")
        workspace.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkspaceMemberListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, workspace_id):
        workspace = get_object_or_404(Workspace, id=workspace_id)
        role = get_user_workspace_role(request.user, workspace)
        if role is None:
            raise PermissionDenied("You are not a member of this workspace.")

        # Ensure the workspace owner has a membership record
        WorkspaceMembership.objects.get_or_create(
            workspace=workspace,
            user=workspace.owner,
            defaults={"role": "Owner"},
        )

        memberships = WorkspaceMembership.objects.filter(
            workspace=workspace
        ).select_related("user").order_by("joined_at")
        serializer = WorkspaceMembershipSerializer(memberships, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class WorkspaceMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_workspace_and_membership(self, request, workspace_id, user_id):
        workspace = get_object_or_404(Workspace, id=workspace_id)
        actor_role = get_user_workspace_role(request.user, workspace)
        if actor_role is None:
            raise PermissionDenied("You are not a member of this workspace.")

        if workspace.owner_id == user_id:
            WorkspaceMembership.objects.get_or_create(
                workspace=workspace,
                user=workspace.owner,
                defaults={"role": "Owner"},
            )

        target_membership = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user_id=user_id,
        ).select_related("user").first()

        if not target_membership:
            raise NotFound("User is not a member of this workspace.")

        return workspace, actor_role, target_membership

    def get(self, request, workspace_id, user_id):
        workspace, actor_role, target_membership = self.get_workspace_and_membership(
            request, workspace_id, user_id
        )
        serializer = WorkspaceMembershipSerializer(target_membership)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, workspace_id, user_id):
        workspace, actor_role, target_membership = self.get_workspace_and_membership(
            request, workspace_id, user_id
        )

        if actor_role not in ["Owner", "Admin"]:
            raise PermissionDenied("Only workspace Owners and Admins can assign roles.")

        serializer = RoleAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data["role"]

        # Prevent self-escalation
        if request.user.id == target_membership.user_id:
            if actor_role != "Owner" and new_role in ["Owner", "Admin"]:
                raise PermissionDenied("Users cannot escalate their own role.")

        # Admin restrictions per SRS:
        # 1. Admin cannot assign Owner role
        # 2. Admin cannot modify the Owner's role
        if actor_role == "Admin":
            if new_role == "Owner":
                raise PermissionDenied("Admins cannot assign the Owner role.")
            if target_membership.user_id == workspace.owner_id or target_membership.role == "Owner":
                raise PermissionDenied("Admins cannot modify the Owner's role.")

        # Prevent demoting the workspace Owner without a valid ownership transfer
        if target_membership.user_id == workspace.owner_id and new_role != "Owner":
            return Response(
                {"detail": "Cannot demote the workspace Owner. Transfer workspace ownership to another member first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_role == "Owner":
            # Only the current Owner can transfer ownership
            if actor_role != "Owner":
                raise PermissionDenied("Only the workspace Owner can transfer ownership.")

            # Make ownership transfer atomic
            with transaction.atomic():
                locked_workspace = Workspace.objects.select_for_update().get(id=workspace.id)
                new_owner = target_membership.user
                old_owner = request.user

                locked_workspace.owner = new_owner
                locked_workspace.save(update_fields=["owner"])

                target_membership.role = "Owner"
                target_membership.save(update_fields=["role"])

                old_membership = WorkspaceMembership.objects.filter(
                    workspace=locked_workspace,
                    user=old_owner,
                ).first()
                if old_membership:
                    old_membership.role = "Admin"
                    old_membership.save(update_fields=["role"])

            return Response(
                WorkspaceMembershipSerializer(target_membership).data,
                status=status.HTTP_200_OK,
            )

        # Standard role change (Admin, Member, Viewer)
        target_membership.role = new_role
        target_membership.save(update_fields=["role"])

        return Response(
            WorkspaceMembershipSerializer(target_membership).data,
            status=status.HTTP_200_OK,
        )

    def put(self, request, workspace_id, user_id):
        return self.patch(request, workspace_id, user_id)

    def delete(self, request, workspace_id, user_id):
        workspace, actor_role, target_membership = self.get_workspace_and_membership(
            request, workspace_id, user_id
        )

        if actor_role not in ["Owner", "Admin"]:
            raise PermissionDenied("Only workspace Owners and Admins can remove members.")

        # Prevent removing the current Owner without a valid ownership transfer
        if target_membership.user_id == workspace.owner_id:
            return Response(
                {"detail": "The workspace Owner cannot be removed. Transfer workspace ownership before removing this user."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Admin cannot remove an Owner or another Admin
        if actor_role == "Admin" and target_membership.role in ["Owner", "Admin"]:
            raise PermissionDenied("Admins cannot remove other Admins or the Owner.")

        target_membership.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkspaceInvitationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, workspace_id):
        workspace = get_object_or_404(
            Workspace,
            id=workspace_id,
        )

        role = get_user_workspace_role(request.user, workspace)
        if role not in ["Owner", "Admin"]:
            if role == "Viewer":
                raise PermissionDenied(
                    "Viewers have read-only access and cannot create, edit, or delete content."
                )
            raise PermissionDenied(
                "Only workspace Owners and Admins can create invitations."
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
