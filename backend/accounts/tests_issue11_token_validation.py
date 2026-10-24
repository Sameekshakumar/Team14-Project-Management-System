"""
Issue #11 — Reject expired/invalid auth tokens (SEC-003)

Tests that:
  - Valid tokens are accepted on protected endpoints.
  - Expired access tokens are rejected with HTTP 401.
  - Malformed tokens are rejected with HTTP 401.
  - Invalid-signature / tampered tokens are rejected with HTTP 401.
  - Requests with missing Authorization header receive HTTP 401.
  - Token refresh with a valid refresh token continues to work.
  - Token refresh with an expired/invalid refresh token is rejected.
"""

import time
from datetime import timedelta

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.utils import aware_utcnow
from unittest.mock import patch

User = get_user_model()

ME_URL = "/api/auth/me/"
REFRESH_URL = "/api/auth/token/refresh/"


def _make_access_token(user):
    """Return a fresh, valid access token string for the given user."""
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)


def _make_refresh_token(user):
    """Return a fresh, valid refresh token string for the given user."""
    return str(RefreshToken.for_user(user))


class ValidTokenAcceptedTests(APITestCase):
    """SEC-003: A valid JWT access token must be accepted on protected endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="valid_tok@example.com", password="Str0ng-Example-Pass!"
        )

    def test_valid_access_token_allows_access_to_me(self):
        """A freshly issued access token must grant access to /me."""
        token = _make_access_token(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)


class MissingTokenRejectedTests(APITestCase):
    """SEC-003: Requests without an Authorization header must be rejected."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="no_tok@example.com", password="Str0ng-Example-Pass!"
        )

    def test_no_token_returns_401_on_protected_endpoint(self):
        """A request with no token must return 401 Unauthorized."""
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_empty_bearer_returns_401(self):
        """A 'Bearer ' header with no value must return 401."""
        self.client.credentials(HTTP_AUTHORIZATION="Bearer ")
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class MalformedTokenRejectedTests(APITestCase):
    """SEC-003: Malformed tokens must be rejected."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="malform@example.com", password="Str0ng-Example-Pass!"
        )

    def _assert_401(self, token_value):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_value}")
        response = self.client.get(ME_URL)
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
            f"Expected 401 for token: {token_value!r}",
        )

    def test_random_string_is_rejected(self):
        self._assert_401("thisisnota.validjwt.token")

    def test_single_segment_is_rejected(self):
        self._assert_401("onlyone")

    def test_two_segment_is_rejected(self):
        self._assert_401("header.payload")

    def test_all_dots_is_rejected(self):
        self._assert_401("...")

    def test_garbage_bytes_are_rejected(self):
        self._assert_401("aaa.bbb.ccc")

    def test_sql_injection_string_is_rejected(self):
        self._assert_401("' OR '1'='1")

    def test_number_is_rejected(self):
        self._assert_401("12345")


class ExpiredAccessTokenRejectedTests(APITestCase):
    """SEC-003: Expired access tokens must be rejected."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="expired@example.com", password="Str0ng-Example-Pass!"
        )

    def test_expired_access_token_returns_401(self):
        """
        Create a token that is already set to expire in the past, then
        verify that the server rejects it with 401.
        """
        # Issue a token then manipulate its expiry to be in the past
        refresh = RefreshToken.for_user(self.user)
        access = refresh.access_token
        # Set expiry to 2 seconds ago
        access.set_exp(lifetime=timedelta(seconds=-2))
        token = str(access)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(ME_URL)
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
            "An expired access token must be rejected with 401.",
        )

    def test_valid_token_after_expiry_patch_is_still_accepted(self):
        """Sanity check: a non-expired token must still be accepted."""
        token = _make_access_token(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(ME_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TamperedTokenRejectedTests(APITestCase):
    """SEC-003: Tokens with invalid signatures or tampered payloads must be rejected."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="tamper@example.com", password="Str0ng-Example-Pass!"
        )

    def test_tampered_signature_is_rejected(self):
        """A JWT whose signature has been altered must be rejected."""
        token = _make_access_token(self.user)
        # Replace the last character of the signature to break it
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tampered}")
        response = self.client.get(ME_URL)
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
            "A token with a tampered signature must be rejected with 401.",
        )

    def test_token_with_wrong_signature_section_is_rejected(self):
        """A JWT whose signature section is replaced entirely must be rejected."""
        token = _make_access_token(self.user)
        parts = token.split(".")
        # Replace signature with an invalid value
        parts[2] = "invalidsignatureXXXXXXXXXXXXXXXXXXXXXXXX"
        tampered = ".".join(parts)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tampered}")
        response = self.client.get(ME_URL)
        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
            "A token with a replaced signature must be rejected with 401.",
        )

    def test_token_from_different_user_cannot_impersonate(self):
        """A token issued for user A must not give access as user B."""
        other_user = User.objects.create_user(
            email="tamper_other@example.com", password="Str0ng-Example-Pass!"
        )
        token_for_other = _make_access_token(other_user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_for_other}")
        response = self.client.get(ME_URL)
        # It's valid but returns the other user's identity — not the test user's
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], other_user.email)
        self.assertNotEqual(response.data["email"], self.user.email)


class TokenRefreshTests(APITestCase):
    """SEC-003: Token refresh must work for valid tokens and fail for invalid ones."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="refresh_test@example.com", password="Str0ng-Example-Pass!"
        )

    def test_valid_refresh_token_returns_new_access_token(self):
        """A valid refresh token submitted to /token/refresh/ must return a new access token."""
        refresh_token = _make_refresh_token(self.user)
        response = self.client.post(
            REFRESH_URL, {"refresh": refresh_token}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_malformed_refresh_token_is_rejected(self):
        """A malformed string sent as a refresh token must be rejected."""
        response = self.client.post(
            REFRESH_URL, {"refresh": "not.a.valid.token"}, format="json"
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
            "Malformed refresh token must be rejected.",
        )

    def test_expired_refresh_token_is_rejected(self):
        """An expired refresh token must be rejected."""
        refresh = RefreshToken.for_user(self.user)
        # Manually expire the refresh token by setting its expiry in the past
        refresh.set_exp(lifetime=timedelta(seconds=-2))
        expired_refresh = str(refresh)
        response = self.client.post(
            REFRESH_URL, {"refresh": expired_refresh}, format="json"
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED],
            "Expired refresh token must be rejected.",
        )

    def test_missing_refresh_token_is_rejected(self):
        """A request to /token/refresh/ with no refresh field must be rejected."""
        response = self.client.post(REFRESH_URL, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_new_access_token_from_refresh_grants_access(self):
        """The new access token obtained via refresh must actually work on /me."""
        refresh_token = _make_refresh_token(self.user)
        refresh_response = self.client.post(
            REFRESH_URL, {"refresh": refresh_token}, format="json"
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        new_access = refresh_response.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {new_access}")
        me_response = self.client.get(ME_URL)
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data["email"], self.user.email)


class ProtectedEndpointTokenValidationTests(APITestCase):
    """SEC-003: Protected endpoints must validate tokens server-side."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="prot_owner@example.com", password="Str0ng-Example-Pass!"
        )
        from .models import Workspace
        self.workspace = Workspace.objects.create(
            name="Protected WS", owner=self.owner
        )
        self.ws_url = f"/api/auth/workspaces/{self.workspace.id}/"

    def test_workspace_endpoint_rejects_missing_token(self):
        """Workspace detail endpoint must reject unauthenticated requests."""
        response = self.client.get(self.ws_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_workspace_endpoint_rejects_expired_token(self):
        """Workspace detail endpoint must reject expired access tokens."""
        refresh = RefreshToken.for_user(self.owner)
        access = refresh.access_token
        access.set_exp(lifetime=timedelta(seconds=-2))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(access)}")
        response = self.client.get(self.ws_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_workspace_endpoint_accepts_valid_token(self):
        """Workspace detail endpoint must accept a valid access token."""
        token = _make_access_token(self.owner)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(self.ws_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
