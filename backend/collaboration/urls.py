from django.urls import path

from .views import ProjectMemberSearchView, TaskCommentDetailView, TaskCommentsView

urlpatterns = [
    path("tasks/<uuid:task_id>/comments/", TaskCommentsView.as_view(), name="task-comments"),
    path("tasks/<uuid:task_id>/comments/<int:comment_id>/", TaskCommentDetailView.as_view(), name="task-comment-detail"),
    path("projects/<uuid:project_id>/members/search/", ProjectMemberSearchView.as_view(), name="project-member-search"),
]
