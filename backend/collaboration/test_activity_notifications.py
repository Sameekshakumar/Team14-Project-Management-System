from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken
from channels.testing import WebsocketCommunicator

from accounts.models import Workspace, WorkspaceMembership
from config.asgi import application
from projects.models import Project, Task

from .models import ActivityEvent, Notification

User = get_user_model()


class ActivityNotificationApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@activity.test", password="StrongPass!234")
        self.member = User.objects.create_user(email="member@activity.test", password="StrongPass!234")
        self.outsider = User.objects.create_user(email="outsider@activity.test", password="StrongPass!234")
        self.workspace = Workspace.objects.create(name="Activity", owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.member)
        self.project = Project.objects.create(workspace=self.workspace, name="Activity")
        self.task = Task.objects.create(project=self.project, title="Task", created_by=self.owner)
        self.client.force_authenticate(self.owner)

    def test_assignment_activity_and_notification_skip_actor(self):
        response = self.client.patch(
            f"/api/tasks/{self.task.pk}/", {"assignee": self.member.pk}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ActivityEvent.objects.filter(verb="task_assigned", task=self.task).exists())
        notification = Notification.objects.get(kind="assignment")
        self.assertEqual(notification.recipient_id, self.member.pk)
        self.assertFalse(Notification.objects.filter(recipient=self.owner).exists())

    def test_comment_notifications_and_private_read_marking(self):
        self.client.force_authenticate(self.member)
        response = self.client.post(
            f"/api/tasks/{self.task.pk}/comments/",
            {"body": "A comment for @owner@activity.test"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        notification = Notification.objects.get(kind="comment")
        self.assertEqual(notification.recipient_id, self.owner.pk)
        self.assertTrue(ActivityEvent.objects.filter(verb="comment_added", task=self.task).exists())
        self.assertTrue(ActivityEvent.objects.filter(verb="user_mentioned", task=self.task).exists())
        self.assertTrue(Notification.objects.filter(kind="mention", recipient=self.owner).exists())
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get("/api/notifications/").data["count"], 0)
        self.assertEqual(self.client.post(f"/api/notifications/{notification.pk}/read/").status_code, 404)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f"/api/notifications/{notification.pk}/read/").status_code, 200)
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data["count"], 1)
        self.assertEqual(self.client.post("/api/notifications/read-all/").status_code, 200)
        self.assertEqual(self.client.get("/api/notifications/unread-count/").data["count"], 0)

    def test_activity_is_member_scoped_filterable_and_paginated(self):
        for index in range(3):
            ActivityEvent.objects.create(
                project=self.project, actor=self.owner, task=self.task,
                verb="task_updated", target_type="task", target_id=str(self.task.pk),
                metadata={"index": index},
            )
        url = f"/api/projects/{self.project.pk}/activity/?type=task_updated&page_size=1"
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.data["count"], 3)
        self.assertIsNotNone(page.data["next"])
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 403)


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class NotificationSocketTests(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="member@notify.test", password="StrongPass!234")

    async def test_private_notification_socket_receives_only_recipient_events(self):
        token = str(AccessToken.for_user(self.user))
        socket = WebsocketCommunicator(
            application, "/ws/notifications/", subprotocols=["t14", f"bearer.{token}"]
        )
        connected, _ = await socket.connect()
        self.assertTrue(connected)
        try:
            from channels.layers import get_channel_layer
            await get_channel_layer().group_send(
                f"user_{self.user.pk}",
                {"type": "user.event", "event_type": "notification", "payload": {"id": 1}},
            )
            message = await socket.receive_json_from(timeout=1)
            self.assertEqual(message["type"], "notification")
            self.assertEqual(message["payload"]["id"], 1)
        finally:
            await socket.disconnect()
