from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken


@database_sync_to_async
def user_from_token(raw_token):
    try:
        token = AccessToken(raw_token)
        return get_user_model().objects.get(pk=token["user_id"], is_active=True)
    except (TokenError, KeyError, ValueError, get_user_model().DoesNotExist):
        return AnonymousUser()


class BearerTokenWebSocketMiddleware:
    """Authenticate browser sockets using the existing SimpleJWT access token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["user"] = AnonymousUser()
        for protocol in scope.get("subprotocols", []):
            if protocol.startswith("bearer."):
                scope["user"] = await user_from_token(protocol[len("bearer."):])
                break
        return await self.app(scope, receive, send)
