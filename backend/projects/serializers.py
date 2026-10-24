from rest_framework import serializers

from accounts.permissions import get_user_workspace_role

from .models import (
    Project,
    Task,
    TaskDependency,
    dependency_creates_cycle,
    incomplete_dependencies,
)


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "workspace", "name", "description", "created_by", "created_at"]
        read_only_fields = ["id", "workspace", "created_by", "created_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Project name cannot be empty.")
        return value

    def validate(self, attrs):
        # UniqueConstraint spans workspace, which is set by the view, so the
        # model-level validator cannot see it. Check it here instead.
        name = attrs.get("name")
        workspace = self.context.get("workspace")
        if name and workspace:
            duplicates = Project.objects.filter(workspace=workspace, name=name)
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError(
                    {"name": "A project with this name already exists in this workspace."}
                )
        return attrs


class SubtaskSerializer(serializers.ModelSerializer):
    """Compact nested representation; avoids recursing through TaskSerializer."""

    class Meta:
        model = Task
        fields = ["id", "title", "status", "assignee"]
        read_only_fields = fields


class TaskSerializer(serializers.ModelSerializer):
    subtasks = SubtaskSerializer(many=True, read_only=True)
    assignee_email = serializers.EmailField(source="assignee.email", read_only=True)
    depends_on = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            "id",
            "project",
            "parent",
            "title",
            "description",
            "status",
            "assignee",
            "assignee_email",
            "created_by",
            "created_at",
            "updated_at",
            "subtasks",
            "depends_on",
            "is_blocked",
        ]
        read_only_fields = ["id", "project", "created_by", "created_at", "updated_at"]

    def get_project(self):
        return self.context.get("project") or getattr(self.instance, "project", None)

    def get_depends_on(self, obj):
        return [dependency.depends_on_id for dependency in obj.dependencies.all()]

    def get_is_blocked(self, obj):
        """
        True while any prerequisite task is still open. Reads the prefetched
        dependencies so listing a board stays at a constant query count.
        """
        return any(
            dependency.depends_on.status != Task.STATUS_DONE
            for dependency in obj.dependencies.all()
        )

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Task title cannot be empty.")
        return value

    def validate_assignee(self, value):
        # FR-TASK-02: a task is assigned to a member of the project's workspace.
        if value is None:
            return value
        project = self.get_project()
        if project and get_user_workspace_role(value, project.workspace) is None:
            raise serializers.ValidationError(
                "Assignee must be a member of this project's workspace."
            )
        return value

    def validate_parent(self, value):
        if value is None:
            return value
        project = self.get_project()
        if project and value.project_id != project.id:
            raise serializers.ValidationError(
                "A subtask's parent must belong to the same project."
            )
        if value.parent_id is not None:
            raise serializers.ValidationError(
                "Subtasks cannot be nested more than one level deep."
            )
        if self.instance and value.pk == self.instance.pk:
            raise serializers.ValidationError("A task cannot be its own parent.")
        return value

    def validate(self, attrs):
        # A task that already has subtasks cannot itself become a subtask,
        # which would create a second level of nesting.
        parent = attrs.get("parent")
        if parent is not None and self.instance and self.instance.subtasks.exists():
            raise serializers.ValidationError(
                {"parent": "A task with subtasks cannot become a subtask itself."}
            )

        # SRS 6.5: a task cannot be marked Done while it has an incomplete
        # dependency.
        if attrs.get("status") == Task.STATUS_DONE and self.instance:
            blockers = incomplete_dependencies(self.instance)
            if blockers.exists():
                titles = ", ".join(blockers.values_list("title", flat=True))
                raise serializers.ValidationError(
                    {"status": f"Cannot mark Done while these dependencies are incomplete: {titles}."}
                )
        return attrs


class TaskDependencySerializer(serializers.ModelSerializer):
    depends_on_title = serializers.CharField(source="depends_on.title", read_only=True)
    depends_on_status = serializers.CharField(source="depends_on.status", read_only=True)

    class Meta:
        model = TaskDependency
        fields = ["id", "task", "depends_on", "depends_on_title", "depends_on_status", "created_at"]
        read_only_fields = ["id", "task", "created_at"]

    def validate_depends_on(self, value):
        task = self.context.get("task")
        if task is None:
            return value
        if value.pk == task.pk:
            raise serializers.ValidationError("A task cannot depend on itself.")
        if value.project_id != task.project_id:
            raise serializers.ValidationError(
                "A dependency must be between two tasks in the same project."
            )
        if TaskDependency.objects.filter(task=task, depends_on=value).exists():
            raise serializers.ValidationError("This dependency already exists.")
        # FR-TASK-04: reject an edge that would create a cycle.
        if dependency_creates_cycle(task, value):
            raise serializers.ValidationError(
                "This dependency would create a circular dependency."
            )
        return value
