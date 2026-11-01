import re

import bleach
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import serializers

from .models import ActivityEvent, Mention, Notification, TaskComment

User = get_user_model()
MENTION_PATTERN = re.compile(r"(?<![\w.+-])@([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})", re.IGNORECASE)


class TaskCommentSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source="author.email", read_only=True, default=None)
    mentioned_users = serializers.SerializerMethodField()

    class Meta:
        model = TaskComment
        fields = ["id", "task", "author", "author_email", "body", "mentioned_users", "created_at", "updated_at"]
        read_only_fields = ["id", "task", "author", "author_email", "created_at", "updated_at"]

    def get_mentioned_users(self, comment):
        return [{"id": mention.mentioned_user_id, "email": mention.mentioned_user.email}
                for mention in comment.mentions.select_related("mentioned_user")]

    def validate_body(self, value):
        value = bleach.clean(value.strip(), tags=[], attributes={}, strip=True, strip_comments=True)
        if not value:
            raise serializers.ValidationError("Comment cannot be empty.")
        return value

    def validate(self, attrs):
        task = self.context["task"]
        body = attrs.get("body", self.instance.body if self.instance else "")
        if "body" in attrs:
            emails = list(dict.fromkeys(email.lower() for email in MENTION_PATTERN.findall(body)))
            workspace = task.project.workspace
            users = list(User.objects.filter(
                Q(workspace_memberships__workspace=workspace) | Q(pk=workspace.owner_id),
                email__in=emails, is_active=True,
            ).distinct())
            found = {user.email.lower(): user for user in users}
            missing = [email for email in emails if email not in found]
            if missing:
                raise serializers.ValidationError({
                    "body": "Only active workspace members can be mentioned: " + ", ".join(missing)
                })
            attrs["_mentioned_users"] = [found[email] for email in emails]
        return attrs

    def create(self, validated_data):
        users = validated_data.pop("_mentioned_users", [])
        comment = super().create(validated_data)
        Mention.objects.bulk_create([Mention(comment=comment, mentioned_user=user) for user in users])
        return comment

    def update(self, instance, validated_data):
        users = validated_data.pop("_mentioned_users", None)
        comment = super().update(instance, validated_data)
        if users is not None:
            Mention.objects.filter(comment=comment).delete()
            Mention.objects.bulk_create([Mention(comment=comment, mentioned_user=user) for user in users])
        return comment


class ActivityEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None)
    task_title = serializers.CharField(source="task.title", read_only=True, default=None)

    class Meta:
        model = ActivityEvent
        fields = ["id", "verb", "target_type", "target_id", "metadata", "actor", "actor_email", "task", "task_title", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)
    task_title = serializers.CharField(source="task.title", read_only=True, default=None)

    class Meta:
        model = Notification
        fields = ["id", "project", "project_name", "task", "task_title", "activity", "kind", "message", "is_read", "created_at", "read_at"]
        read_only_fields = fields
