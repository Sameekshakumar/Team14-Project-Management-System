from rest_framework import serializers

from .models import Project


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
