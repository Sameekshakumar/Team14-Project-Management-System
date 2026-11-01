from django.urls import path
from .views import BacklogListCreateView

urlpatterns = [
    path("projects/<uuid:project_id>/backlog-items/", BacklogListCreateView.as_view(), name="backlog-list"),
]
