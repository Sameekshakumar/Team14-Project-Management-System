import json
import logging
from datetime import datetime, timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

logger = logging.getLogger(__name__)


def publish_project_event(project_id, event_type, payload):
    """Broadcast a committed task change to the project's connected members."""
    safe_payload = json.loads(json.dumps(payload, cls=DjangoJSONEncoder))
    timestamp = datetime.now(timezone.utc).isoformat()

    def publish():
        try:
            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(
                    f"project_{project_id}",
                    {
                        "type": "project.event",
                        "event_type": event_type,
                        "payload": safe_payload,
                        "timestamp": timestamp,
                    },
                )
        except Exception:
            logger.exception("Could not publish %s for project %s", event_type, project_id)

    transaction.on_commit(publish)


def record_task_change(*, task, actor, created, previous=None, task_data=None):
    payload = {
        "task_id": str(task.pk),
        "actor": actor.pk,
        "task": task_data or {
            "id": str(task.pk),
            "title": task.title,
            "status": task.status,
            "assignee": task.assignee_id,
        },
    }
    if previous:
        current = {
            "title": task.title,
            "status": task.status,
            "assignee_id": task.assignee_id,
        }
        payload["changed"] = [key for key, value in current.items() if previous.get(key) != value]
    payload["task_id"] = str(task.pk)
    publish_project_event(task.project_id, "task_created" if created else "task_updated", payload)


def record_task_deletion(*, task, actor):
    publish_project_event(task.project_id, "task_deleted", {
        "task_id": str(task.pk), "actor": actor.pk, "title": task.title,
    })
