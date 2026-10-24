from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Workspace, WorkspaceMembership

from .models import Project

User = get_user_model()


class ProjectCreationTests(APITestCase):
    """FR-TASK-01: an authenticated member can create a project in a workspace."""

    def setUp(self):
        self.owner = User.objects.create_user(email="owner@team14.test", password="StrongPass!234")
        self.admin = User.objects.create_user(email="admin@team14.test", password="StrongPass!234")
        self.member = User.objects.create_user(email="member@team14.test", password="StrongPass!234")
        self.viewer = User.objects.create_user(email="viewer@team14.test", password="StrongPass!234")
        self.outsider = User.objects.create_user(email="outsider@team14.test", password="StrongPass!234")

        self.workspace = Workspace.objects.create(name="Team 14", owner=self.owner)
        for user, role in [(self.admin, "Admin"), (self.member, "Member"), (self.viewer, "Viewer")]:
            WorkspaceMembership.objects.update_or_create(
                workspace=self.workspace, user=user, defaults={"role": role}
            )

        self.list_url = reverse("project-list", args=[self.workspace.id])

    def detail_url(self, project):
        return reverse("project-detail", args=[self.workspace.id, project.id])

    def create_project(self, name="Apollo"):
        return Project.objects.create(
            workspace=self.workspace, name=name, created_by=self.owner
        )

    def test_unauthenticated_user_cannot_create_project(self):
        response = self.client.post(self.list_url, {"name": "Apollo"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_member_can_create_project(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(
            self.list_url, {"name": "Apollo", "description": "First project"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Apollo")
        self.assertEqual(response.data["created_by"], self.member.id)

        project = Project.objects.get(id=response.data["id"])
        self.assertEqual(project.workspace, self.workspace)

    def test_owner_and_admin_can_create_project(self):
        for index, user in enumerate([self.owner, self.admin]):
            self.client.force_authenticate(user)
            response = self.client.post(
                self.list_url, {"name": f"Project {index}"}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_viewer_cannot_create_project(self):
        self.client.force_authenticate(self.viewer)
        response = self.client.post(self.list_url, {"name": "Apollo"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Project.objects.count(), 0)

    def test_non_member_cannot_create_or_list_projects(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(
            self.client.post(self.list_url, {"name": "Apollo"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_403_FORBIDDEN)

    def test_empty_project_name_is_rejected(self):
        self.client.force_authenticate(self.member)
        for bad_name in ["", "   "]:
            response = self.client.post(self.list_url, {"name": bad_name}, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Project.objects.count(), 0)

    def test_project_name_is_trimmed(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(self.list_url, {"name": "  Apollo  "}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Apollo")

    def test_duplicate_project_name_in_same_workspace_is_rejected(self):
        self.create_project("Apollo")
        self.client.force_authenticate(self.member)
        response = self.client.post(self.list_url, {"name": "Apollo"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Project.objects.filter(name="Apollo").count(), 1)

    def test_same_project_name_allowed_in_different_workspace(self):
        self.create_project("Apollo")
        other = Workspace.objects.create(name="Other", owner=self.member)
        self.client.force_authenticate(self.member)
        response = self.client.post(
            reverse("project-list", args=[other.id]), {"name": "Apollo"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_workspace_cannot_be_overridden_by_client(self):
        other = Workspace.objects.create(name="Other", owner=self.member)
        self.client.force_authenticate(self.member)
        response = self.client.post(
            self.list_url, {"name": "Apollo", "workspace": str(other.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Project.objects.get(id=response.data["id"]).workspace, self.workspace)

    def test_members_can_list_only_their_workspace_projects(self):
        self.create_project("Apollo")
        other = Workspace.objects.create(name="Other", owner=self.outsider)
        Project.objects.create(workspace=other, name="Hidden", created_by=self.outsider)

        self.client.force_authenticate(self.viewer)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [project["name"] for project in response.data]
        self.assertEqual(names, ["Apollo"])

    def test_viewer_can_retrieve_but_not_edit_project(self):
        project = self.create_project()
        self.client.force_authenticate(self.viewer)
        self.assertEqual(
            self.client.get(self.detail_url(project)).status_code, status.HTTP_200_OK
        )
        response = self.client.patch(
            self.detail_url(project), {"name": "Renamed"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_member_can_update_project(self):
        project = self.create_project()
        self.client.force_authenticate(self.member)
        response = self.client.patch(
            self.detail_url(project), {"description": "Updated"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        project.refresh_from_db()
        self.assertEqual(project.description, "Updated")

    def test_only_owner_or_admin_can_delete_project(self):
        project = self.create_project()
        self.client.force_authenticate(self.member)
        self.assertEqual(
            self.client.delete(self.detail_url(project)).status_code,
            status.HTTP_403_FORBIDDEN,
        )

        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.delete(self.detail_url(project)).status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(Project.objects.filter(id=project.id).exists())

    def test_project_from_another_workspace_is_not_reachable(self):
        other = Workspace.objects.create(name="Other", owner=self.outsider)
        hidden = Project.objects.create(workspace=other, name="Hidden", created_by=self.outsider)

        self.client.force_authenticate(self.owner)
        response = self.client.get(reverse("project-detail", args=[self.workspace.id, hidden.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_deleting_workspace_cascades_to_projects(self):
        self.create_project()
        self.workspace.delete()
        self.assertEqual(Project.objects.count(), 0)
