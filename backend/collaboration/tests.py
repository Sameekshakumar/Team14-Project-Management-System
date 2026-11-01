from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Workspace, WorkspaceMembership
from config.asgi import application
from projects.models import Project, Task

from .services import record_task_change

User = get_user_model()


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
})
class ProjectSocketTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@socket.test", password="StrongPass!234")
        self.member = User.objects.create_user(email="member@socket.test", password="StrongPass!234")
        self.outsider = User.objects.create_user(email="outsider@socket.test", password="StrongPass!234")
        self.workspace = Workspace.objects.create(name="Socket workspace", owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.member)
        self.project = Project.objects.create(workspace=self.workspace, name="Socket project")
        self.task = Task.objects.create(project=self.project, title="Original task", created_by=self.owner)
        self.path = f"/ws/projects/{self.project.pk}/board/"

    def communicator(self, user=None):
        protocols = ["t14"]
        if user is not None:
            protocols.append(f"bearer.{AccessToken.for_user(user)}")
        return WebsocketCommunicator(application, self.path, subprotocols=protocols)

    @database_sync_to_async
    def update_task(self):
        self.task.status = Task.STATUS_IN_PROGRESS
        self.task.save(update_fields=["status", "updated_at"])
        record_task_change(
            task=self.task,
            actor=self.owner,
            created=False,
            previous={"status": Task.STATUS_TODO},
            task_data={"id": str(self.task.pk), "status": Task.STATUS_IN_PROGRESS},
        )

    async def test_rejects_unauthenticated_connection(self):
        communicator = self.communicator()
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def test_rejects_non_member_connection(self):
        communicator = self.communicator(self.outsider)
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

    async def test_task_update_is_broadcast_to_project_member(self):
        communicator = self.communicator(self.member)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        try:
            await self.update_task()
            message = await communicator.receive_json_from(timeout=1)
            self.assertEqual(message["type"], "task_updated")
            self.assertEqual(message["task_id"], str(self.task.pk))
            self.assertEqual(message["actor"], self.owner.pk)
            self.assertEqual(message["payload"]["task"]["status"], Task.STATUS_IN_PROGRESS)
            self.assertTrue(message["timestamp"])
        finally:
            await communicator.disconnect()
