from django.conf import settings
from django.db import models

from projects.models import Project, Task


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="task_comments"
    )
    body = models.TextField(max_length=5000)
    mentioned_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, through="collaboration.Mention",
        related_name="mentioned_in_comments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment on {self.task_id} by {self.author_id}"


class Mention(models.Model):
    comment = models.ForeignKey(TaskComment, on_delete=models.CASCADE, related_name="mentions")
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comment_mentions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["comment", "mentioned_user"], name="unique_comment_mention")
        ]


class ActivityEvent(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="activity")
    task = models.ForeignKey(
        Task, on_delete=models.SET_NULL, null=True, blank=True, related_name="activity_events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="activity_events",
    )
    event_type = models.CharField(max_length=40)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["project", "-created_at"], name="collab_act_proj_idx")]


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    activity = models.ForeignKey(
        ActivityEvent, on_delete=models.CASCADE, related_name="notifications"
    )
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="notifications")
    task = models.ForeignKey(
        Task, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications"
    )
    kind = models.CharField(max_length=20)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["recipient", "activity", "kind"], name="unique_activity_notification")
        ]
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"], name="collab_notif_inbox_idx")]
