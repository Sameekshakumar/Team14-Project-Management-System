from django.urls import path

from .views import (
    NotificationListView, NotificationReadAllView, NotificationReadView,
    NotificationUnreadCountView, ProjectActivityView, ProjectContextView,
    ProjectMemberSearchView, TaskCommentDetailView, TaskCommentsView,
)

urlpatterns = [
    path("tasks/<uuid:task_id>/comments/", TaskCommentsView.as_view(), name="task-comments"),
    path("tasks/<uuid:task_id>/comments/<int:comment_id>/", TaskCommentDetailView.as_view(), name="task-comment-detail"),
    path("projects/<uuid:project_id>/members/search/", ProjectMemberSearchView.as_view(), name="project-member-search"),
    path("projects/<uuid:project_id>/activity/", ProjectActivityView.as_view(), name="project-activity"),
    path("projects/<uuid:project_id>/context/", ProjectContextView.as_view(), name="project-context"),
    path("notifications/", NotificationListView.as_view(), name="notifications"),
    path("notifications/read-all/", NotificationReadAllView.as_view(), name="notifications-read-all"),
    path("notifications/unread-count/", NotificationUnreadCountView.as_view(), name="notifications-unread-count"),
    path("notifications/<int:notification_id>/read/", NotificationReadView.as_view(), name="notification-read"),
]
