from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from .models import Workspace
from datetime import timedelta
from django.utils import timezone
from .models import WorkspaceInvitation, WorkspaceMembership


User = get_user_model()


class RegistrationLoginTests(APITestCase):
    def setUp(self):
        self.register_url = "/api/auth/register/"
        self.login_url = "/api/auth/login/"
        self.valid_payload = {"email": "samarth@example.com", "password": "Str0ng-Example-Pass!"}

    def test_registration_creates_user_and_returns_tokens(self):
        response = self.client.post(self.register_url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertTrue(User.objects.filter(email="samarth@example.com").exists())
        user = User.objects.get(email="samarth@example.com")
        self.assertTrue(user.check_password(self.valid_payload["password"]))
        self.assertNotEqual(user.password, self.valid_payload["password"])
        self.assertNotIn("password", response.data["user"])

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.client.post(self.register_url, self.valid_payload, format="json")
        response = self.client.post(
            self.register_url,
            {"email": "SAMARTH@example.com", "password": "Another-Strong-Pass!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_returns_tokens_for_valid_credentials(self):
        User.objects.create_user(email="samarth@example.com", password=self.valid_payload["password"])
        response = self.client.post(self.login_url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_rejects_wrong_password(self):
        User.objects.create_user(email="samarth@example.com", password=self.valid_payload["password"])
        response = self.client.post(
            self.login_url,
            {"email": "samarth@example.com", "password": "Wrong-password!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("access", response.data)

    def test_registration_rejects_invalid_email(self):
        response = self.client.post(
            self.register_url,
            {"email": "not-an-email", "password": "Str0ng-Example-Pass!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class WorkspaceCreationTests(APITestCase):
    def setUp(self):
        self.workspace_url = "/api/auth/workspaces/"
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="Str0ng-Example-Pass!",
        )

    def test_unauthenticated_user_cannot_create_workspace(self):
        response = self.client.post(
            self.workspace_url,
            {"name": "Team Workspace"},
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_authenticated_user_can_create_workspace(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.workspace_url,
            {
                "name": "Team Workspace",
                "description": "Workspace for our project team",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Team Workspace")
        self.assertEqual(response.data["owner"], self.user.pk)

        workspace = Workspace.objects.get(name="Team Workspace")
        self.assertEqual(workspace.owner, self.user)
        self.assertIsNotNone(workspace.id)

    def test_empty_workspace_name_is_rejected(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.workspace_url,
            {"name": "   "},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Workspace.objects.exists())


class WorkspaceInvitationTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="Str0ng-Example-Pass!",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            password="Str0ng-Example-Pass!",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="Str0ng-Example-Pass!",
        )

        self.workspace = Workspace.objects.create(
            name="Team Workspace",
            description="Testing invitations",
            owner=self.owner,
        )

        self.create_url = (
            f"/api/auth/workspaces/{self.workspace.id}/invitations/"
        )

    def test_owner_can_create_invitation(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(self.create_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["token"])
        self.assertTrue(
            WorkspaceInvitation.objects.filter(
                workspace=self.workspace,
                created_by=self.owner,
            ).exists()
        )

    def test_non_owner_cannot_create_invitation(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(self.create_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            WorkspaceInvitation.objects.filter(
                workspace=self.workspace,
            ).exists()
        )

    def test_member_can_accept_valid_invitation(self):
        invitation = WorkspaceInvitation.objects.create(
            workspace=self.workspace,
            created_by=self.owner,
            expires_at=timezone.now() + timedelta(days=7),
        )
        self.client.force_authenticate(user=self.member)

        response = self.client.post(
            f"/api/auth/invitations/{invitation.token}/accept/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            WorkspaceMembership.objects.filter(
                workspace=self.workspace,
                user=self.member,
                role="Member",
            ).exists()
        )

        invitation.refresh_from_db()
        self.assertEqual(invitation.accepted_by, self.member)
        self.assertIsNotNone(invitation.accepted_at)

    def test_expired_invitation_is_rejected(self):
        invitation = WorkspaceInvitation.objects.create(
            workspace=self.workspace,
            created_by=self.owner,
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.client.force_authenticate(user=self.member)

        response = self.client.post(
            f"/api/auth/invitations/{invitation.token}/accept/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            WorkspaceMembership.objects.filter(
                workspace=self.workspace,
                user=self.member,
            ).exists()
        )

    def test_used_invitation_cannot_be_accepted_again(self):
        invitation = WorkspaceInvitation.objects.create(
            workspace=self.workspace,
            created_by=self.owner,
            expires_at=timezone.now() + timedelta(days=7),
            accepted_by=self.other_user,
            accepted_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.member)

        response = self.client.post(
            f"/api/auth/invitations/{invitation.token}/accept/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            WorkspaceMembership.objects.filter(
                workspace=self.workspace,
                user=self.member,
            ).exists()
        )


