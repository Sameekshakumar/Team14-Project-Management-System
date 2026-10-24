from django.contrib import admin

from .models import Project, Task, TaskDependency


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "created_by", "created_at")
    list_filter = ("workspace",)
    search_fields = ("name",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "status", "assignee", "parent")
    list_filter = ("status", "project")
    search_fields = ("title",)


@admin.register(TaskDependency)
class TaskDependencyAdmin(admin.ModelAdmin):
    list_display = ("task", "depends_on", "created_at")
