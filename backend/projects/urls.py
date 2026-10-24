from django.urls import path

from .views import ProjectViewSet

project_list = ProjectViewSet.as_view({"get": "list", "post": "create"})
project_detail = ProjectViewSet.as_view({
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
]
