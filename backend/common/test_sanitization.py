"""SEC-003: user input is validated and sanitized before it is processed."""
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import Workspace, WorkspaceMembership
from projects.models import Project, Task

from .validators import MAX_TEXT, sanitize_text

User = get_user_model()


class SanitizeTextTests(APITestCase):
    def test_markup_is_removed(self):
        for raw, expected in [
            ("<script>alert(1)</script>", "alert(1)"),
            ("<img src=x onerror=alert(1)>", ""),
            ("Tom <b>bold</b>", "Tom bold"),
            ("<!-- secret -->visible", "visible"),
        ]:
            self.assertEqual(sanitize_text(raw), expected, raw)

    def test_escaped_markup_cannot_survive_as_live_markup(self):
        # A single unescape would turn this back into a usable <script> tag.
        self.assertEqual(sanitize_text("&lt;script&gt;alert(1)&lt;/script&gt;"), "alert(1)")
        self.assertEqual(sanitize_text("&amp;lt;script&amp;gt;"), "")

    def test_plain_text_is_not_entity_escaped(self):
        # bleach escapes what it keeps; re-saving would otherwise stack
        # another "&amp;" onto the value every time.
        for text in ["R&D sprint", "a < b and b > c", "Tom & Jerry", "100% done"]:
            self.assertEqual(sanitize_text(text), text)
            self.assertEqual(sanitize_text(sanitize_text(text)), text)

    def test_control_characters_and_edge_whitespace_are_removed(self):
        # PostgreSQL rejects NUL in a text column, so this would be a 500.
        self.assertEqual(sanitize_text("nul\x00byte"), "nulbyte")
        self.assertEqual(sanitize_text("bell\x07here"), "bellhere")
        self.assertEqual(sanitize_text("  padded  "), "padded")
        self.assertEqual(sanitize_text("keep\tthe\ntabs"), "keep\tthe\ntabs")


class SanitizedEndpointTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="owner@sec.test", password="StrongPass!234")
        self.workspace = Workspace.objects.create(name="Sec", owner=self.owner)
        WorkspaceMembership.objects.get_or_create(
            workspace=self.workspace, user=self.owner, defaults={"role": "Owner"},
        )
        self.project = Project.objects.create(workspace=self.workspace, name="Sec project")
        self.client.force_authenticate(self.owner)
        self.workspace_url = "/api/auth/workspaces/"
        self.project_url = f"/api/workspaces/{self.workspace.pk}/projects/"
        self.task_url = f"/api/projects/{self.project.pk}/tasks/"

    def test_workspace_name_and_description_are_sanitized(self):
        response = self.client.post(self.workspace_url, {
            "name": "<b>Acme</b> R&D",
            "description": "<script>steal()</script> notes",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        workspace = Workspace.objects.get(pk=response.data["id"])
        self.assertEqual(workspace.name, "Acme R&D")
        self.assertEqual(workspace.description, "steal() notes")

    def test_project_name_and_description_are_sanitized(self):
        response = self.client.post(self.project_url, {
            "name": "<i>Apollo</i>",
            "description": "<script>x</script>plan",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["name"], "Apollo")
        self.assertEqual(response.data["description"], "xplan")

    def test_task_title_and_description_are_sanitized(self):
        response = self.client.post(self.task_url, {
            "title": "<script>alert(1)</script>Ship it",
            "description": "<img src=x onerror=alert(1)>details",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        task = Task.objects.get(pk=response.data["id"])
        self.assertEqual(task.title, "alert(1)Ship it")
        self.assertEqual(task.description, "details")

    def test_input_that_is_only_markup_is_rejected_not_stored_blank(self):
        for url, payload in [
            (self.workspace_url, {"name": "<b></b>"}),
            (self.project_url, {"name": "<img src=x>"}),
            (self.task_url, {"title": "<!-- nothing -->"}),
        ]:
            response = self.client.post(url, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, url)

    def test_free_text_length_is_bounded(self):
        response = self.client.post(self.project_url, {
            "name": "Huge", "description": "x" * (MAX_TEXT + 1),
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("description", response.data)

    def test_nul_byte_in_free_text_is_rejected(self):
        # PostgreSQL raises on NUL in a text column, which would surface as a
        # 500. DRF's CharField catches it first and returns a 400.
        response = self.client.post(self.task_url, {"title": "clean\x00title"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(Task.objects.count(), 0)

    def test_passwords_are_never_sanitized(self):
        # A password is a credential, not display text; stripping markup from
        # it would silently change what the user typed.
        password = "<b>Str0ng&Pass!</b>"
        response = self.client.post("/api/auth/register/", {
            "email": "markup@sec.test", "password": password,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(User.objects.get(email="markup@sec.test").check_password(password))
