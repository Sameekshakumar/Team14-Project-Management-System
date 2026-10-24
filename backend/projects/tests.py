from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Workspace, WorkspaceMembership

from .models import Project, Task, TaskDependency

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

    def test_assignee_email_is_null_rather_than_missing_when_unassigned(self):
        """The field must always be present so clients see one response shape."""
        task = self.make_task()
        self.client.force_authenticate(self.member)
        response = self.client.get(self.detail_url(task))
        self.assertIn("assignee_email", response.data)
        self.assertIsNone(response.data["assignee_email"])

    def test_deleting_project_cascades_to_tasks(self):
        self.make_task()
        self.project.delete()
        self.assertEqual(Task.objects.count(), 0)


class TaskDependencyTests(APITestCase):
    """FR-TASK-04 plus the SRS 6.5 rule on completing blocked tasks."""

    def setUp(self):
        self.owner = User.objects.create_user(email="d-owner@team14.test", password="StrongPass!234")
        self.member = User.objects.create_user(email="d-member@team14.test", password="StrongPass!234")
        self.viewer = User.objects.create_user(email="d-viewer@team14.test", password="StrongPass!234")
        self.outsider = User.objects.create_user(email="d-outsider@team14.test", password="StrongPass!234")

        self.workspace = Workspace.objects.create(name="Team 14", owner=self.owner)
        for user, role in [(self.member, "Member"), (self.viewer, "Viewer")]:
            WorkspaceMembership.objects.update_or_create(
                workspace=self.workspace, user=user, defaults={"role": role}
            )
        self.project = Project.objects.create(
            workspace=self.workspace, name="Apollo", created_by=self.owner
        )
        self.a = self.make_task("Task A")
        self.b = self.make_task("Task B")
        self.c = self.make_task("Task C")

    def make_task(self, title, **kwargs):
        return Task.objects.create(
            project=self.project, title=title, created_by=self.owner, **kwargs
        )

    def dep_url(self, task):
        return reverse("task-dependency-list", args=[task.id])

    def add_dependency(self, task, depends_on, user=None):
        self.client.force_authenticate(user or self.member)
        return self.client.post(
            self.dep_url(task), {"depends_on": str(depends_on.id)}, format="json"
        )

    def link(self, task, depends_on):
        return TaskDependency.objects.create(task=task, depends_on=depends_on)

    # --- creating dependencies -------------------------------------------

    def test_member_can_define_a_dependency_between_two_tasks(self):
        response = self.add_dependency(self.b, self.a)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["depends_on"], self.a.id)
        self.assertEqual(response.data["depends_on_title"], "Task A")
        self.assertTrue(TaskDependency.objects.filter(task=self.b, depends_on=self.a).exists())

    def test_unauthenticated_user_cannot_define_a_dependency(self):
        response = self.client.post(
            self.dep_url(self.b), {"depends_on": str(self.a.id)}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_viewer_cannot_define_or_delete_a_dependency(self):
        response = self.add_dependency(self.b, self.a, user=self.viewer)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        dependency = self.link(self.b, self.a)
        self.client.force_authenticate(self.viewer)
        response = self.client.delete(
            reverse("task-dependency-detail", args=[self.b.id, dependency.id])
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_member_cannot_define_or_list_dependencies(self):
        self.assertEqual(
            self.add_dependency(self.b, self.a, user=self.outsider).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.dep_url(self.b)).status_code, status.HTTP_403_FORBIDDEN)

    def test_dependency_can_be_listed_and_deleted(self):
        dependency = self.link(self.b, self.a)
        self.client.force_authenticate(self.member)

        response = self.client.get(self.dep_url(self.b))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([d["depends_on"] for d in response.data], [self.a.id])

        response = self.client.delete(
            reverse("task-dependency-detail", args=[self.b.id, dependency.id])
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(TaskDependency.objects.count(), 0)

    def test_duplicate_dependency_is_rejected(self):
        self.link(self.b, self.a)
        response = self.add_dependency(self.b, self.a)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(TaskDependency.objects.count(), 1)

    def test_dependency_must_be_within_the_same_project(self):
        other_project = Project.objects.create(
            workspace=self.workspace, name="Zeus", created_by=self.owner
        )
        foreign = Task.objects.create(
            project=other_project, title="Elsewhere", created_by=self.owner
        )
        response = self.add_dependency(self.b, foreign)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(TaskDependency.objects.count(), 0)

    # --- cycle detection (FR-TASK-04 negative tests) ---------------------

    def test_self_dependency_is_rejected(self):
        response = self.add_dependency(self.a, self.a)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(TaskDependency.objects.count(), 0)

    def test_direct_two_task_cycle_is_rejected(self):
        self.assertEqual(self.add_dependency(self.b, self.a).status_code, status.HTTP_201_CREATED)
        response = self.add_dependency(self.a, self.b)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("circular", str(response.data).lower())
        self.assertEqual(TaskDependency.objects.count(), 1)

    def test_indirect_three_task_cycle_is_rejected(self):
        # C -> B -> A, then A -> C would close the loop.
        self.link(self.c, self.b)
        self.link(self.b, self.a)
        response = self.add_dependency(self.a, self.c)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("circular", str(response.data).lower())
        self.assertEqual(TaskDependency.objects.count(), 2)

    def test_long_chain_cycle_is_rejected(self):
        chain = [self.make_task(f"Chain {i}") for i in range(6)]
        for upstream, downstream in zip(chain, chain[1:]):
            self.link(downstream, upstream)
        response = self.add_dependency(chain[0], chain[-1])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("circular", str(response.data).lower())

    def test_diamond_dependency_is_allowed(self):
        # B and C both depend on A; D depends on both. No cycle.
        d = self.make_task("Task D")
        self.link(self.b, self.a)
        self.link(self.c, self.a)
        self.assertEqual(self.add_dependency(d, self.b).status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.add_dependency(d, self.c).status_code, status.HTTP_201_CREATED)
        self.assertEqual(TaskDependency.objects.count(), 4)

    def test_shared_prerequisite_is_not_mistaken_for_a_cycle(self):
        self.link(self.b, self.a)
        self.link(self.c, self.a)
        self.assertEqual(self.add_dependency(self.c, self.b).status_code, status.HTTP_201_CREATED)

    # --- SRS 6.5: completing a blocked task ------------------------------

    def test_task_cannot_be_marked_done_while_a_dependency_is_incomplete(self):
        self.link(self.b, self.a)
        self.client.force_authenticate(self.member)
        response = self.client.patch(
            reverse("task-detail", args=[self.b.id]), {"status": "Done"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Task A", str(response.data))
        self.b.refresh_from_db()
        self.assertNotEqual(self.b.status, Task.STATUS_DONE)

    def test_task_can_be_marked_done_once_dependencies_are_done(self):
        self.link(self.b, self.a)
        self.a.status = Task.STATUS_DONE
        self.a.save(update_fields=["status"])

        self.client.force_authenticate(self.member)
        response = self.client.patch(
            reverse("task-detail", args=[self.b.id]), {"status": "Done"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, Task.STATUS_DONE)

    def test_blocked_task_can_still_move_to_other_columns(self):
        self.link(self.b, self.a)
        self.client.force_authenticate(self.member)
        response = self.client.patch(
            reverse("task-detail", args=[self.b.id]),
            {"status": Task.STATUS_IN_PROGRESS},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_task_exposes_blocked_state_and_prerequisites(self):
        self.link(self.b, self.a)
        self.client.force_authenticate(self.member)

        response = self.client.get(reverse("task-detail", args=[self.b.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_blocked"])
        self.assertEqual(response.data["depends_on"], [self.a.id])

        response = self.client.get(reverse("task-detail", args=[self.a.id]))
        self.assertFalse(response.data["is_blocked"])
        self.assertEqual(response.data["depends_on"], [])

    def test_unblocked_once_prerequisite_is_done(self):
        self.link(self.b, self.a)
        self.a.status = Task.STATUS_DONE
        self.a.save(update_fields=["status"])
        self.client.force_authenticate(self.member)
        response = self.client.get(reverse("task-detail", args=[self.b.id]))
        self.assertFalse(response.data["is_blocked"])

    def test_deleting_a_task_removes_its_dependency_edges(self):
        self.link(self.b, self.a)
        self.link(self.c, self.a)
        self.a.delete()
        self.assertEqual(TaskDependency.objects.count(), 0)

    def test_self_dependency_is_blocked_at_database_level(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TaskDependency.objects.create(task=self.a, depends_on=self.a)


class TaskFlowScreenCountTests(APITestCase):
    """
    NFR-003: a new user shall be able to create and assign a task in no more
    than 4 primary screens.

    The UI reaches it in three (frontend/src/App.jsx):

        1. Sign in / register   -> AuthScreen
        2. Workspace & project  -> Dashboard
        3. Task board           -> Board (create and assign inline)

    These tests walk the API calls each of those screens makes, in order, with
    no extra round trips, so the claim stays checkable if the flow is ever
    reshuffled.
    """

    MAX_SCREENS = 4

    def test_new_user_creates_and_assigns_a_task_within_the_screen_budget(self):
        screens = 0

        # Screen 1 - register, which returns tokens directly so no separate
        # login step is needed.
        screens += 1
        response = self.client.post(
            "/api/auth/register/",
            {"email": "nfr-new@team14.test", "password": "StrongPass!234"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

        # Screen 2 - the dashboard creates a workspace and a project together.
        screens += 1
        response = self.client.post("/api/auth/workspaces/", {"name": "Team 14"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        workspace_id = response.data["id"]

        response = self.client.post(
            f"/api/workspaces/{workspace_id}/projects/", {"name": "Apollo"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project_id = response.data["id"]

        # Screen 3 - the board loads its members for the assignee picker, then
        # creates and assigns the task in a single submit.
        screens += 1
        members = self.client.get(f"/api/auth/workspaces/{workspace_id}/members/")
        self.assertEqual(members.status_code, status.HTTP_200_OK)
        self.assertTrue(members.data, "The board needs at least one assignable member.")

        response = self.client.post(
            f"/api/projects/{project_id}/tasks/",
            {"title": "Design the schema", "assignee": members.data[0]["user_id"]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["assignee"], members.data[0]["user_id"])

        self.assertLessEqual(screens, self.MAX_SCREENS)
        self.assertEqual(screens, 3, "The documented flow is three screens.")

    def test_creation_and_assignment_happen_in_one_request(self):
        """
        The task is assigned as it is created, so assignment never costs the
        user an extra screen.
        """
        owner = User.objects.create_user(email="nfr-owner@team14.test", password="StrongPass!234")
        workspace = Workspace.objects.create(name="Team 14", owner=owner)
        project = Project.objects.create(workspace=workspace, name="Apollo", created_by=owner)

        self.client.force_authenticate(owner)
        response = self.client.post(
            f"/api/projects/{project.id}/tasks/",
            {"title": "Design the schema", "assignee": owner.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["assignee"], owner.id)
        self.assertEqual(response.data["status"], Task.STATUS_TODO)

    def test_board_opens_without_a_separate_task_list_screen(self):
        """
        One request returns every card the board draws, so the board itself is
        a single screen rather than a list plus a detail view.
        """
        owner = User.objects.create_user(email="nfr-board@team14.test", password="StrongPass!234")
        workspace = Workspace.objects.create(name="Team 14", owner=owner)
        project = Project.objects.create(workspace=workspace, name="Apollo", created_by=owner)
        parent = Task.objects.create(project=project, title="Parent", created_by=owner)
        Task.objects.create(project=project, title="Child", parent=parent, created_by=owner)

        self.client.force_authenticate(owner)
        response = self.client.get(f"/api/projects/{project.id}/tasks/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        card = next(task for task in response.data if str(task["id"]) == str(parent.id))
        # Everything a card renders arrives with the list: status column,
        # assignee, subtasks and blocked state.
        for field in ["status", "assignee_email", "subtasks", "is_blocked"]:
            self.assertIn(field, card)
        self.assertEqual(len(card["subtasks"]), 1)
