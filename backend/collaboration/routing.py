from django.urls import path

from .consumers import NotificationConsumer, ProjectConsumer

websocket_urlpatterns = [
    path("ws/projects/<uuid:project_id>/board/", ProjectConsumer.as_asgi()),
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
