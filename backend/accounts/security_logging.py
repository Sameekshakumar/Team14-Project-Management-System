import logging
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger("security")


def security_exception_handler(exc, context):
    """Log authentication failures at the API boundary as a fallback."""
    from rest_framework.views import exception_handler as rest_framework_exception_handler

    response = rest_framework_exception_handler(exc, context)
    if isinstance(exc, AuthenticationFailed):
        request = context.get("request")
        log_security_event(
            event_type="TOKEN_INVALID_OR_EXPIRED",
            request=request,
            reason="Authentication failed",
            level=logging.WARNING,
        )
    return response

# Sensitive keys that must NEVER appear in log details
SENSITIVE_KEYS = {
    "password",
    "password1",
    "password2",
    "pass",
    "token",
    "access",
    "refresh",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
    "key",
    "api_key",
    "credentials",
}


def sanitize_data(data):
    """
    Recursively remove sensitive keys (passwords, tokens, credentials) from dictionaries.
    """
    if not isinstance(data, dict):
        return data
    sanitized = {}
    for k, v in data.items():
        if k.lower() in SENSITIVE_KEYS or any(
            s in k.lower() for s in ["password", "token", "secret", "auth"]
        ):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_data(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_data(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            sanitized[k] = v
    return sanitized


def get_client_ip(request):
    """Extract client IP address safely from request META."""
    if not request:
        return None
    try:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")
    except Exception:
        return None


def log_security_event(
    event_type: str,
    request=None,
    user=None,
    user_id=None,
    attempted_identifier=None,
    workspace_id=None,
    reason=None,
    extra=None,
    level=logging.INFO,
):
    """
    Record a structured security event (SEC-006).

    Guarantees:
    - NEVER logs plaintext passwords, tokens, or Authorization headers.
    - NEVER allows a logging failure to break calling authentication flow.
    - Records event_type, timestamp, user_id, attempted_identifier, client IP, workspace_id.
    - Prevents duplicate events for the same request.
    """
    try:
        # Determine user_id
        if user_id is None and user and hasattr(user, "id"):
            user_id = user.id
        elif (
            user_id is None
            and request
            and hasattr(request, "user")
            and getattr(request.user, "is_authenticated", False)
        ):
            user_id = request.user.id

        ip_address = get_client_ip(request)
        ts = timezone.now().isoformat()

        # Sanitize attempted identifier (safely handles nonexistent users)
        safe_identifier = None
        if attempted_identifier and isinstance(attempted_identifier, str):
            safe_identifier = attempted_identifier.strip().lower()

        # Build details payload with recursive redaction of sensitive keys
        details = {}
        if reason:
            details["reason"] = str(reason)
        if extra and isinstance(extra, dict):
            details.update(sanitize_data(extra))

        event_data = {
            "event_type": event_type,
            "timestamp": ts,
            "user_id": user_id,
            "attempted_identifier": safe_identifier,
            "ip_address": ip_address,
            "workspace_id": str(workspace_id) if workspace_id else None,
            "details": details,
        }

        # Avoid duplicate events on the same request for the same event signature
        if request:
            logged_events = getattr(request, "_security_logged_events", None)
            if logged_events is None:
                logged_events = set()
                try:
                    request._security_logged_events = logged_events
                except Exception:
                    pass
            event_sig = (
                event_type,
                user_id,
                safe_identifier,
                str(workspace_id) if workspace_id else None,
            )
            if event_sig in logged_events:
                return event_data
            logged_events.add(event_sig)

        msg = (
            f"SECURITY_EVENT: event_type={event_type} "
            f"timestamp={ts} "
            f"user_id={user_id} "
            f"attempted_identifier={safe_identifier} "
            f"ip={ip_address} "
            f"workspace_id={workspace_id} "
            f"details={details}"
        )

        logger.log(level, msg, extra={"security_event": event_data})
        return event_data
    except Exception:
        # Critical Requirement 7: logging failure must never break normal authentication
        return None
