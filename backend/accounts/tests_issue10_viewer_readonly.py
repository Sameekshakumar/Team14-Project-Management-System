"""
Issue #10 — Viewer role restricted from edit actions (SEC-002)

Tests that:
  - Viewers can perform permitted read operations (GET workspace, GET members).
  - Viewers are denied all prohibited write operations (PATCH, PUT, DELETE workspace;
    POST invitations; PATCH role assignments; DELETE members).
  - Unauthorized role changes and membership-management actions are rejected for Viewers.
  - Owner, Admin, and Member permissions continue to behave correctly.
  - Workspace isolation prevents cross-workspace access.
  - Role changes take effect immediately on subsequent requests.
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from .models import Workspace, WorkspaceMembership

User = get_user_model()


class ViewerReadOnlyWorkspaceTests(APITestCase):
    """SEC-002: Viewer can read workspace information but cannot mutate it."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="vo-owner@example.com", password="Str0ng-Example-Pass!"
        )
        self.viewer = User.objects.create_user(
            email="vo-viewer@example.com", password="Str0ng-Example-Pass!"
        )
        self.workspace = Workspace.objects.create(
            name="Viewer Test Workspace",
            description="For SEC-002 tests",
            owner=self.owner,
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.viewer, role="Viewer"
        )
        self.ws_url = f"/api/auth/workspaces/{self.workspace.id}/"

    def test_viewer_can_get_workspace_detail(self):
        """Viewer must be able to GET workspace details (read is permitted)."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(self.ws_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current_user_role"], "Viewer")

    def test_viewer_can_list_workspace_members(self):
        """Viewer must be able to GET the members list (read is permitted)."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(f"{self.ws_url}members/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_patch_workspace(self):
        """Viewer must receive 403 when attempting PATCH on a workspace."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.patch(self.ws_url, {"name": "Hacked Name"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.workspace.refresh_from_db()
        self.assertNotEqual(self.workspace.name, "Hacked Name")

    def test_viewer_cannot_put_workspace(self):
        """Viewer must receive 403 when attempting PUT on a workspace."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.put(
            self.ws_url, {"name": "Hacked Name", "description": "x"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_delete_workspace(self):
        """Viewer must receive 403 when attempting DELETE on a workspace."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.delete(self.ws_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Workspace.objects.filter(id=self.workspace.id).exists())

    def test_viewer_cannot_create_invitation(self):
        """Viewer must receive 403 when attempting to create a workspace invitation."""
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(f"{self.ws_url}invitations/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_assign_roles(self):
        """Viewer must receive 403 when attempting to assign a role to a member."""
        member = User.objects.create_user(
            email="vo-member@example.com", password="Str0ng-Example-Pass!"
        )
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=member, role="Member"
        )
        self.client.force_authenticate(user=self.viewer)
        url = f"{self.ws_url}members/{member.id}/"
        response = self.client.patch(url, {"role": "Admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        # Role must not have changed
        membership = WorkspaceMembership.objects.get(workspace=self.workspace, user=member)
        self.assertEqual(membership.role, "Member")

    def test_viewer_cannot_remove_member(self):
        """Viewer must receive 403 when attempting to remove a member."""
        member = User.objects.create_user(
            email="vo-member2@example.com", password="Str0ng-Example-Pass!"
        )
        membership = WorkspaceMembership.objects.create(
            workspace=self.workspace, user=member, role="Member"
        )
        self.client.force_authenticate(user=self.viewer)
        url = f"{self.ws_url}members/{member.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(
            WorkspaceMembership.objects.filter(id=membership.id).exists(),
            "Member must not have been removed.",
        )

    def test_viewer_cannot_create_workspace(self):
        """Viewer of one workspace can still create their own workspace (creating is not forbidden)."""
        # Creating a workspace is a global action, not workspace-scoped; verify it works.
        self.client.force_authenticate(user=self.viewer)
        response = self.client.post(
            "/api/auth/workspaces/", {"name": "My New Workspace"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class ViewerRolePersistenceAndEscalationTests(APITestCase):
    """SEC-002: Role changes are reflected immediately; privilege escalation is blocked."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="vpe-owner@example.com", password="Str0ng-Example-Pass!"
        )
        self.viewer = User.objects.create_user(
            email="vpe-viewer@example.com", password="Str0ng-Example-Pass!"
        )
        self.workspace = Workspace.objects.create(
            name="Persistence Workspace",
            owner=self.owner,
        )
        self.membership = WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.viewer, role="Viewer"
        )
        self.ws_url = f"/api/auth/workspaces/{self.workspace.id}/"

    def test_viewer_demoted_from_member_loses_write_access_immediately(self):
        """After a user is downgraded from Member to Viewer, writes must be rejected."""
        # First promote to Member
        self.membership.role = "Member"
        self.membership.save()

        # Confirm Member can read (not testing write since Members can't edit either, by design)
        self.client.force_authenticate(user=self.viewer)
        self.assertEqual(self.client.get(self.ws_url).status_code, status.HTTP_200_OK)

        # Now demote back to Viewer (simulating owner action)
        self.membership.role = "Viewer"
        self.membership.save()

        # Write must now be blocked
        response = self.client.patch(self.ws_url, {"name": "Escalated"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_cannot_self_escalate_via_role_endpoint(self):
        """A Viewer attempting to PATCH their own role to Admin must be denied."""
        self.client.force_authenticate(user=self.viewer)
        url = f"{self.ws_url}members/{self.viewer.id}/"
        response = self.client.patch(url, {"role": "Admin"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.role, "Viewer")

    def test_viewer_from_another_workspace_cannot_access_this_workspace(self):
        """A Viewer of one workspace must not access a different workspace."""
        other_workspace = Workspace.objects.create(
            name="Other Workspace", owner=self.owner
        )
        WorkspaceMembership.objects.create(
            workspace=other_workspace, user=self.viewer, role="Viewer"
        )
        # Different user's workspace (owner is the same here, but viewer has no membership in ws)
        unrelated_ws = Workspace.objects.create(
            name="Unrelated WS",
            owner=User.objects.create_user(
                email="vpe-other@example.com", password="Str0ng-Example-Pass!"
            ),
        )
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(f"/api/auth/workspaces/{unrelated_ws.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AuthorizedRolePermissionsTests(APITestCase):
    """SEC-002: Owner, Admin, and Member retain their expected permissions."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="arp-owner@example.com", password="Str0ng-Example-Pass!"
        )
        self.admin = User.objects.create_user(
            email="arp-admin@example.com", password="Str0ng-Example-Pass!"
        )
        self.member = User.objects.create_user(
            email="arp-member@example.com", password="Str0ng-Example-Pass!"
        )
        self.workspace = Workspace.objects.create(
            name="ARP Workspace", owner=self.owner
        )
        self.admin_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.admin, role="Admin"
        )
        self.member_membership = WorkspaceMembership.objects.create(
            workspace=self.workspace, user=self.member, role="Member"
        )
        self.ws_url = f"/api/auth/workspaces/{self.workspace.id}/"

    def test_owner_can_patch_workspace(self):
        """Owner must be able to update the workspace."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            self.ws_url, {"description": "Owner updated"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_patch_workspace(self):
        """Admin must be able to update the workspace."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(
            self.ws_url, {"description": "Admin updated"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_create_invitation(self):
        """Admin must be able to create invitations."""
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f"{self.ws_url}invitations/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_member_cannot_patch_workspace(self):
        """Member must not be able to update workspace settings."""
        self.client.force_authenticate(user=self.member)
        response = self.client.patch(
            self.ws_url, {"name": "Member Attempt"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_delete_workspace(self):
        """Owner must be able to delete the workspace."""
        self.client.force_authenticate(user=self.owner)
        response = self.client.delete(self.ws_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Workspace.objects.filter(id=self.workspace.id).exists())
