"""
Issue #23 — Security Event Logging (SEC-006)

Tests that security-relevant events are recorded:
  - Failed login attempts generate security events.
  - Successful login attempts generate security events.
  - Nonexistent-user login attempts are recorded safely without errors.
  - Invalid and expired authentication token attempts generate suitable events.
  - Workspace member removal generates a security event with metadata.
  - Logout events generate a security event.
  - Unauthorized access attempts generate security events.
  - Event metadata includes event_type, timestamp, user_id, client IP, workspace_id.
  - Plaintext passwords are NEVER recorded.
  - JWT tokens and Authorization headers are NEVER recorded.
  - Logging failures do not break authentication or normal application flow.
  - Existing authentication functionality remains intact.
"""

from datetime import timedelta
import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Workspace, WorkspaceMembership

User = get_user_model()


class SecurityLogCaptureHandler(logging.Handler):
    """Custom logging handler to capture security events during test runs."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def clear(self):
        self.records.clear()


class SecurityEventLoggingTests(APITestCase):
    """SEC-006: Comprehensive security event logging test suite."""

    def setUp(self):
        self.security_logger = logging.getLogger("security")
        self.handler = SecurityLogCaptureHandler()
        self.security_logger.addHandler(self.handler)
        self.security_logger.setLevel(logging.INFO)

        self.user_password = "Str0ng-Security-Pass!123"
        self.user = User.objects.create_user(
            email="sec_user@example.com",
            password=self.user_password,
        )

        self.login_url = "/api/auth/login/"
        self.logout_url = "/api/auth/logout/"
        self.refresh_url = "/api/auth/token/refresh/"
        self.me_url = "/api/auth/me/"

    def tearDown(self):
        self.security_logger.removeHandler(self.handler)

    # -------------------------------------------------------------------------
    # 1. Login Events (Success & Failure)
    # -------------------------------------------------------------------------

    def test_successful_login_generates_security_event(self):
        """Successful login records a LOGIN_SUCCESS security event with user metadata."""
        response = self.client.post(
            self.login_url,
            {"email": "sec_user@example.com", "password": self.user_password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        login_events = [
            r for r in self.handler.records
            if "LOGIN_SUCCESS" in r.getMessage()
        ]
        self.assertGreaterEqual(len(login_events), 1)
        record = login_events[0]
        event_data = getattr(record, "security_event", {})

        self.assertEqual(event_data.get("event_type"), "LOGIN_SUCCESS")
        self.assertEqual(event_data.get("user_id"), self.user.id)
        self.assertEqual(event_data.get("attempted_identifier"), "sec_user@example.com")
        self.assertIsNotNone(event_data.get("timestamp"))
        self.assertIsNotNone(event_data.get("ip_address"))

    def test_failed_login_wrong_password_generates_security_event(self):
        """Failed login with incorrect password generates a LOGIN_FAILURE event."""
        wrong_pass = "Completely-Wrong-Pass!"
        response = self.client.post(
            self.login_url,
            {"email": "sec_user@example.com", "password": wrong_pass},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        failure_events = [
            r for r in self.handler.records
            if "LOGIN_FAILURE" in r.getMessage()
        ]
        self.assertGreaterEqual(len(failure_events), 1)
        event_data = getattr(failure_events[0], "security_event", {})

        self.assertEqual(event_data.get("event_type"), "LOGIN_FAILURE")
        self.assertEqual(event_data.get("attempted_identifier"), "sec_user@example.com")
        self.assertIsNotNone(event_data.get("timestamp"))

    def test_nonexistent_user_login_attempt_recorded_safely(self):
        """Login attempt for a non-existent email is logged safely with user_id=None."""
        nonexistent_email = "nonexistent_ghost@example.com"
        response = self.client.post(
            self.login_url,
            {"email": nonexistent_email, "password": "AnyPassword!123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        failure_events = [
            r for r in self.handler.records
            if "LOGIN_FAILURE" in r.getMessage()
        ]
        self.assertGreaterEqual(len(failure_events), 1)
        event_data = getattr(failure_events[0], "security_event", {})

        self.assertEqual(event_data.get("event_type"), "LOGIN_FAILURE")
        self.assertEqual(event_data.get("attempted_identifier"), nonexistent_email)
        self.assertIsNone(event_data.get("user_id"))

    def test_malformed_login_payload_generates_security_event(self):
        """Malformed login request (e.g. invalid email structure) generates LOGIN_FAILURE."""
        response = self.client.post(
            self.login_url,
            {"email": "not-a-valid-email", "password": "Short"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        failure_events = [
            r for r in self.handler.records
            if "LOGIN_FAILURE" in r.getMessage()
        ]
        self.assertGreaterEqual(len(failure_events), 1)
        event_data = getattr(failure_events[0], "security_event", {})
        self.assertIsNone(event_data.get("attempted_identifier"))

    def test_malformed_login_does_not_log_unvalidated_identifier(self):
        """Unvalidated login fields can contain secrets and must not enter logs."""
        secret_value = "Bearer eyJ-secret-token-value"
        response = self.client.post(
            self.login_url,
            {"email": secret_value, "password": secret_value},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        for record in self.handler.records:
            self.assertNotIn(secret_value, record.getMessage())
            self.assertNotIn(secret_value, str(getattr(record, "security_event", {})))

    # -------------------------------------------------------------------------
    # 2. Token Events (Invalid and Expired Tokens)
    # -------------------------------------------------------------------------

    def test_invalid_token_generates_security_event(self):
        """Requests with invalid/tampered JWT tokens generate TOKEN_INVALID_OR_EXPIRED."""
        fake_token = "invalid.bearer.token"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {fake_token}")
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            response.wsgi_request.META.get("HTTP_AUTHORIZATION"),
            f"Bearer {fake_token}",
        )

        token_events = [
            r for r in self.handler.records
            if "TOKEN_INVALID_OR_EXPIRED" in r.getMessage()
        ]
        self.assertGreaterEqual(len(token_events), 1)
        event_data = getattr(token_events[0], "security_event", {})
        self.assertEqual(event_data.get("event_type"), "TOKEN_INVALID_OR_EXPIRED")
        self.assertIsNotNone(event_data.get("ip_address"))

    def test_expired_token_generates_security_event(self):
        """Requests with an expired JWT access token generate TOKEN_INVALID_OR_EXPIRED."""
        refresh = RefreshToken.for_user(self.user)
        access = refresh.access_token
        access.set_exp(lifetime=timedelta(seconds=-10))
        expired_token = str(access)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired_token}")
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        token_events = [
            r for r in self.handler.records
            if "TOKEN_INVALID_OR_EXPIRED" in r.getMessage()
        ]
        self.assertGreaterEqual(len(token_events), 1)

    def test_invalid_refresh_token_generates_security_event(self):
        """Invalid token submitted to /token/refresh/ generates TOKEN_INVALID_OR_EXPIRED."""
        response = self.client.post(
            self.refresh_url,
            {"refresh": "invalid.refresh.token"},
            format="json",
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
        )

        token_events = [
            r for r in self.handler.records
            if "TOKEN_INVALID_OR_EXPIRED" in r.getMessage()
        ]
        self.assertGreaterEqual(len(token_events), 1)

    # -------------------------------------------------------------------------
    # 3. Workspace Member Removal & Access Events
    # -------------------------------------------------------------------------

    def test_workspace_member_removal_generates_security_event(self):
        """Member removal by workspace owner generates WORKSPACE_MEMBER_REMOVED."""
        owner = User.objects.create_user(
            email="ws_owner@example.com", password=self.user_password
        )
        member = User.objects.create_user(
            email="ws_member@example.com", password=self.user_password
        )
        workspace = Workspace.objects.create(name="Security WS", owner=owner)
        WorkspaceMembership.objects.create(
            workspace=workspace, user=member, role="Member"
        )

        self.client.force_authenticate(user=owner)
        del_url = f"/api/auth/workspaces/{workspace.id}/members/{member.id}/"
        response = self.client.delete(del_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        removal_events = [
            r for r in self.handler.records
            if "WORKSPACE_MEMBER_REMOVED" in r.getMessage()
        ]
        self.assertGreaterEqual(len(removal_events), 1)
        event_data = getattr(removal_events[0], "security_event", {})
        self.assertEqual(event_data.get("event_type"), "WORKSPACE_MEMBER_REMOVED")
        self.assertEqual(event_data.get("user_id"), owner.id)
        self.assertEqual(event_data.get("workspace_id"), str(workspace.id))
        self.assertEqual(
            event_data.get("details", {}).get("removed_user_id"), member.id
        )

    def test_unauthorized_workspace_access_generates_security_event(self):
        """Unauthorized attempt to access another workspace logs UNAUTHORIZED_ACCESS."""
        owner = User.objects.create_user(
            email="ws_owner2@example.com", password=self.user_password
        )
        workspace = Workspace.objects.create(name="Private WS", owner=owner)

        outsider = User.objects.create_user(
            email="outsider@example.com", password=self.user_password
        )
        self.client.force_authenticate(user=outsider)

        response = self.client.get(f"/api/auth/workspaces/{workspace.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        unauth_events = [
            r for r in self.handler.records
            if "UNAUTHORIZED_ACCESS" in r.getMessage()
        ]
        self.assertGreaterEqual(len(unauth_events), 1)
        event_data = getattr(unauth_events[0], "security_event", {})
        self.assertEqual(event_data.get("event_type"), "UNAUTHORIZED_ACCESS")
        self.assertEqual(event_data.get("user_id"), outsider.id)
        self.assertEqual(event_data.get("workspace_id"), str(workspace.id))

    # -------------------------------------------------------------------------
    # 4. Logout Event
    # -------------------------------------------------------------------------

    def test_logout_generates_security_event(self):
        """Calling the logout endpoint records a LOGOUT security event."""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.logout_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        logout_events = [
            r for r in self.handler.records
            if "LOGOUT" in r.getMessage()
        ]
        self.assertGreaterEqual(len(logout_events), 1)
        event_data = getattr(logout_events[0], "security_event", {})
        self.assertEqual(event_data.get("event_type"), "LOGOUT")
        self.assertEqual(event_data.get("user_id"), self.user.id)

    # -------------------------------------------------------------------------
    # 5. Critical Privacy & Credential Exclusion Safeguards
    # -------------------------------------------------------------------------

    def test_plaintext_passwords_never_recorded(self):
        """Plaintext passwords must NEVER appear anywhere in security event logs."""
        secret_password = "SuperSecretPlainTextPassword!456"
        # Test failed login with secret password
        self.client.post(
            self.login_url,
            {"email": "sec_user@example.com", "password": secret_password},
            format="json",
        )
        # Test successful login with secret password
        temp_user = User.objects.create_user(
            email="temp_pass_test@example.com", password=secret_password
        )
        self.client.post(
            self.login_url,
            {"email": "temp_pass_test@example.com", "password": secret_password},
            format="json",
        )

        for record in self.handler.records:
            msg = record.getMessage()
            self.assertNotIn(
                secret_password,
                msg,
                "Plaintext password must NEVER appear in log messages.",
            )
            event_data = getattr(record, "security_event", {})
            for key, val in event_data.items():
                self.assertNotEqual(
                    val,
                    secret_password,
                    f"Plaintext password found in field {key}.",
                )
                if isinstance(val, dict):
                    self.assertNotIn(
                        secret_password,
                        str(val),
                        f"Plaintext password found in nested dict {key}.",
                    )

    def test_jwt_tokens_and_auth_headers_never_recorded(self):
        """Tokens and Authorization header contents must NEVER appear in logs."""
        fake_secret_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.SuperSecretPayload.FakeSig"
        auth_header_value = f"Bearer {fake_secret_token}"

        self.client.credentials(HTTP_AUTHORIZATION=auth_header_value)
        self.client.get(self.me_url)

        for record in self.handler.records:
            msg = record.getMessage()
            self.assertNotIn(
                fake_secret_token,
                msg,
                "Raw JWT tokens must NEVER appear in log messages.",
            )
            self.assertNotIn(
                auth_header_value,
                msg,
                "Authorization header values must NEVER appear in log messages.",
            )
            event_data = getattr(record, "security_event", {})
            self.assertNotIn(fake_secret_token, str(event_data))
            self.assertNotIn(auth_header_value, str(event_data))

    # -------------------------------------------------------------------------
    # 6. Logging Failures Do Not Break Normal Flow
    # -------------------------------------------------------------------------

    def test_logging_failure_does_not_break_login(self):
        """A failure within the logging system must not prevent successful authentication."""
        with patch.object(self.security_logger, "log", side_effect=RuntimeError("Logging failed!")):
            response = self.client.post(
                self.login_url,
                {"email": "sec_user@example.com", "password": self.user_password},
                format="json",
            )
            # Login must succeed despite logging failure
            self.assertEqual(
                response.status_code,
                status.HTTP_200_OK,
                "Logging failure must not break normal login flow.",
            )
            self.assertIn("access", response.data)
            self.assertIn("refresh", response.data)

    def test_no_duplicate_security_events_for_same_request(self):
        """A single login request must not emit duplicate events for the same action."""
        self.handler.clear()
        self.client.post(
            self.login_url,
            {"email": "sec_user@example.com", "password": self.user_password},
            format="json",
        )
        login_success_events = [
            r for r in self.handler.records
            if "LOGIN_SUCCESS" in r.getMessage()
        ]
        self.assertEqual(
            len(login_success_events),
            1,
            "Expected exactly 1 LOGIN_SUCCESS event for a single login request.",
        )

    # -------------------------------------------------------------------------
    # 7. Existing Authentication Functionality Intact
    # -------------------------------------------------------------------------

    def test_existing_auth_pipeline_remains_fully_functional(self):
        """Verify registration, login, me, and token refresh all continue working seamlessly."""
        reg_payload = {
            "email": "pipeline_user@example.com",
            "password": "Valid-Pipeline-Pass!789",
        }
        reg_res = self.client.post("/api/auth/register/", reg_payload, format="json")
        self.assertEqual(reg_res.status_code, status.HTTP_201_CREATED)
        access_token = reg_res.data["access"]
        refresh_token = reg_res.data["refresh"]

        # Authenticate on /me
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        me_res = self.client.get(self.me_url)
        self.assertEqual(me_res.status_code, status.HTTP_200_OK)
        self.assertEqual(me_res.data["email"], "pipeline_user@example.com")

        # Refresh token
        self.client.credentials()  # clear credentials
        ref_res = self.client.post(
            self.refresh_url, {"refresh": refresh_token}, format="json"
        )
        self.assertEqual(ref_res.status_code, status.HTTP_200_OK)
        new_access = ref_res.data["access"]

        # Access /me with new token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
        me_res2 = self.client.get(self.me_url)
        self.assertEqual(me_res2.status_code, status.HTTP_200_OK)
