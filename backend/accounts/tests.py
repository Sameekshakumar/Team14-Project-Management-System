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


class RoleBasedAccessControlTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="Str0ng-Example-Pass!",
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="Str0ng-Example-Pass!",
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            password="Str0ng-Example-Pass!",
        )
        self.viewer = User.objects.create_user(
            email="viewer@example.com",
            password="Str0ng-Example-Pass!",
        )
        self.other_user = User.objects.create_user(
            email="outsider@example.com",
            password="Str0ng-Example-Pass!",
        )

        self.workspace = Workspace.objects.create(
            name="Main Workspace",
            description="RBAC Test Workspace",
            owner=self.owner,
        )
        self.admin_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.admin,
            role="Admin",
        )
        self.member_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.member,
            role="Member",
        )
        self.viewer_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.viewer,
            role="Viewer",
        )

        self.other_workspace = Workspace.objects.create(
            name="Other Workspace",
            description="Cross workspace test",
            owner=self.other_user,
        )

    def test_workspace_creation_atomically_creates_owner_membership(self):
        new_user = User.objects.create_user(
            email="newcreator@example.com",
            password="Str0ng-Example-Pass!",
        )
        self.client.force_authenticate(user=new_user)
        response = self.client.post(
            "/api/auth/workspaces/",
            {"name": "Created By New User", "description": "Testing atomic owner membership"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ws_id = response.data["id"]
        ws = Workspace.objects.get(id=ws_id)
        self.assertEqual(ws.owner, new_user)
        membership = WorkspaceMembership.objects.filter(workspace=ws, user=new_user).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, "Owner")

    def test_owner_can_assign_admin_and_viewer_roles(self):
        self.client.force_authenticate(user=self.owner)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"

        # Owner assigns Admin
        response = self.client.patch(url, {"role": "Admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "Admin")
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.role, "Admin")

        # Owner assigns Viewer
        response = self.client.patch(url, {"role": "Viewer"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "Viewer")
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.role, "Viewer")

    def test_admin_can_assign_member_and_viewer_roles(self):
        self.client.force_authenticate(user=self.admin)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"

        response = self.client.patch(url, {"role": "Viewer"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.role, "Viewer")

        response = self.client.patch(url, {"role": "Member"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.role, "Member")

    def test_admin_cannot_assign_owner_role(self):
        self.client.force_authenticate(user=self.admin)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"
        response = self.client.patch(url, {"role": "Owner"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.member_membership.refresh_from_db()
        self.assertNotEqual(self.member_membership.role, "Owner")

    def test_admin_cannot_modify_owner_role(self):
        self.client.force_authenticate(user=self.admin)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.owner.id}/"
        response = self.client.patch(url, {"role": "Admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_member_and_viewer_cannot_assign_roles(self):
        self.client.force_authenticate(user=self.member)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.viewer.id}/"
        response = self.client.patch(url, {"role": "Member"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.viewer)
        response = self.client.patch(url, {"role": "Admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_self_escalate_role(self):
        self.client.force_authenticate(user=self.member)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"
        response = self.client.patch(url, {"role": "Admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        admin_url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.admin.id}/"
        response = self.client.patch(admin_url, {"role": "Owner"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_role_choice_is_rejected(self):
        self.client.force_authenticate(user=self.owner)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"
        response = self.client.patch(url, {"role": "SuperUser"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_existent_member_returns_404(self):
        self.client.force_authenticate(user=self.owner)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.other_user.id}/"
        response = self.client.patch(url, {"role": "Admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cross_workspace_isolation(self):
        self.client.force_authenticate(user=self.other_user)
        detail_url = f"/api/auth/workspaces/{self.workspace.id}/"
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        members_url = f"/api/auth/workspaces/{self.workspace.id}/members/"
        response = self.client.get(members_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        assign_url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"
        response = self.client.patch(assign_url, {"role": "Admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_read_only_and_write_restrictions(self):
        self.client.force_authenticate(user=self.viewer)
        ws_url = f"/api/auth/workspaces/{self.workspace.id}/"

        get_res = self.client.get(ws_url)
        self.assertEqual(get_res.status_code, status.HTTP_200_OK)
        self.assertEqual(get_res.data["current_user_role"], "Viewer")

        members_res = self.client.get(f"{ws_url}members/")
        self.assertEqual(members_res.status_code, status.HTTP_200_OK)

        patch_res = self.client.patch(ws_url, {"name": "Hacked Name"}, format="json")
        self.assertEqual(patch_res.status_code, status.HTTP_403_FORBIDDEN)

        del_res = self.client.delete(ws_url)
        self.assertEqual(del_res.status_code, status.HTTP_403_FORBIDDEN)

        invite_res = self.client.post(f"{ws_url}invitations/", {}, format="json")
        self.assertEqual(invite_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_member_write_restrictions_on_workspace(self):
        self.client.force_authenticate(user=self.member)
        ws_url = f"/api/auth/workspaces/{self.workspace.id}/"

        self.assertEqual(self.client.get(ws_url).status_code, status.HTTP_200_OK)

        self.assertEqual(
            self.client.patch(ws_url, {"name": "New Name"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertEqual(
            self.client.delete(ws_url).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.assertEqual(
            self.client.post(f"{ws_url}invitations/", {}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_admin_and_owner_permissions(self):
        self.client.force_authenticate(user=self.admin)
        ws_url = f"/api/auth/workspaces/{self.workspace.id}/"
        patch_res = self.client.patch(ws_url, {"description": "Updated by admin"}, format="json")
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.description, "Updated by admin")

        invite_res = self.client.post(f"{ws_url}invitations/", {}, format="json")
        self.assertEqual(invite_res.status_code, status.HTTP_201_CREATED)

        self.assertEqual(self.client.delete(ws_url).status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.owner)
        self.assertEqual(self.client.delete(ws_url).status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Workspace.objects.filter(id=self.workspace.id).exists())

    def test_atomic_ownership_transfer(self):
        self.client.force_authenticate(user=self.owner)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"

        response = self.client.patch(url, {"role": "Owner"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.owner, self.member)

        self.member_membership.refresh_from_db()
        self.assertEqual(self.member_membership.role, "Owner")

        former_owner_membership = WorkspaceMembership.objects.get(
            workspace=self.workspace,
            user=self.owner,
        )
        self.assertEqual(former_owner_membership.role, "Admin")

        response = self.client.patch(
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.admin.id}/",
            {"role": "Owner"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_demote_or_remove_owner_without_transfer(self):
        self.client.force_authenticate(user=self.owner)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.owner.id}/"

        response = self.client.patch(url, {"role": "Member"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        del_res = self.client.delete(url)
        self.assertEqual(del_res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_member_removal_and_immediate_access_revocation(self):
        self.client.force_authenticate(user=self.admin)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"

        del_res = self.client.delete(url)
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            WorkspaceMembership.objects.filter(
                workspace=self.workspace,
                user=self.member,
            ).exists()
        )

        self.client.force_authenticate(user=self.member)
        res = self.client.get(f"/api/auth/workspaces/{self.workspace.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_remove_another_admin(self):
        other_admin = User.objects.create_user(
            email="admin2@example.com",
            password="Str0ng-Example-Pass!",
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=other_admin,
            role="Admin",
        )
        self.client.force_authenticate(user=self.admin)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{other_admin.id}/"
        del_res = self.client.delete(url)
        self.assertEqual(del_res.status_code, status.HTTP_403_FORBIDDEN)

    def test_role_persistence_and_subsequent_permission_enforcement(self):
        self.client.force_authenticate(user=self.owner)
        url = f"/api/auth/workspaces/{self.workspace.id}/members/{self.viewer.id}/"
        self.client.patch(url, {"role": "Member"}, format="json")

        self.viewer_membership.refresh_from_db()
        self.assertEqual(self.viewer_membership.role, "Member")

        self.client.force_authenticate(user=self.viewer)
        res = self.client.get(f"/api/auth/workspaces/{self.workspace.id}/")
        self.assertEqual(res.data["current_user_role"], "Member")

        self.client.force_authenticate(user=self.owner)
        self.client.patch(url, {"role": "Viewer"}, format="json")

        self.client.force_authenticate(user=self.viewer)
        res = self.client.patch(
            f"/api/auth/workspaces/{self.workspace.id}/",
            {"name": "Changed"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)





class WorkspaceListTests(APITestCase):
    """The board UI needs to enumerate the workspaces a user can open."""

    def setUp(self):
        self.owner = User.objects.create_user(email="wl-owner@team14.test", password="StrongPass!234")
        self.member = User.objects.create_user(email="wl-member@team14.test", password="StrongPass!234")
        self.outsider = User.objects.create_user(email="wl-outsider@team14.test", password="StrongPass!234")

        self.owned = Workspace.objects.create(name="Owned", owner=self.owner)
        self.joined = Workspace.objects.create(name="Joined", owner=self.outsider)
        WorkspaceMembership.objects.update_or_create(
            workspace=self.joined, user=self.member, defaults={"role": "Member"}
        )
        self.url = "/api/auth/workspaces/"

    def test_unauthenticated_user_cannot_list_workspaces(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_owner_sees_owned_workspace_once(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([w["name"] for w in response.data], ["Owned"])

    def test_member_sees_only_workspaces_they_belong_to(self):
        self.client.force_authenticate(self.member)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([w["name"] for w in response.data], ["Joined"])

    def test_user_with_no_workspaces_gets_empty_list(self):
        loner = User.objects.create_user(email="wl-loner@team14.test", password="StrongPass!234")
        self.client.force_authenticate(loner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_creating_a_workspace_still_works(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(self.url, {"name": "Fresh"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            sorted(w["name"] for w in self.client.get(self.url).data), ["Fresh", "Joined"]
        )
