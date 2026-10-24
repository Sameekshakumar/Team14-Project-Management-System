from rest_framework import serializers

from accounts.permissions import get_user_workspace_role

from .models import Project, Task


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
        ]
        read_only_fields = ["id", "project", "created_by", "created_at", "updated_at"]

    def get_project(self):
        return self.context.get("project") or getattr(self.instance, "project", None)

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
        return attrs
