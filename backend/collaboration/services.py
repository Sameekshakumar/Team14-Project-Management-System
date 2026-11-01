import logging
import json
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder

from .models import ActivityEvent, Notification

logger = logging.getLogger(__name__)


def _json_safe(value):
    """Keep UUIDs, dates and decimals serializable across Redis and WebSockets."""
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def publish_project_event(project_id, event_type, payload):
    """Publish committed state; Redis failures never undo a successful REST write."""
    def publish():
        try:
            layer = get_channel_layer()
            if layer is None:
                return
            async_to_sync(layer.group_send)(
                f"project_{project_id}",
                {"type": "project.event", "event_type": event_type, "payload": _json_safe(payload)},
            )
        except Exception:
            logger.exception("Could not publish %s for project %s", event_type, project_id)

    transaction.on_commit(publish)


def publish_user_event(user_id, event_type, payload):
    """Deliver private notifications only to sockets owned by their recipient."""
    def publish():
        try:
            layer = get_channel_layer()
            if layer is None:
                return
            async_to_sync(layer.group_send)(
                f"user_{user_id}",
                {"type": "project.event", "event_type": event_type, "payload": _json_safe(payload)},
            )
        except Exception:
            logger.exception("Could not publish %s to user %s", event_type, user_id)

    transaction.on_commit(publish)


def activity_payload(event):
    return {
        "id": event.pk,
        "event_type": event.event_type,
        "payload": event.payload,
        "actor": event.actor_id,
        "actor_email": event.actor.email if event.actor_id else None,
        "task": event.task_id,
        "created_at": event.created_at.isoformat(),
    }


def create_activity(*, project, task, actor, event_type, payload):
    event = ActivityEvent.objects.create(
        project=project, task=task, actor=actor, event_type=event_type, payload=payload
    )
    return event


def create_notification(*, recipient, event, project, task, kind, message):
    if recipient is None:
        return None
    notification, _ = Notification.objects.get_or_create(
        recipient=recipient,
        activity=event,
        kind=kind,
        defaults={"project": project, "task": task, "message": message},
    )
    publish_user_event(
        recipient.id,
        "notification",
        {
            "id": notification.id,
            "recipient_id": recipient.id,
            "kind": kind,
            "message": message,
            "task_id": task.id if task else None,
            "activity_id": event.id,
            "created_at": notification.created_at.isoformat(),
        },
    )
    return notification


def record_task_change(*, task, actor, created, previous=None, task_data=None):
    event_type = "task_created" if created else "task_updated"
    payload = {
        "task_id": str(task.id),
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "assignee_id": task.assignee_id,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "actor_id": actor.id,
    }
    if previous:
        changed = [key for key, value in payload.items() if previous.get(key) != value]
        payload["changed"] = changed
    event = create_activity(
        project=task.project, task=task, actor=actor, event_type=event_type, payload=payload
    )

    old_assignee = previous.get("assignee_id") if previous else None
    if task.assignee_id and task.assignee_id != actor.id and (
        created or old_assignee != task.assignee_id
    ):
        create_notification(
            recipient=task.assignee,
            event=event,
            project=task.project,
            task=task,
            kind="assigned",
            message=f"You were assigned to {task.title}.",
        )

    if task_data is not None:
        payload["task"] = task_data
    publish_project_event(task.project_id, event_type, payload)
    publish_project_event(task.project_id, "activity_created", activity_payload(event))
    return event


def record_task_deletion(*, task, actor):
    payload = {"task_id": str(task.id), "title": task.title, "actor_id": actor.id}
    event = create_activity(
        project=task.project, task=task, actor=actor, event_type="task_deleted", payload=payload
    )
    publish_project_event(task.project_id, "task_deleted", payload)
    publish_project_event(task.project_id, "activity_created", activity_payload(event))
    return event


def record_comment(*, comment, actor, comment_data):
    task = comment.task
    project = task.project
    payload = {
        "comment_id": comment.id,
        "task_id": str(task.id),
        "task_title": task.title,
        "author_id": actor.id,
        "actor_id": actor.id,
        "author_email": actor.email,
        "body": comment.body,
        "mentioned_users": list(comment.mentioned_users.values_list("id", flat=True)),
    }
    event = create_activity(
        project=project,
        task=task,
        actor=actor,
        event_type="comment_created",
        payload=payload,
    )
    for recipient in comment.mentioned_users.exclude(pk=actor.pk):
        mentioned_event = create_activity(
            project=project,
            task=task,
            actor=actor,
            event_type="user_mentioned",
            payload={"comment_id": comment.id, "task_id": str(task.id), "mentioned_user_id": recipient.pk},
        )
        create_notification(
            recipient=recipient,
            event=mentioned_event,
            project=project,
            task=task,
            kind="mention",
            message=f"{actor.email} mentioned you on {task.title}.",
        )
        publish_project_event(project.id, "activity_created", activity_payload(mentioned_event))
    mentioned_ids = set(comment.mentioned_users.values_list("id", flat=True))
    task_owners = {task.assignee_id, task.created_by_id} - {None, actor.pk} - mentioned_ids
    for owner_id in task_owners:
        recipient = task.assignee if task.assignee_id == owner_id else task.created_by
        create_notification(
            recipient=recipient,
            event=event,
            project=project,
            task=task,
            kind="comment",
            message=f"{actor.email} commented on {task.title}.",
        )
    payload["comment"] = comment_data
    publish_project_event(project.id, "comment_created", payload)
    publish_project_event(project.id, "activity_created", activity_payload(event))
    return event


def record_comment_update(*, comment, actor, comment_data, previous_mentions):
    task = comment.task
    project = task.project
    payload = {
        "comment_id": comment.id,
        "task_id": str(task.id),
        "task_title": task.title,
        "author_id": actor.id,
        "actor_id": actor.id,
        "author_email": actor.email,
        "body": comment.body,
    }
    event = create_activity(
        project=project, task=task, actor=actor, event_type="comment_updated", payload=payload
    )
    for recipient in comment.mentioned_users.exclude(pk=actor.pk):
        if recipient.pk in previous_mentions:
            continue
        mentioned_event = create_activity(
            project=project,
            task=task,
            actor=actor,
            event_type="user_mentioned",
            payload={"comment_id": comment.id, "task_id": str(task.id), "mentioned_user_id": recipient.pk},
        )
        create_notification(
            recipient=recipient,
            event=mentioned_event,
            project=project,
            task=task,
            kind="mention",
            message=f"{actor.email} mentioned you on {task.title}.",
        )
        publish_project_event(project.id, "activity_created", activity_payload(mentioned_event))
    payload["comment"] = comment_data
    publish_project_event(project.id, "comment_updated", payload)
    publish_project_event(project.id, "activity_created", activity_payload(event))
    return event
