from django.urls import path

from .views import (
    NotificationListView,
    NotificationReadAllView,
    NotificationReadView,
    NotificationUnreadCountView,
    ProjectActivityListView,
    ProjectAnalyticsView,
    ProjectMemberSearchView,
    ProjectContextView,
    TaskCommentDetailView,
    TaskCommentListCreateView,
)

urlpatterns = [
    path("tasks/<uuid:task_id>/comments/", TaskCommentListCreateView.as_view(), name="task-comments"),
    path("tasks/<uuid:task_id>/comments/<int:comment_id>/", TaskCommentDetailView.as_view(), name="task-comment-detail"),
    path("projects/<uuid:project_id>/activity/", ProjectActivityListView.as_view(), name="project-activity"),
    path("projects/<uuid:project_id>/members/search/", ProjectMemberSearchView.as_view(), name="project-member-search"),
    path("projects/<uuid:project_id>/context/", ProjectContextView.as_view(), name="project-context"),
    path("projects/<uuid:project_id>/analytics/", ProjectAnalyticsView.as_view(), name="project-analytics"),
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/read-all/", NotificationReadAllView.as_view(), name="notification-read-all"),
    path("notifications/unread-count/", NotificationUnreadCountView.as_view(), name="notification-unread-count"),
    path("notifications/<int:notification_id>/read/", NotificationReadView.as_view(), name="notification-read"),
]
