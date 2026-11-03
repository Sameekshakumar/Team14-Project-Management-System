from rest_framework import serializers
from .models import Sprint


class ItemIdsSerializer(serializers.Serializer):
    item_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=1000)

    def validate_item_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Do not repeat an item ID.")
        return value


class SprintCreateSerializer(serializers.ModelSerializer):
    project = serializers.UUIDField()
    item_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=1000)

    class Meta:
        model = Sprint
        fields = ["project", "name", "start_date", "end_date", "item_ids"]

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError({"end_date": "End date must be on or after start date."})
        ids = attrs["item_ids"]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError({"item_ids": "Do not repeat an item ID."})
        return attrs


class SprintSerializer(serializers.ModelSerializer):
    total_story_points = serializers.SerializerMethodField()
    unestimated_count = serializers.SerializerMethodField()
    items = serializers.SerializerMethodField()

    class Meta:
        model = Sprint
        fields = ["id", "project", "name", "start_date", "end_date", "status", "created_by", "created_at", "total_story_points", "unestimated_count", "items", "started_at", "completed_at", "committed_story_points", "completed_story_points"]

    def get_total_story_points(self, obj):
        return sum(item.story_points or 0 for item in obj.items.all())

    def get_unestimated_count(self, obj):
        return sum(item.story_points is None for item in obj.items.all())

    def get_items(self, obj):
        return [{"id": str(t.pk), "title": t.title, "status": t.status, "story_points": t.story_points} for t in obj.items.all()]
