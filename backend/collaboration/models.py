from django.conf import settings
from django.db import models

from projects.models import Task


class TaskComment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name="task_comments",
    )
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]


class Mention(models.Model):
    comment = models.ForeignKey(TaskComment, on_delete=models.CASCADE, related_name="mentions")
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comment_mentions",
    )

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["comment", "mentioned_user"], name="unique_comment_mention",
        )]
