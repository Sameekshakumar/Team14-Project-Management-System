from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Workspace, WorkspaceMembership

from .models import Project, Task

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


class TaskTests(APITestCase):
    """FR-TASK-02: task creation, subtasks and assignment to one member."""

    def setUp(self):
        self.owner = User.objects.create_user(email="t-owner@team14.test", password="StrongPass!234")
        self.member = User.objects.create_user(email="t-member@team14.test", password="StrongPass!234")
        self.viewer = User.objects.create_user(email="t-viewer@team14.test", password="StrongPass!234")
        self.outsider = User.objects.create_user(email="t-outsider@team14.test", password="StrongPass!234")

        self.workspace = Workspace.objects.create(name="Team 14", owner=self.owner)
        for user, role in [(self.member, "Member"), (self.viewer, "Viewer")]:
            WorkspaceMembership.objects.update_or_create(
                workspace=self.workspace, user=user, defaults={"role": role}
            )
        self.project = Project.objects.create(
            workspace=self.workspace, name="Apollo", created_by=self.owner
        )
        self.list_url = reverse("task-list", args=[self.project.id])

    def detail_url(self, task):
        return reverse("task-detail", args=[task.id])

    def make_task(self, title="Build login", **kwargs):
        kwargs.setdefault("created_by", self.owner)
        return Task.objects.create(project=self.project, title=title, **kwargs)

    def test_unauthenticated_user_cannot_create_task(self):
        response = self.client.post(self.list_url, {"title": "Build login"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_member_can_create_task_with_default_status(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(
            self.list_url, {"title": "Build login", "description": "JWT"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Task.STATUS_TODO)
        self.assertEqual(response.data["created_by"], self.member.id)
        self.assertEqual(response.data["parent"], None)
        self.assertEqual(Task.objects.get(id=response.data["id"]).project, self.project)

    def test_task_title_is_required_and_trimmed(self):
        self.client.force_authenticate(self.member)
        for bad_title in ["", "   "]:
            response = self.client.post(self.list_url, {"title": bad_title}, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        response = self.client.post(self.list_url, {"title": "  Build login  "}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "Build login")

    def test_viewer_cannot_create_task(self):
        self.client.force_authenticate(self.viewer)
        response = self.client.post(self.list_url, {"title": "Build login"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Task.objects.count(), 0)

    def test_non_member_cannot_create_or_list_tasks(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(
            self.client.post(self.list_url, {"title": "X"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_403_FORBIDDEN)

    def test_task_can_be_assigned_to_a_workspace_member(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            self.list_url, {"title": "Build login", "assignee": self.member.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["assignee"], self.member.id)
        self.assertEqual(response.data["assignee_email"], self.member.email)

    def test_task_cannot_be_assigned_to_a_non_member(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(
            self.list_url, {"title": "Build login", "assignee": self.outsider.id}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("assignee", response.data)
        self.assertEqual(Task.objects.count(), 0)

    def test_assignee_can_be_cleared(self):
        task = self.make_task(assignee=self.member)
        self.client.force_authenticate(self.owner)
        response = self.client.patch(self.detail_url(task), {"assignee": None}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertIsNone(task.assignee)

    def test_subtask_can_be_created_under_a_task(self):
        parent = self.make_task("Parent task")
        self.client.force_authenticate(self.member)
        response = self.client.post(
            self.list_url, {"title": "Subtask A", "parent": str(parent.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["parent"], parent.id)
        self.assertEqual(parent.subtasks.count(), 1)

    def test_parent_task_exposes_its_subtasks(self):
        parent = self.make_task("Parent task")
        self.make_task("Subtask A", parent=parent, assignee=self.member)
        self.client.force_authenticate(self.member)
        response = self.client.get(self.detail_url(parent))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([s["title"] for s in response.data["subtasks"]], ["Subtask A"])

    def test_subtasks_cannot_be_nested_more_than_one_level(self):
        parent = self.make_task("Parent task")
        subtask = self.make_task("Subtask A", parent=parent)
        self.client.force_authenticate(self.member)
        response = self.client.post(
            self.list_url, {"title": "Too deep", "parent": str(subtask.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent", response.data)

    def test_parent_must_belong_to_the_same_project(self):
        other_project = Project.objects.create(
            workspace=self.workspace, name="Zeus", created_by=self.owner
        )
        foreign_parent = Task.objects.create(
            project=other_project, title="Elsewhere", created_by=self.owner
        )
        self.client.force_authenticate(self.member)
        response = self.client.post(
            self.list_url, {"title": "Subtask", "parent": str(foreign_parent.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("parent", response.data)

    def test_task_cannot_become_its_own_parent(self):
        task = self.make_task()
        self.client.force_authenticate(self.member)
        response = self.client.patch(
            self.detail_url(task), {"parent": str(task.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_task_with_subtasks_cannot_become_a_subtask(self):
        parent = self.make_task("Parent task")
        self.make_task("Subtask A", parent=parent)
        sibling = self.make_task("Sibling")
        self.client.force_authenticate(self.member)
        response = self.client.patch(
            self.detail_url(parent), {"parent": str(sibling.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deleting_parent_deletes_its_subtasks(self):
        parent = self.make_task("Parent task")
        self.make_task("Subtask A", parent=parent)
        self.client.force_authenticate(self.owner)
        response = self.client.delete(self.detail_url(parent))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Task.objects.count(), 0)

    def test_invalid_status_is_rejected(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(
            self.list_url, {"title": "Build login", "status": "Shipped"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_all_srs_statuses_are_accepted(self):
        self.client.force_authenticate(self.member)
        for value in ["Backlog", "To Do", "In Progress", "Done"]:
            response = self.client.post(
                self.list_url, {"title": f"Task {value}", "status": value}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(response.data["status"], value)

    def test_project_cannot_be_overridden_by_client(self):
        other_project = Project.objects.create(
            workspace=self.workspace, name="Zeus", created_by=self.owner
        )
        self.client.force_authenticate(self.member)
        response = self.client.post(
            self.list_url,
            {"title": "Build login", "project": str(other_project.id)},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Task.objects.get(id=response.data["id"]).project, self.project)

    def test_list_returns_only_tasks_of_the_requested_project(self):
        self.make_task("Mine")
        other_project = Project.objects.create(
            workspace=self.workspace, name="Zeus", created_by=self.owner
        )
        Task.objects.create(project=other_project, title="Theirs", created_by=self.owner)

        self.client.force_authenticate(self.viewer)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([t["title"] for t in response.data], ["Mine"])

    def test_viewer_can_read_but_not_edit_or_delete_task(self):
        task = self.make_task()
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(self.detail_url(task)).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.patch(self.detail_url(task), {"title": "Nope"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.delete(self.detail_url(task)).status_code, status.HTTP_403_FORBIDDEN
        )

    def test_non_member_cannot_read_or_edit_task_from_another_workspace(self):
        task = self.make_task()
        self.client.force_authenticate(self.outsider)
        self.assertEqual(
            self.client.get(self.detail_url(task)).status_code, status.HTTP_403_FORBIDDEN
        )
        self.assertEqual(
            self.client.patch(self.detail_url(task), {"title": "Nope"}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_member_can_update_task_status_and_title(self):
        task = self.make_task()
        self.client.force_authenticate(self.member)
        response = self.client.patch(
            self.detail_url(task),
            {"title": "Build login v2", "status": Task.STATUS_IN_PROGRESS},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.title, "Build login v2")
        self.assertEqual(task.status, Task.STATUS_IN_PROGRESS)

    def test_deleting_project_cascades_to_tasks(self):
        self.make_task()
        self.project.delete()
        self.assertEqual(Task.objects.count(), 0)
