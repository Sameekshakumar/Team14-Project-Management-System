from django.urls import path

from .views import (
    ProjectViewSet,
    TaskDependencyViewSet,
    TaskDetailViewSet,
    TaskListCreateViewSet,
)

project_list = ProjectViewSet.as_view({"get": "list", "post": "create"})
project_detail = ProjectViewSet.as_view({
    "get": "retrieve",
    "patch": "partial_update",
    "put": "update",
    "delete": "destroy",
})
task_list = TaskListCreateViewSet.as_view({"get": "list", "post": "create"})
dependency_list = TaskDependencyViewSet.as_view({"get": "list", "post": "create"})
dependency_detail = TaskDependencyViewSet.as_view({"delete": "destroy"})
task_detail = TaskDetailViewSet.as_view({
    "get": "retrieve",
    "patch": "partial_update",
    "put": "update",
    "delete": "destroy",
})

urlpatterns = [
    path(
        "workspaces/<uuid:workspace_id>/projects/",
        project_list,
        name="project-list",
    ),
    path(
        "workspaces/<uuid:workspace_id>/projects/<uuid:project_id>/",
        project_detail,
        name="project-detail",
    ),
    path(
        "projects/<uuid:project_id>/tasks/",
        task_list,
        name="task-list",
    ),
    path(
        "tasks/<uuid:task_id>/",
        task_detail,
        name="task-detail",
    ),
    path(
        "tasks/<uuid:task_id>/dependencies/",
        dependency_list,
        name="task-dependency-list",
    ),
    path(
        "tasks/<uuid:task_id>/dependencies/<uuid:dependency_id>/",
        dependency_detail,
        name="task-dependency-detail",
    ),
]
