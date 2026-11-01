from rest_framework.exceptions import APIException, ValidationError
from django.utils import timezone
from projects.models import Task


class EmptySprint(APIException):
    status_code = 409
    default_detail = "Assign at least one backlog item before starting the sprint."
    default_code = "empty_sprint"


class SprintConflict(APIException):
    status_code = 409
    default_detail = "Only planned sprints can be changed or started."
    default_code = "sprint_conflict"


def assign_items(sprint, ids):
    """Caller holds project lock in an atomic transaction; validate whole batch first."""
    if sprint.status != "Planned":
        raise SprintConflict()
    tasks = list(Task.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
    if len(tasks) != len(ids) or any(t.project_id != sprint.project_id or t.sprint_id is not None or t.status != Task.STATUS_BACKLOG for t in tasks):
        raise ValidationError({"item_ids": "Every item must be an unassigned backlog item in this project."})
    Task.objects.filter(pk__in=ids).update(sprint=sprint, status=Task.STATUS_TODO, updated_at=timezone.now())
