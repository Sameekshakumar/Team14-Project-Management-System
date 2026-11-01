import logging
from rest_framework.views import exception_handler

logger = logging.getLogger("django.security")


class SprintErrorsMixin:
    """SRS 3.3 envelope, scoped to this module to preserve existing clients."""
    def handle_exception(self, exc):
        response = exception_handler(exc, self.get_exception_handler_context())
        if response is None:
            return super().handle_exception(exc)
        code = {400: "invalid_field", 401: "invalid_token", 403: "insufficient_role",
                404: "not_found", 409: "conflict"}.get(response.status_code, "request_failed")
        detail = response.data
        message = str(detail.get("detail", "Please check the submitted fields.")) if isinstance(detail, dict) else "Request failed."
        if response.status_code == 403:
            logger.warning("Sprint access denied: user=%s path=%s", self.request.user.pk, self.request.path)
        response.data = {"error": {"code": getattr(exc, "default_code", code) if response.status_code == 409 else code,
                                   "message": message, "details": detail}}
        response.exception = True
        return response
