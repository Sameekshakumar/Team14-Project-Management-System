"""
Issue #22 — Immediate Access Revocation on Member Removal (SEC-005)

Tests that after a user is removed from a workspace:
  - They had access before removal.
  - Removal succeeds for authorized users.
  - Their previously-issued, still-valid JWT is rejected on that workspace.
  - They cannot perform write operations in that workspace.
  - They still have access to other workspaces they remain a member of.
  - Existing active members retain their expected access.
  - Role-based access control continues working correctly.
  - Unauthorized users cannot remove workspace members.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Workspace, WorkspaceMembership

User = get_user_model()


def _access_token(user):
    """Return a fresh, valid access token string for *user*."""
    return str(RefreshToken.for_user(user).access_token)


class MemberAccessBeforeAndAfterRemovalTests(APITestCase):
    """
    SEC-005: Core revocation scenario.

    A removed member with a still-valid JWT must be denied access to the
    workspace they were removed from.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            email="sec005.owner@team14.test", password="Str0ng-Example-Pass!"
        )
        self.member = User.objects.create_user(
            email="sec005.member@team14.test", password="Str0ng-Example-Pass!"
        )

        self.workspace = Workspace.objects.create(
            name="Revocation Test Workspace",
            owner=self.owner,
        )
        self.membership = WorkspaceMembership.objects.create(
            workspace=self.workspace,
            user=self.member,
            role="Member",
        )

        self.ws_url = f"/api/auth/workspaces/{self.workspace.id}/"
        self.member_url = (
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"
        )

    # -----------------------------------------------------------------
    # Pre-removal: member has access
    # -----------------------------------------------------------------

    def test_member_can_access_workspace_before_removal(self):
        """A member with a valid JWT must be able to GET the workspace."""
        token = _access_token(self.member)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(self.ws_url)
        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            "Member should have read access before removal.",
        )

    def test_member_can_list_workspace_members_before_removal(self):
        """A member can list workspace members before being removed."""
        token = _access_token(self.member)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(
            f"/api/auth/workspaces/{self.workspace.id}/members/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # -----------------------------------------------------------------
    # Removal by authorized user
    # -----------------------------------------------------------------

    def test_owner_successfully_removes_member(self):
        """An Owner can remove a Member; the membership row is deleted."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.delete(self.member_url)
        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
            "Owner should be able to remove a member.",
        )
        self.assertFalse(
            WorkspaceMembership.objects.filter(
                workspace=self.workspace, user=self.member
            ).exists(),
            "Membership record must be deleted.",
        )

    def test_admin_successfully_removes_member(self):
        """An Admin can remove a plain Member."""
        admin = User.objects.create_user(
            email="sec005.admin@team14.test", password="Str0ng-Example-Pass!"
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=admin, role="Admin"
        )
        self.client.force_authenticate(user=admin)
        response = self.client.delete(self.member_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            WorkspaceMembership.objects.filter(
                workspace=self.workspace, user=self.member
            ).exists()
        )

    # -----------------------------------------------------------------
    # Post-removal: previously valid JWT is denied on this workspace
    # -----------------------------------------------------------------

    def test_removed_member_jwt_denied_on_workspace_detail(self):
        """
        A member's old, still-valid JWT must be denied on GET /workspaces/{id}/
        after removal.
        """
        # Capture a valid token BEFORE removal
        old_token = _access_token(self.member)

        # Remove the member
        self.client.force_authenticate(user=self.owner)
        self.client.delete(self.member_url)
        self.client.logout()

        # Present the old, still-valid JWT
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_token}")
        response = self.client.get(self.ws_url)
        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            "A previously valid JWT must be denied after membership removal.",
        )

    def test_removed_member_jwt_denied_on_member_list(self):
        """Removed member's JWT is denied on GET /workspaces/{id}/members/."""
        old_token = _access_token(self.member)

        self.client.force_authenticate(user=self.owner)
        self.client.delete(self.member_url)
        self.client.logout()

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_token}")
        response = self.client.get(
            f"/api/auth/workspaces/{self.workspace.id}/members/"
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
            "Removed member must not list workspace members.",
        )

    def test_removed_member_cannot_perform_write_operations(self):
        """Removed member's JWT is denied on PATCH /workspaces/{id}/."""
        old_token = _access_token(self.member)

        # Promote to Admin so they *would* have write access while a member
        self.membership.role = "Admin"
        self.membership.save()

        self.client.force_authenticate(user=self.owner)
        self.client.delete(self.member_url)
        self.client.logout()

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_token}")
        response = self.client.patch(
            self.ws_url, {"name": "Hacked Name"}, format="json"
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
            "Removed member must not be able to write to the workspace.",
        )

    def test_removed_member_cannot_invite_new_members(self):
        """
        A removed user (formerly Admin) cannot create an invitation using
        their old JWT.
        """
        old_token = _access_token(self.member)
        self.membership.role = "Admin"
        self.membership.save()

        self.client.force_authenticate(user=self.owner)
        self.client.delete(self.member_url)
        self.client.logout()

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_token}")
        response = self.client.post(
            f"/api/auth/workspaces/{self.workspace.id}/invitations/",
            {},
            format="json",
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )

    def test_removed_member_cannot_access_member_detail(self):
        """Removed member's JWT is denied on member detail endpoint."""
        old_token = _access_token(self.member)

        self.client.force_authenticate(user=self.owner)
        self.client.delete(self.member_url)
        self.client.logout()

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_token}")
        response = self.client.get(
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.owner.id}/"
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND],
        )

    # -----------------------------------------------------------------
    # Removed member retains access to OTHER workspaces
    # -----------------------------------------------------------------

    def test_removed_member_retains_access_to_other_workspace(self):
        """
        After being removed from workspace A the user must still have access
        to workspace B where their membership is intact.
        """
        other_workspace = Workspace.objects.create(
            name="Other Workspace",
            owner=self.owner,
        )
        WorkspaceMembership.objects.create(
            workspace=other_workspace,
            user=self.member,
            role="Member",
        )
        other_ws_url = f"/api/auth/workspaces/{other_workspace.id}/"

        # Remove from first workspace
        self.client.force_authenticate(user=self.owner)
        self.client.delete(self.member_url)
        self.client.logout()

        # Must still have access to the other workspace
        token = _access_token(self.member)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(other_ws_url)
        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            "Removed member must still access other workspaces.",
        )

    def test_removed_member_other_workspace_still_listed(self):
        """
        The workspace list for the removed member still includes the other
        workspace they belong to.
        """
        other_workspace = Workspace.objects.create(
            name="Retained Workspace",
            owner=self.owner,
        )
        WorkspaceMembership.objects.create(
            workspace=other_workspace,
            user=self.member,
            role="Member",
        )

        # Remove from first workspace
        self.client.force_authenticate(user=self.owner)
        self.client.delete(self.member_url)
        self.client.logout()

        token = _access_token(self.member)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get("/api/auth/workspaces/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ws_names = [w["name"] for w in response.data]
        self.assertIn(
            "Retained Workspace",
            ws_names,
            "Retained workspace must appear in list.",
        )
        self.assertNotIn(
            "Revocation Test Workspace",
            ws_names,
            "Removed workspace must not appear in list.",
        )


class ExistingMembersUnaffectedTests(APITestCase):
    """Existing active members retain their expected access after a removal."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="sec005.unaffected.owner@team14.test",
            password="Str0ng-Example-Pass!",
        )
        self.admin = User.objects.create_user(
            email="sec005.unaffected.admin@team14.test",
            password="Str0ng-Example-Pass!",
        )
        self.member_to_remove = User.objects.create_user(
            email="sec005.to.remove@team14.test", password="Str0ng-Example-Pass!"
        )
        self.viewer = User.objects.create_user(
            email="sec005.unaffected.viewer@team14.test",
            password="Str0ng-Example-Pass!",
        )

        self.workspace = Workspace.objects.create(
            name="Unaffected Members Workspace", owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.admin, role="Admin"
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.member_to_remove, role="Member"
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.viewer, role="Viewer"
        )

        self.ws_url = f"/api/auth/workspaces/{self.workspace.id}/"

    def _remove_target_member(self):
        """Helper: owner removes the target member."""
        self.client.force_authenticate(user=self.owner)
        self.client.delete(
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.member_to_remove.id}/"
        )
        self.client.logout()

    def test_owner_still_has_full_access_after_removal(self):
        self._remove_target_member()
        self.client.force_authenticate(user=self.owner)
        response = self.client.get(self.ws_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current_user_role"], "Owner")

    def test_admin_still_has_access_after_removal(self):
        self._remove_target_member()
        token = _access_token(self.admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(self.ws_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current_user_role"], "Admin")

    def test_viewer_still_has_read_access_after_removal(self):
        self._remove_target_member()
        token = _access_token(self.viewer)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(self.ws_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current_user_role"], "Viewer")


class RoleBasedAccessControlIntegrity(APITestCase):
    """Existing RBAC rules continue working correctly after removal logic."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="sec005.rbac.owner@team14.test", password="Str0ng-Example-Pass!"
        )
        self.admin = User.objects.create_user(
            email="sec005.rbac.admin@team14.test", password="Str0ng-Example-Pass!"
        )
        self.member = User.objects.create_user(
            email="sec005.rbac.member@team14.test", password="Str0ng-Example-Pass!"
        )
        self.viewer = User.objects.create_user(
            email="sec005.rbac.viewer@team14.test", password="Str0ng-Example-Pass!"
        )

        self.workspace = Workspace.objects.create(
            name="RBAC Integrity Workspace", owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.admin, role="Admin"
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.member, role="Member"
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.viewer, role="Viewer"
        )
        self.ws_url = f"/api/auth/workspaces/{self.workspace.id}/"

    def test_viewer_still_cannot_write_after_another_removal(self):
        """Viewer write restrictions remain even after another member is removed."""
        # Remove member
        self.client.force_authenticate(user=self.owner)
        self.client.delete(
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"
        )
        self.client.logout()

        # Viewer write attempt
        token = _access_token(self.viewer)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.patch(self.ws_url, {"name": "Bad Name"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_remove_owner(self):
        """Admin cannot remove the workspace Owner (unchanged RBAC rule)."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.owner.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_member_cannot_remove_another_member(self):
        """A plain Member has no authority to remove other members."""
        # Create extra member target
        extra = User.objects.create_user(
            email="sec005.rbac.extra@team14.test", password="Str0ng-Example-Pass!"
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=extra, role="Member"
        )
        self.client.force_authenticate(user=self.member)
        response = self.client.delete(
            f"/api/auth/workspaces/{self.workspace.id}/members/{extra.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_remove_member(self):
        """A Viewer has no authority to remove members."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.delete(
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class UnauthorizedRemovalAttemptTests(APITestCase):
    """Unauthorized users cannot remove workspace members."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="sec005.unauth.owner@team14.test", password="Str0ng-Example-Pass!"
        )
        self.member = User.objects.create_user(
            email="sec005.unauth.member@team14.test", password="Str0ng-Example-Pass!"
        )
        self.outsider = User.objects.create_user(
            email="sec005.outsider@team14.test", password="Str0ng-Example-Pass!"
        )

        self.workspace = Workspace.objects.create(
            name="Unauthorized Removal Workspace", owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.member, role="Member"
        )

        self.remove_url = (
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"
        )

    def test_outsider_cannot_remove_member(self):
        """A user not in the workspace cannot remove members."""
        self.client.force_authenticate(user=self.outsider)
        response = self.client.delete(self.remove_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_request_cannot_remove_member(self):
        """Unauthenticated requests are rejected."""
        response = self.client.delete(self.remove_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_nonexistent_member_removal_returns_404(self):
        """Trying to remove a user who is not a member returns 404."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.delete(
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.outsider.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class EdgeCasesTests(APITestCase):
    """Edge-case handling for the revocation implementation."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="sec005.edge.owner@team14.test", password="Str0ng-Example-Pass!"
        )
        self.member = User.objects.create_user(
            email="sec005.edge.member@team14.test", password="Str0ng-Example-Pass!"
        )
        self.workspace = Workspace.objects.create(
            name="Edge Case Workspace", owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.member, role="Member"
        )

    def test_owner_cannot_be_removed(self):
        """The workspace Owner cannot be removed via the member endpoint."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.delete(
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.owner.id}/"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Owner membership must still exist
        self.assertTrue(
            WorkspaceMembership.objects.filter(
                workspace=self.workspace, user=self.owner
            ).exists()
        )

    def test_removed_member_does_not_affect_workspace_ownership(self):
        """Removing a regular member does not change workspace ownership."""
        self.client.force_authenticate(user=self.owner)
        self.client.delete(
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"
        )
        self.workspace.refresh_from_db()
        self.assertEqual(self.workspace.owner, self.owner)

    def test_removed_member_jwt_still_valid_for_non_workspace_endpoints(self):
        """
        The old JWT remains valid for non-workspace endpoints (like /me).
        Only workspace access is revoked — no global token invalidation.
        """
        old_token = _access_token(self.member)

        # Remove the member
        self.client.force_authenticate(user=self.owner)
        self.client.delete(
            f"/api/auth/workspaces/{self.workspace.id}/members/{self.member.id}/"
        )
        self.client.logout()

        # /me should still work: JWT is valid, just workspace membership gone
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_token}")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            "JWT must remain globally valid after workspace-scoped removal.",
        )
        self.assertEqual(response.data["email"], self.member.email)

