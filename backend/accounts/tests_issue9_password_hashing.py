"""
Issue #9 — Password hashing & secure storage (SEC-001)

Tests that:
  - Passwords are stored using Django's supported secure hashing framework.
  - Registered users have their passwords hashed, never stored as plaintext.
  - Valid credentials authenticate successfully.
  - Invalid passwords are rejected.
  - Passwords and password hashes are not returned in any API response.
  - Existing registration and authentication flows continue to work.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher, is_password_usable
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class PasswordHashingStorageTests(APITestCase):
    """SEC-001: Passwords must never be stored as plaintext."""

    REGISTER_URL = "/api/auth/register/"
    LOGIN_URL = "/api/auth/login/"
    PLAINTEXT_PASSWORD = "Str0ng-Example-Pass!"

    def test_registration_stores_hashed_password_not_plaintext(self):
        """Password stored in DB must not equal the original plaintext."""
        response = self.client.post(
            self.REGISTER_URL,
            {"email": "hash_test@example.com", "password": self.PLAINTEXT_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(email="hash_test@example.com")
        # The stored value must differ from the plaintext
        self.assertNotEqual(
            user.password,
            self.PLAINTEXT_PASSWORD,
            "Password must not be stored as plaintext.",
        )

    def test_stored_password_uses_django_supported_hasher(self):
        """Django's identify_hasher must recognise the stored password hash."""
        User.objects.create_user(
            email="hasher_check@example.com", password=self.PLAINTEXT_PASSWORD
        )
        user = User.objects.get(email="hasher_check@example.com")
        # identify_hasher raises ValueError if the hash is not a recognised format
        hasher = identify_hasher(user.password)
        self.assertIsNotNone(hasher, "Password must be stored using a Django-recognised hasher.")

    def test_stored_password_is_usable(self):
        """is_password_usable must return True for a hashed password."""
        User.objects.create_user(
            email="usable@example.com", password=self.PLAINTEXT_PASSWORD
        )
        user = User.objects.get(email="usable@example.com")
        self.assertTrue(
            is_password_usable(user.password),
            "Stored password must be usable (i.e., properly hashed).",
        )

    def test_check_password_validates_correct_password(self):
        """user.check_password must return True for the original password."""
        User.objects.create_user(
            email="check_pass@example.com", password=self.PLAINTEXT_PASSWORD
        )
        user = User.objects.get(email="check_pass@example.com")
        self.assertTrue(
            user.check_password(self.PLAINTEXT_PASSWORD),
            "check_password must return True for the correct plaintext password.",
        )

    def test_check_password_rejects_wrong_password(self):
        """user.check_password must return False for an incorrect password."""
        User.objects.create_user(
            email="wrong_pass@example.com", password=self.PLAINTEXT_PASSWORD
        )
        user = User.objects.get(email="wrong_pass@example.com")
        self.assertFalse(
            user.check_password("WrongPassword123!"),
            "check_password must return False for an incorrect password.",
        )

    def test_two_users_with_same_password_have_different_hashes(self):
        """Different accounts with the same plaintext must have distinct stored hashes."""
        User.objects.create_user(email="user_a@example.com", password=self.PLAINTEXT_PASSWORD)
        User.objects.create_user(email="user_b@example.com", password=self.PLAINTEXT_PASSWORD)
        user_a = User.objects.get(email="user_a@example.com")
        user_b = User.objects.get(email="user_b@example.com")
        self.assertNotEqual(
            user_a.password,
            user_b.password,
            "Two users with the same plaintext password must have different hashes (salt).",
        )


class PasswordNotExposedInAPITests(APITestCase):
    """SEC-001: Passwords and hashes must not appear in any API response."""

    REGISTER_URL = "/api/auth/register/"
    LOGIN_URL = "/api/auth/login/"
    ME_URL = "/api/auth/me/"
    PLAINTEXT_PASSWORD = "Str0ng-Example-Pass!"

    def _register_user(self, email="api_test@example.com"):
        return self.client.post(
            self.REGISTER_URL,
            {"email": email, "password": self.PLAINTEXT_PASSWORD},
            format="json",
        )

    def test_registration_response_does_not_contain_password_field(self):
        """The register endpoint response must not include a 'password' field."""
        response = self._register_user()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotIn(
            "password",
            response.data.get("user", {}),
            "Registration response must not expose the password field.",
        )

    def test_registration_response_does_not_leak_password_hash(self):
        """The register response body must not contain the password hash string."""
        response = self._register_user()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response_str = str(response.data)
        # Retrieve the actual stored hash and ensure it's not in the response
        user = User.objects.get(email="api_test@example.com")
        self.assertNotIn(
            user.password,
            response_str,
            "Registration response must not leak the stored password hash.",
        )

    def test_login_response_does_not_contain_password_field(self):
        """The login endpoint response must not include a 'password' field."""
        User.objects.create_user(
            email="login_nopw@example.com", password=self.PLAINTEXT_PASSWORD
        )
        response = self.client.post(
            self.LOGIN_URL,
            {"email": "login_nopw@example.com", "password": self.PLAINTEXT_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(
            "password",
            response.data,
            "Login response must not expose the password field.",
        )

    def test_me_endpoint_does_not_expose_password(self):
        """The /me endpoint must not include the password or hash."""
        user = User.objects.create_user(
            email="me_nopw@example.com", password=self.PLAINTEXT_PASSWORD
        )
        self.client.force_authenticate(user=user)
        response = self.client.get(self.ME_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(
            "password",
            response.data,
            "/me response must not expose the password field.",
        )


class LoginAuthenticationSecurityTests(APITestCase):
    """SEC-001: Authentication must verify passwords securely."""

    LOGIN_URL = "/api/auth/login/"
    PLAINTEXT_PASSWORD = "Str0ng-Example-Pass!"

    def setUp(self):
        self.user = User.objects.create_user(
            email="auth_user@example.com", password=self.PLAINTEXT_PASSWORD
        )

    def test_valid_credentials_return_tokens(self):
        """Login with correct email and password must return access and refresh tokens."""
        response = self.client.post(
            self.LOGIN_URL,
            {"email": "auth_user@example.com", "password": self.PLAINTEXT_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_wrong_password_is_rejected(self):
        """Login with a wrong password must be rejected with 400."""
        response = self.client.post(
            self.LOGIN_URL,
            {"email": "auth_user@example.com", "password": "WrongPassword!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("access", response.data)

    def test_wrong_email_is_rejected(self):
        """Login with a non-existent email must be rejected with 400."""
        response = self.client.post(
            self.LOGIN_URL,
            {"email": "nobody@example.com", "password": self.PLAINTEXT_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("access", response.data)

    def test_empty_password_is_rejected(self):
        """Login with an empty password must be rejected."""
        response = self.client.post(
            self.LOGIN_URL,
            {"email": "auth_user@example.com", "password": ""},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_followed_by_login_works(self):
        """A freshly registered user must be able to log in immediately."""
        email = "fresh_user@example.com"
        password = "Fr3sh-User-Pass!"
        reg_response = self.client.post(
            "/api/auth/register/",
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(reg_response.status_code, status.HTTP_201_CREATED)

        login_response = self.client.post(
            self.LOGIN_URL,
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", login_response.data)
