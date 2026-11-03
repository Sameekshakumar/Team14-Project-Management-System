import uuid
from django.conf import settings
from django.db import models


class Sprint(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="sprints")
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=[("Planned", "Planned"), ("Active", "Active"), ("Completed", "Completed")], default="Planned")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    committed_story_points = models.PositiveBigIntegerField(null=True, blank=True)
    completed_story_points = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["start_date", "created_at"]
        constraints = [models.CheckConstraint(condition=models.Q(end_date__gte=models.F("start_date")), name="sprint_valid_date_range")]


class TimeEntry(models.Model):
    """FR-SPR-03: immutable time recorded by the authenticated user."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey("projects.Task", on_delete=models.CASCADE, related_name="time_entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="time_entries")
    minutes = models.PositiveIntegerField()
    note = models.CharField(max_length=1000, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.CheckConstraint(condition=models.Q(minutes__gte=1), name="time_entry_positive_minutes")]


class SprintDailySnapshot(models.Model):
    sprint = models.ForeignKey(Sprint, on_delete=models.CASCADE, related_name="daily_snapshots")
    date = models.DateField()
    total_points = models.PositiveBigIntegerField()
    remaining_points = models.PositiveBigIntegerField()
    completed_points = models.PositiveBigIntegerField()
    unestimated_count = models.PositiveIntegerField()

    class Meta:
        ordering = ["date"]
        constraints = [models.UniqueConstraint(fields=["sprint", "date"], name="unique_sprint_snapshot_day")]
