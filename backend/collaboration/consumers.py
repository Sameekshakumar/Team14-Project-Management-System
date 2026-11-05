import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone
from django.conf import settings
from redis.asyncio import Redis

from accounts.models import WorkspaceMembership
from projects.models import Project

logger = logging.getLogger(__name__)


class ConnectionQuotaMixin:
    """Bound live sockets using Redis leases shared by all ASGI workers."""

    async def reserve_connection(self, user_id, project_id=None):
        # In-memory channels are intended for single-process development and
        # tests; production Redis deployments enforce the shared limits.
        if settings.CHANNEL_LAYER_BACKEND == "memory":
            return True
        self._quota_redis = Redis.from_url(settings.CHANNEL_REDIS_URL, decode_responses=True)
        now = await self._quota_redis.time()
        now_seconds = int(now[0])
        lease_until = now_seconds + settings.WS_CONNECTION_LEASE_SECONDS
        channel_name = self.channel_name
        keys = []
        limits = []
        if project_id is not None:
            keys.append(f"ws:quota:project:{project_id}")
            limits.append(settings.WS_MAX_CONNECTIONS_PER_PROJECT)
        keys.append(f"ws:quota:user:{user_id}")
        limits.append(settings.WS_MAX_CONNECTIONS_PER_USER)

        # Check both scopes and reserve atomically so simultaneous connects
        # cannot overshoot either limit.
        script = """
        local now = tonumber(ARGV[1])
        local expires = tonumber(ARGV[2])
        local member = ARGV[3]
        for i, key in ipairs(KEYS) do
            redis.call('ZREMRANGEBYSCORE', key, '-inf', now)
            if redis.call('ZCARD', key) >= tonumber(ARGV[3 + i]) then
                return 0
            end
        end
        for _, key in ipairs(KEYS) do
            redis.call('ZADD', key, expires, member)
            redis.call('EXPIRE', key, expires - now)
        end
        return 1
        """
        args = [now_seconds, lease_until, channel_name, *limits]
        reserved = await self._quota_redis.eval(script, len(keys), *keys, *args)
        if not reserved:
            await self._quota_redis.aclose()
            self._quota_redis = None
            return False
        self._quota_keys = keys
        return True

    async def refresh_connection_lease(self):
        client = getattr(self, "_quota_redis", None)
        if not client:
            return True
        now = int((await client.time())[0])
        expires = now + settings.WS_CONNECTION_LEASE_SECONDS
        pipe = client.pipeline()
        for key in self._quota_keys:
            pipe.zadd(key, {self.channel_name: expires})
            pipe.expire(key, settings.WS_CONNECTION_LEASE_SECONDS)
        await pipe.execute()
        return True

    async def release_connection(self):
        client = getattr(self, "_quota_redis", None)
        if client:
            try:
                if getattr(self, "_quota_keys", None):
                    pipe = client.pipeline()
                    for key in self._quota_keys:
                        pipe.zrem(key, self.channel_name)
                    await pipe.execute()
            finally:
                await client.aclose()
                self._quota_redis = None


class ProjectConsumer(ConnectionQuotaMixin, AsyncJsonWebsocketConsumer):
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
            if not await self.reserve_connection(user.pk, self.project_id):
                await self.close(code=4429)
                return
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept(subprotocol="t14")
        except Exception:
            logger.exception("Could not join project WebSocket group %s", self.project_id)
            await self.release_connection()
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            except Exception:
                logger.warning("Could not clean up failed WebSocket group join", exc_info=True)
            await self.close(code=1013)

    async def disconnect(self, close_code):
        await self.release_connection()
        group_name = getattr(self, "group_name", None)
        if group_name:
            try:
                await self.channel_layer.group_discard(group_name, self.channel_name)
            except Exception:
                logger.warning("Could not remove project WebSocket group membership", exc_info=True)

    async def receive_json(self, content, **kwargs):
        if isinstance(content, dict) and content.get("type") == "ping":
            try:
                await self.refresh_connection_lease()
                await self.send_json({"type": "pong", "timestamp": timezone.now().isoformat()})
            except Exception:
                logger.exception("Could not refresh project WebSocket lease")
                await self.close(code=1013)

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
