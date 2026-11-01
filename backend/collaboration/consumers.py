import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from accounts.models import WorkspaceMembership
from projects.models import Project

logger = logging.getLogger(__name__)


class ProjectConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.project_id = self.scope["url_route"]["kwargs"]["project_id"]
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        if not await self.is_project_member(user.pk, self.project_id):
            await self.close(code=4403)
            return
        self.group_name = f"project_{self.project_id}"
        try:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept(subprotocol="t14")
        except Exception:
            logger.exception("Could not join project WebSocket group %s", self.project_id)
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            except Exception:
                logger.warning("Could not clean up failed WebSocket group join", exc_info=True)
            await self.close(code=1013)

    async def disconnect(self, close_code):
        group_name = getattr(self, "group_name", None)
        if group_name:
            try:
                await self.channel_layer.group_discard(group_name, self.channel_name)
            except Exception:
                logger.warning("Could not remove project WebSocket group membership", exc_info=True)

    async def project_event(self, event):
        payload = event["payload"]
        await self.send_json({
            "type": event["event_type"],
            "task_id": payload.get("task_id"),
            "actor": payload.get("actor"),
            "payload": payload,
            "timestamp": event["timestamp"],
        })

    @database_sync_to_async
    def is_project_member(self, user_id, project_id):
        try:
            project = Project.objects.select_related("workspace").get(pk=project_id)
        except Project.DoesNotExist:
            return False
        return project.workspace.owner_id == user_id or WorkspaceMembership.objects.filter(
            workspace=project.workspace, user_id=user_id
        ).exists()
