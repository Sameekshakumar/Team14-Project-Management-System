import logging
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken

from .security_logging import log_security_event


class LoggingJWTAuthentication(JWTAuthentication):
    """
    Extends SimpleJWT's JWTAuthentication to record security events
    when invalid or expired tokens are supplied, without logging credentials (SEC-006).
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except (InvalidToken, AuthenticationFailed):
            log_security_event(
                event_type="TOKEN_INVALID_OR_EXPIRED",
                request=request,
                # Never include exception text: token validation exceptions can
                # contain input supplied by the caller.
                reason="Token authentication failed",
                level=logging.WARNING,
            )
            raise
