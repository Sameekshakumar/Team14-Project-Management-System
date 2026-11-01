from django.urls import path
from .views import (BacklogListCreateView, SprintCreateView, SprintListView,
                    SprintItemsView, SprintItemRemoveView, SprintStartView)

urlpatterns = [
    path("projects/<uuid:project_id>/backlog-items/", BacklogListCreateView.as_view(), name="backlog-list"),
    path("projects/<uuid:project_id>/sprints/", SprintListView.as_view(), name="sprint-list"),
    path("sprints/", SprintCreateView.as_view(), name="sprint-create"),
    path("sprints/<uuid:sprint_id>/items/", SprintItemsView.as_view(), name="sprint-items"),
    path("sprints/<uuid:sprint_id>/items/<uuid:task_id>/", SprintItemRemoveView.as_view(), name="sprint-item-remove"),
    path("sprints/<uuid:sprint_id>/start/", SprintStartView.as_view(), name="sprint-start"),
]
