from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

User = get_user_model()


class RegistrationLoginTests(APITestCase):
    def setUp(self):
        self.register_url = "/api/auth/register/"
        self.login_url = "/api/auth/login/"
        self.valid_payload = {"email": "samarth@example.com", "password": "Str0ng-Example-Pass!"}

    def test_registration_creates_user_and_returns_tokens(self):
        response = self.client.post(self.register_url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertTrue(User.objects.filter(email="samarth@example.com").exists())
        user = User.objects.get(email="samarth@example.com")
        self.assertTrue(user.check_password(self.valid_payload["password"]))
        self.assertNotEqual(user.password, self.valid_payload["password"])
        self.assertNotIn("password", response.data["user"])

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.client.post(self.register_url, self.valid_payload, format="json")
        response = self.client.post(
            self.register_url,
            {"email": "SAMARTH@example.com", "password": "Another-Strong-Pass!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_returns_tokens_for_valid_credentials(self):
        User.objects.create_user(email="samarth@example.com", password=self.valid_payload["password"])
        response = self.client.post(self.login_url, self.valid_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_rejects_wrong_password(self):
        User.objects.create_user(email="samarth@example.com", password=self.valid_payload["password"])
        response = self.client.post(
            self.login_url,
            {"email": "samarth@example.com", "password": "Wrong-password!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("access", response.data)

    def test_registration_rejects_invalid_email(self):
        response = self.client.post(
            self.register_url,
            {"email": "not-an-email", "password": "Str0ng-Example-Pass!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
