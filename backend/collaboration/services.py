import json
import logging
from datetime import datetime, timezone

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction

from .models import ActivityEvent, Notification

logger = logging.getLogger(__name__)


def _json_safe(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def publish_project_event(project_id, event_type, payload):
    """Broadcast a committed task change to the project's connected members."""
    safe_payload = _json_safe(payload)
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


def publish_user_event(user_id, event_type, payload):
    safe_payload = _json_safe(payload)

    def publish():
        try:
            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(
                    f"user_{user_id}",
                    {"type": "user.event", "event_type": event_type, "payload": safe_payload},
                )
        except Exception:
            logger.exception("Could not publish %s to user %s", event_type, user_id)

    transaction.on_commit(publish)


def create_activity(*, project, actor, verb, target_type, target_id, task=None, metadata=None):
    activity = ActivityEvent.objects.create(
        project=project, actor=actor, task=task, verb=verb,
        target_type=target_type, target_id=str(target_id), metadata=metadata or {},
    )
    publish_project_event(project.pk, "activity_created", {
        "id": activity.pk, "verb": activity.verb, "actor": actor.pk if actor else None,
        "target_type": activity.target_type, "target_id": activity.target_id,
        "task_id": str(task.pk) if task else None, "metadata": activity.metadata,
        "created_at": activity.created_at.isoformat(),
    })
    return activity


def create_notification(*, recipient, activity, project, task, kind, message):
    if not recipient or (activity.actor_id and recipient.pk == activity.actor_id):
        return None
    notification, created = Notification.objects.get_or_create(
        recipient=recipient, activity=activity, kind=kind,
        defaults={"project": project, "task": task, "message": message},
    )
    if created:
        publish_user_event(recipient.pk, "notification", {
            "id": notification.pk, "kind": notification.kind,
            "message": notification.message, "project_id": str(project.pk),
            "task_id": str(task.pk) if task else None,
            "activity_id": activity.pk, "created_at": notification.created_at.isoformat(),
        })
    return notification


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
    event_types = ["task_created"] if created else ["task_updated"]
    if previous and previous.get("status") != task.status:
        event_types.append("task_moved")
    if previous and previous.get("assignee_id") != task.assignee_id:
        event_types.append("task_assigned")
    if created and task.assignee_id:
        event_types.append("task_assigned")
    for event_type in event_types:
        activity = create_activity(
            project=task.project, task=task, actor=actor, verb=event_type,
            target_type="task", target_id=task.pk,
            metadata={"title": task.title, "status": task.status, "assignee_id": task.assignee_id},
        )
        if event_type == "task_assigned" and task.assignee_id:
            create_notification(
                recipient=task.assignee, activity=activity, project=task.project, task=task,
                kind="assignment", message=f"You were assigned to {task.title}.",
            )


def record_task_deletion(*, task, actor):
    publish_project_event(task.project_id, "task_deleted", {
        "task_id": str(task.pk), "actor": actor.pk, "title": task.title,
    })
    create_activity(
        project=task.project, task=task, actor=actor, verb="task_deleted",
        target_type="task", target_id=task.pk, metadata={"title": task.title},
    )


def record_comment_change(*, comment, event_type):
    payload = {
        "task_id": str(comment.task_id),
        "actor": comment.author_id,
        "comment": {
            "id": comment.pk,
            "task_id": str(comment.task_id),
            "author": comment.author_id,
            "author_email": comment.author.email if comment.author_id else None,
            "body": comment.body,
            "mentioned_users": [
                {"id": mention.mentioned_user_id, "email": mention.mentioned_user.email}
                for mention in comment.mentions.select_related("mentioned_user")
            ],
            "created_at": comment.created_at.isoformat(),
            "updated_at": comment.updated_at.isoformat(),
        },
    }
    publish_project_event(comment.task.project_id, event_type, payload)
    activity = create_activity(
        project=comment.task.project, task=comment.task, actor=comment.author,
        verb="comment_added" if event_type == "comment_created" else "comment_updated",
        target_type="comment", target_id=comment.pk,
        metadata={"comment_id": comment.pk, "task_id": str(comment.task_id), "body": comment.body[:240]},
    )
    if event_type == "comment_created":
        for mention in comment.mentions.select_related("mentioned_user"):
            mention_activity = create_activity(
                project=comment.task.project, task=comment.task, actor=comment.author,
                verb="user_mentioned", target_type="user", target_id=mention.mentioned_user_id,
                metadata={"comment_id": comment.pk, "task_id": str(comment.task_id)},
            )
            create_notification(
                recipient=mention.mentioned_user, activity=mention_activity,
                project=comment.task.project, task=comment.task, kind="mention",
                message=f"You were mentioned in a comment on {comment.task.title}.",
            )
        recipients = []
        owner = comment.task.created_by
        if owner and owner.pk != (comment.author_id or None):
            recipients.append((owner, "comment", f"A comment was added to your task: {comment.task.title}."))
        for recipient, kind, message in recipients:
            create_notification(
                recipient=recipient, activity=activity, project=comment.task.project,
                task=comment.task, kind=kind, message=message,
            )
