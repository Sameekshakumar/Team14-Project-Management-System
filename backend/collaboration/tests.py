import asyncio
import json
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Workspace, WorkspaceMembership
from config.asgi import application
from projects.models import Project, Task

from .models import ActivityEvent, Notification


MEMORY_LAYER = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


@override_settings(CHANNEL_LAYERS=MEMORY_LAYER)
class CollaborationApiTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user = get_user_model()
        self.owner = user.objects.create_user(email="owner@example.com", password="valid-pass-123")
        self.member = user.objects.create_user(email="member@example.com", password="valid-pass-123")
        self.outsider = user.objects.create_user(email="outsider@example.com", password="valid-pass-123")
        self.workspace = Workspace.objects.create(name="Team", owner=self.owner)
        WorkspaceMembership.objects.create(workspace=self.workspace, user=self.member, role="Member")
        self.project = Project.objects.create(workspace=self.workspace, name="Delivery")
        self.task = Task.objects.create(project=self.project, title="Prepare release", created_by=self.owner)
        self.client = APIClient()
        self.client.force_authenticate(self.member)

    def test_mentions_are_member_only_deduplicated_and_html_is_removed(self):
        response = self.client.post(
            f"/api/tasks/{self.task.pk}/comments/",
            {"body": "<script>alert(1)</script> hi @member@example.com @member@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["body"], "alert(1) hi @member@example.com @member@example.com")
        self.assertEqual(len(response.data["mentioned_users"]), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 1)

        bad = self.client.post(
            f"/api/tasks/{self.task.pk}/comments/", {"body": "hi @outsider@example.com"}, format="json"
        )
        self.assertEqual(bad.status_code, 400)

    def test_non_member_cannot_read_comments_or_analytics(self):
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f"/api/tasks/{self.task.pk}/comments/").status_code, 403)
        self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/analytics/").status_code, 403)

    def test_comment_edit_and_delete_are_limited_to_author_or_workspace_admin(self):
        colleague = get_user_model().objects.create_user(email="colleague@example.com", password="valid-pass-123")
        WorkspaceMembership.objects.create(workspace=self.workspace, user=colleague, role="Member")
        created = self.client.post(
            f"/api/tasks/{self.task.pk}/comments/", {"body": "original"}, format="json"
        )
        comment_id = created.data["id"]
        self.client.force_authenticate(colleague)
        denied = self.client.patch(
            f"/api/tasks/{self.task.pk}/comments/{comment_id}/", {"body": "changed"}, format="json"
        )
        self.assertEqual(denied.status_code, 403)
        self.client.force_authenticate(self.owner)
        edited = self.client.patch(
            f"/api/tasks/{self.task.pk}/comments/{comment_id}/", {"body": "changed"}, format="json"
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.data["body"], "changed")

    def test_only_notification_recipient_can_read_it_and_actor_is_not_notified(self):
        self.client.post(f"/api/tasks/{self.task.pk}/comments/", {"body": "hello"}, format="json")
        note = Notification.objects.get()
        self.assertEqual(note.recipient_id, self.owner.pk)
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.post(f"/api/notifications/{note.pk}/read/").status_code, 404)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.post(f"/api/notifications/{note.pk}/read/").status_code, 200)
        self.assertEqual(Notification.objects.filter(recipient=self.member).count(), 0)

    def test_analytics_aggregates_and_activity_is_paginated(self):
        Task.objects.create(project=self.project, title="Done", status=Task.STATUS_DONE, created_by=self.owner)
        analytics = self.client.get(f"/api/projects/{self.project.pk}/analytics/")
        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(analytics.data["total_tasks"], 2)
        self.assertEqual(analytics.data["completed_tasks"], 1)
        self.assertEqual(analytics.data["completion_percent"], 50)
        for _ in range(27):
            ActivityEvent.objects.create(project=self.project, actor=self.owner, event_type="task_updated")
        feed = self.client.get(f"/api/projects/{self.project.pk}/activity/")
        self.assertEqual(feed.status_code, 200)
        self.assertEqual(feed.data["count"], 27)
        self.assertIsNotNone(feed.data["next"])


@override_settings(CHANNEL_LAYERS=MEMORY_LAYER)
class CollaborationWebSocketTests(TransactionTestCase):
    def setUp(self):
        user = get_user_model()
        self.member = user.objects.create_user(email="member@example.com", password="valid-pass-123")
        self.outsider = user.objects.create_user(email="outsider@example.com", password="valid-pass-123")
        self.workspace = Workspace.objects.create(name="Team", owner=self.member)
        self.project = Project.objects.create(workspace=self.workspace, name="Delivery")

    def communicator(self, token):
        protocols = [f"bearer.{token}"] if token else []
        return WebsocketCommunicator(application, f"/ws/projects/{self.project.pk}/board/", subprotocols=protocols)

    def test_rejects_missing_token_and_non_member(self):
        async def check():
            missing = self.communicator(None)
            connected, _ = await missing.connect()
            self.assertFalse(connected)
            outsider = self.communicator(str(AccessToken.for_user(self.outsider)))
            connected, _ = await outsider.connect()
            self.assertFalse(connected)
        async_to_sync(check)()

    def test_task_update_is_broadcast_to_project_members(self):
        task = Task.objects.create(project=self.project, title="Initial", created_by=self.member)
        async def check():
            socket = self.communicator(str(AccessToken.for_user(self.member)))
            connected, _ = await socket.connect()
            self.assertTrue(connected)
            client = APIClient()
            client.force_authenticate(self.member)
            response = await database_sync_to_async(client.patch)(
                f"/api/tasks/{task.pk}/", {"title": "Updated"}, format="json"
            )
            self.assertEqual(response.status_code, 200)
            event = await asyncio.wait_for(socket.receive_json_from(), timeout=2)
            while event["type"] != "task_updated":
                event = await asyncio.wait_for(socket.receive_json_from(), timeout=2)
            self.assertEqual(event["payload"]["task"]["title"], "Updated")
            await socket.disconnect()
        async_to_sync(check)()

    def test_ping_pong_and_reconnect_leave_a_single_live_subscription(self):
        task = Task.objects.create(project=self.project, title="Initial", created_by=self.member)
        async def check():
            token = str(AccessToken.for_user(self.member))
            client = APIClient()
            client.force_authenticate(self.member)
            first = self.communicator(token)
            connected, _ = await first.connect()
            self.assertTrue(connected)
            await first.send_json_to({"type": "ping"})
            self.assertEqual((await first.receive_json_from())["type"], "pong")
            await first.disconnect()

            saved = await database_sync_to_async(client.patch)(
                f"/api/tasks/{task.pk}/", {"title": "Saved while offline"}, format="json"
            )
            self.assertEqual(saved.status_code, 200)

            second = self.communicator(token)
            connected, _ = await second.connect()
            self.assertTrue(connected)
            snapshot = await database_sync_to_async(client.get)(f"/api/tasks/{task.pk}/")
            self.assertEqual(snapshot.data["title"], "Saved while offline")
            await get_channel_layer().group_send(
                f"project_{self.project.pk}",
                {"type": "project.event", "event_type": "task_updated", "payload": {"task_id": "saved"}},
            )
            event = await asyncio.wait_for(second.receive_json_from(), timeout=2)
            self.assertEqual(event["payload"]["task_id"], "saved")
            self.assertTrue(await second.receive_nothing(timeout=0.05))
            await second.disconnect()
        async_to_sync(check)()

    def test_comment_creation_is_broadcast_to_project(self):
        task = Task.objects.create(project=self.project, title="Task", created_by=self.member)
        async def check():
            socket = self.communicator(str(AccessToken.for_user(self.member)))
            connected, _ = await socket.connect()
            self.assertTrue(connected)
            client = APIClient()
            client.force_authenticate(self.member)
            response = await database_sync_to_async(client.post)(
                f"/api/tasks/{task.pk}/comments/", {"body": "hello"}, format="json"
            )
            self.assertEqual(response.status_code, 201)
            event = await asyncio.wait_for(socket.receive_json_from(), timeout=2)
            while event["type"] != "comment_created":
                event = await asyncio.wait_for(socket.receive_json_from(), timeout=2)
            self.assertEqual(event["payload"]["comment"]["body"], "hello")
            await socket.disconnect()
        async_to_sync(check)()
