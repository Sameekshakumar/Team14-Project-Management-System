from django.urls import path

from .consumers import ProjectConsumer

websocket_urlpatterns = [
    path("ws/projects/<uuid:project_id>/board/", ProjectConsumer.as_asgi()),
]
