import uuid

from django.conf import settings
from django.db import models

from accounts.models import Workspace


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        Workspace,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_projects",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "name"],
                name="unique_project_name_per_workspace",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.workspace.name})"


class Task(models.Model):
    """
    FR-TASK-02: a task belongs to a project, may be broken into subtasks, and
    may be assigned to a single workspace member.
    """
    STATUS_BACKLOG = "Backlog"
    STATUS_TODO = "To Do"
    STATUS_IN_PROGRESS = "In Progress"
    STATUS_DONE = "Done"

    # Enum and field widths follow the Team 14 SRS data dictionary.
    STATUS_CHOICES = [
        (STATUS_BACKLOG, STATUS_BACKLOG),
        (STATUS_TODO, STATUS_TODO),
        (STATUS_IN_PROGRESS, STATUS_IN_PROGRESS),
        (STATUS_DONE, STATUS_DONE),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subtasks",
    )
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_TODO,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def workspace(self):
        return self.project.workspace

    def __str__(self):
        return self.title


class TaskDependency(models.Model):
    """
    FR-TASK-04: `task` depends on `depends_on`, meaning `depends_on` must be
    Done before `task` can be marked Done (SRS 6.5 business rules).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="dependencies",
    )
    depends_on = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="dependents",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "depends_on"],
                name="unique_task_dependency",
            ),
            models.CheckConstraint(
                condition=~models.Q(task=models.F("depends_on")),
                name="task_cannot_depend_on_itself",
            ),
        ]

    def __str__(self):
        return f"{self.task.title} depends on {self.depends_on.title}"


def dependency_creates_cycle(task, depends_on):
    """
    True if making `task` depend on `depends_on` would close a loop, i.e. if
    `task` is already reachable by walking dependencies outward from
    `depends_on`.

    ponytail: iterative BFS issuing one query per visited task. Fine at
    course-project scale; batch into a recursive CTE if a project ever carries
    thousands of dependencies.
    """
    if task.pk == depends_on.pk:
        return True

    seen = set()
    frontier = [depends_on.pk]
    while frontier:
        current = frontier.pop()
        if current == task.pk:
            return True
        if current in seen:
            continue
        seen.add(current)
        frontier.extend(
            TaskDependency.objects.filter(task_id=current).values_list(
                "depends_on_id", flat=True
            )
        )
    return False


def incomplete_dependencies(task):
    """Prerequisite tasks of `task` that are not yet Done."""
    return Task.objects.filter(
        dependents__task=task,
    ).exclude(status=Task.STATUS_DONE)
