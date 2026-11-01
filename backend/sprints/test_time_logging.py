import uuid
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase
from accounts.models import Workspace, WorkspaceMembership
from projects.models import Project, Task
from .models import TimeEntry


class TimeLoggingTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(email='owner15@example.com', password='TestPass!123')
        self.member = User.objects.create_user(email='member15@example.com', password='TestPass!123')
        self.other = User.objects.create_user(email='other15@example.com')
        self.admin = User.objects.create_user(email='admin15@example.com')
        self.viewer = User.objects.create_user(email='viewer15@example.com')
        self.outsider = User.objects.create_user(email='outside15@example.com')
        self.workspace = Workspace.objects.create(name='Time team', owner=self.owner)
        for user, role in [(self.member, 'Member'), (self.other, 'Member'), (self.admin, 'Admin'), (self.viewer, 'Viewer')]:
            WorkspaceMembership.objects.create(workspace=self.workspace, user=user, role=role)
        self.project = Project.objects.create(name='Time project', workspace=self.workspace, created_by=self.other)
        self.task = Task.objects.create(project=self.project, title='Implement login', assignee=self.member)
        self.url = f'/api/v1/tasks/{self.task.pk}/time-entries/'
        self.client.force_authenticate(self.member)

    def post(self, **data):
        return self.client.post(self.url, data, format='json')

    def test_assignee_records_time_and_total_persists(self):
        first = self.post(minutes=30, note='Implemented form')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data['total_minutes'], 30)
        self.assertEqual(first.data['entries'][0]['user'], self.member.pk)
        self.assertEqual(first.data['entries'][0]['note'], 'Implemented form')
        self.assertEqual(self.post(minutes=45).data['total_minutes'], 75)
        read = self.client.get(self.url)
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.data['total_minutes'], 75)
        self.assertEqual(len(read.data['entries']), 2)
        self.assertTrue(read.data['can_log_time'])

    def test_owner_can_log_unassigned_and_other_users_tasks(self):
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.post(minutes=15).status_code, 201)
        self.task.assignee = None
        self.task.save()
        self.assertEqual(self.post(minutes=5).status_code, 201)
        self.assertTrue(all(e.user_id == self.owner.pk for e in TimeEntry.objects.all()))

    def test_unassigned_member_and_admin_are_readonly(self):
        # Being project creator does not grant the workspace Owner role.
        for user in [self.other, self.admin]:
            self.client.force_authenticate(user)
            self.assertEqual(self.post(minutes=20).status_code, 403)
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.data['can_log_time'])
        self.task.assignee = self.admin
        self.task.save()
        self.assertEqual(self.post(minutes=20).status_code, 201)

    def test_viewer_cannot_write_even_if_assigned(self):
        self.task.assignee = self.viewer
        self.task.save()
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.post(minutes=10).status_code, 403)
        self.assertFalse(self.client.get(self.url).data['can_log_time'])
        self.assertEqual(TimeEntry.objects.count(), 0)

    def test_outsider_removed_member_and_anonymous_denied(self):
        for user in [self.outsider, self.member]:
            WorkspaceMembership.objects.filter(user=self.member).delete()
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.post(minutes=10).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.post(minutes=10).status_code, 401)

    def test_invalid_minutes_and_notes_do_not_create_entries(self):
        for value in [0, -1, 1.5, 'invalid', None, 2147483648, True]:
            response = self.post(minutes=value)
            self.assertEqual(response.status_code, 400, (value, response.data))
        self.assertEqual(self.post().status_code, 400)
        self.assertEqual(self.post(minutes=15, note='x' * 1001).status_code, 400)
        self.assertEqual(TimeEntry.objects.count(), 0)
        self.assertEqual(self.post(minutes=1, note='').status_code, 201)

    def test_identity_task_and_timestamps_cannot_be_spoofed(self):
        other_task = Task.objects.create(project=self.project, title='Other task')
        response = self.post(minutes=10, user=self.owner.pk, task=str(other_task.pk), created_at='2000-01-01T00:00:00Z')
        self.assertEqual(response.status_code, 201)
        entry = TimeEntry.objects.get()
        self.assertEqual(entry.user_id, self.member.pk)
        self.assertEqual(entry.task_id, self.task.pk)
        self.assertNotEqual(entry.created_at.year, 2000)
        self.assertEqual(self.client.get(f'/api/v1/tasks/{other_task.pk}/time-entries/').data['total_minutes'], 0)

    def test_reassignment_revokes_write_and_keeps_history(self):
        self.assertEqual(self.post(minutes=25).status_code, 201)
        self.task.assignee = self.other
        self.task.save()
        self.assertEqual(self.post(minutes=10).status_code, 403)
        self.assertEqual(self.client.get(self.url).data['total_minutes'], 25)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.post(minutes=5).data['total_minutes'], 30)

    def test_missing_task_and_unsupported_mutations(self):
        self.assertEqual(self.client.get(f'/api/v1/tasks/{uuid.uuid4()}/time-entries/').status_code, 404)
        self.post(minutes=15)
        self.assertEqual(self.client.patch(self.url, {'minutes': 20}, format='json').status_code, 405)
        self.assertEqual(self.client.delete(self.url).status_code, 405)
        self.assertEqual(TimeEntry.objects.get().minutes, 15)

    def test_database_rejects_zero_minutes(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TimeEntry.objects.create(task=self.task, user=self.member, minutes=0)

    def test_real_jwt_login_and_time_logging_contract(self):
        self.client.force_authenticate(None)
        login = self.client.post('/api/auth/login/', {'email': self.member.email, 'password': 'TestPass!123'}, format='json')
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + login.data['access'])
        tasks = self.client.get(f'/api/projects/{self.project.pk}/tasks/')
        self.assertEqual(tasks.status_code, 200)
        self.assertEqual(tasks.json()[0]['id'], str(self.task.pk))
        self.assertTrue(self.client.get(self.url).data['can_log_time'])
        self.assertEqual(self.post(minutes=60).data['total_minutes'], 60)
