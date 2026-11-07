from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from common.validators import SanitizedTextMixin
from projects.models import Task
from projects.permissions import require_member, require_write
from .exceptions import SprintErrorsMixin
from .models import TimeEntry


class TimeEntrySerializer(SanitizedTextMixin, serializers.ModelSerializer):
    minutes = serializers.IntegerField(min_value=1, max_value=2147483647)
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = TimeEntry
        fields = ["id", "task", "user", "user_email", "minutes", "note", "created_at"]
        read_only_fields = ["id", "task", "user", "user_email", "created_at"]

    def get_user_email(self, obj):
        return obj.user.email if obj.user else "Deleted user"


def can_log_time(user, task, role):
    # Projects inherit workspace roles; created_by is not a separate Owner role.
    return role != "Viewer" and (role == "Owner" or task.assignee_id == user.pk)


def time_summary(task, user, role):
    entries = list(task.time_entries.select_related("user"))
    return {
        "task": str(task.pk),
        "total_minutes": sum(entry.minutes for entry in entries),
        "can_log_time": can_log_time(user, task, role),
        "entries": TimeEntrySerializer(entries, many=True).data,
    }


class TaskTimeEntriesView(SprintErrorsMixin, APIView):
    def get(self, request, task_id):
        task = get_object_or_404(Task.objects.select_related("project__workspace"), pk=task_id)
        role = require_member(request.user, task.project.workspace)
        return Response(time_summary(task, request.user, role))

    @transaction.atomic
    def post(self, request, task_id):
        task = get_object_or_404(Task.objects.select_for_update(of=("self",)).select_related("project__workspace"), pk=task_id)
        role = require_write(request.user, task.project.workspace)
        if not can_log_time(request.user, task, role):
            raise PermissionDenied("Only the task assignee or workspace Owner can log time against this task.")
        serializer = TimeEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(task=task, user=request.user)
        # Return the updated history and total with the successful write so a
        # failed follow-up GET cannot make a saved entry look like a failed save.
        return Response(time_summary(task, request.user, role), status=status.HTTP_201_CREATED)
