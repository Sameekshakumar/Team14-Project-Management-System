from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken
from channels.testing import WebsocketCommunicator

from accounts.models import Workspace, WorkspaceMembership
from config.asgi import application
from projects.models import Project, Task

from .models import Mention

User = get_user_model()


class TaskCommentApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@comments.test", password="StrongPass!234")
        self.author = User.objects.create_user(email="author@comments.test", password="StrongPass!234")
        self.other = User.objects.create_user(email="other@comments.test", password="StrongPass!234")
        self.outsider = User.objects.create_user(email="outside@comments.test", password="StrongPass!234")
        self.workspace = Workspace.objects.create(name="Comments", owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.author)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.other)
        self.project = Project.objects.create(workspace=self.workspace, name="Comments")
        self.task = Task.objects.create(project=self.project, title="Task", created_by=self.owner)
        self.list_url = f"/api/tasks/{self.task.pk}/comments/"
        self.client.force_authenticate(self.author)

    def test_mentions_resolve_to_distinct_members_and_html_is_removed(self):
        response = self.client.post(self.list_url, {
            "body": "<script>alert(1)</script> hello @other@comments.test @other@comments.test"
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["body"], "alert(1) hello @other@comments.test @other@comments.test")
        self.assertEqual(len(response.data["mentioned_users"]), 1)
        self.assertEqual(Mention.objects.count(), 1)

    def test_nonmember_mentions_are_rejected_and_cannot_read_or_post(self):
        response = self.client.post(self.list_url, {"body": "Hi @outside@comments.test"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.list_url).status_code, 403)
        self.assertEqual(self.client.post(self.list_url, {"body": "No access"}, format="json").status_code, 403)

    def test_only_author_or_workspace_admin_can_edit_or_delete(self):
        created = self.client.post(self.list_url, {"body": "Original"}, format="json")
        detail = f"{self.list_url}{created.data['id']}/"
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.patch(detail, {"body": "Changed"}, format="json").status_code, 403)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.patch(detail, {"body": "Changed"}, format="json").status_code, 200)
        self.assertEqual(self.client.delete(detail).status_code, 204)


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TaskCommentSocketTests(TransactionTestCase):
    def setUp(self):
        self.member = User.objects.create_user(email="member@socket.test", password="StrongPass!234")
        self.workspace = Workspace.objects.create(name="Socket", owner=self.member)
        self.project = Project.objects.create(workspace=self.workspace, name="Socket")
        self.task = Task.objects.create(project=self.project, title="Task", created_by=self.member)

    async def test_comment_creation_is_broadcast_to_project_members(self):
        token = str(AccessToken.for_user(self.member))
        socket = WebsocketCommunicator(
            application,
            f"/ws/projects/{self.project.pk}/board/",
            subprotocols=["t14", f"bearer.{token}"],
        )
        connected, _ = await socket.connect()
        self.assertTrue(connected)
        try:
            client = APIClient()
            client.force_authenticate(self.member)
            from channels.db import database_sync_to_async
            response = await database_sync_to_async(client.post)(
                f"/api/tasks/{self.task.pk}/comments/", {"body": "hello"}, format="json"
            )
            self.assertEqual(response.status_code, 201)
            event = await socket.receive_json_from(timeout=2)
            self.assertEqual(event["type"], "comment_created")
            self.assertEqual(event["payload"]["comment"]["body"], "hello")
        finally:
            await socket.disconnect()
