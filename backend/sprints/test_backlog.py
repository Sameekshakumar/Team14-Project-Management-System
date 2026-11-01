from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from accounts.models import Workspace, WorkspaceMembership
from projects.models import Project, Task


class BacklogTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(email='owner@test.test', password='Strong!Pass123')
        self.member = User.objects.create_user(email='member@test.test')
        self.viewer = User.objects.create_user(email='viewer@test.test')
        self.outsider = User.objects.create_user(email='outside@test.test')
        self.workspace = Workspace.objects.create(name='Team14', owner=self.owner)
        for user, role in [(self.member, 'Member'), (self.viewer, 'Viewer')]:
            WorkspaceMembership.objects.create(user=user, workspace=self.workspace, role=role)
        self.project = Project.objects.create(name='Demo', workspace=self.workspace)
        self.url = f'/api/v1/projects/{self.project.pk}/backlog-items/'
        self.client.force_authenticate(self.member)

    def test_create_persists_and_shares_task_board(self):
        response = self.client.post(self.url, {'title': '  Login  ', 'story_points': 5}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        task = Task.objects.get(pk=response.data['id'])
        self.assertEqual((task.title, task.status, task.story_points), ('Login', 'Backlog', 5))
        board = self.client.get(f'/api/projects/{self.project.pk}/tasks/')
        self.assertEqual(board.data[0]['id'], str(task.pk))
        self.assertEqual(len(self.client.get(self.url).data), 1)

    def test_optional_zero_and_invalid_estimates(self):
        for value in [None, 0, 8]:
            self.assertEqual(self.client.post(self.url, {'title': 'Valid', 'story_points': value}, format='json').status_code, 201)
        for value in [-1, 1.5, 'bad', 2147483648]:
            response = self.client.post(self.url, {'title': 'Invalid', 'story_points': value}, format='json')
            self.assertEqual(response.status_code, 400)
            self.assertIn('error', response.data)
        for title in ['', '   ', 'x'*151]:
            self.assertEqual(self.client.post(self.url, {'title': title}, format='json').status_code, 400)

    def test_estimate_edit_and_clear(self):
        task = Task.objects.create(project=self.project, title='Estimate', status='Backlog')
        for value in [3, None]:
            self.assertEqual(self.client.patch(f'/api/tasks/{task.pk}/', {'story_points': value}, format='json').status_code, 200)
            task.refresh_from_db()
            self.assertEqual(task.story_points, value)

    def test_roles_and_immediate_removal(self):
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, {'title': 'No'}, format='json').status_code, 403)
        task = Task.objects.create(project=self.project, title='Protected')
        self.assertEqual(self.client.patch(f'/api/tasks/{task.pk}/', {'story_points': 8}, format='json').status_code, 403)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        WorkspaceMembership.objects.filter(user=self.member).delete()
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_auth_and_filter(self):
        Task.objects.create(project=self.project, title='Not backlog', status='Done')
        self.assertEqual(self.client.get(self.url).data, [])
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid')
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_workspace_list_exposes_actual_roles(self):
        for user, role in [(self.owner, 'Owner'), (self.member, 'Member'), (self.viewer, 'Viewer')]:
            self.client.force_authenticate(user)
            response = self.client.get('/api/auth/workspaces/')
            self.assertEqual(response.status_code, 200)
            workspace = next(w for w in response.data if w['id'] == str(self.workspace.pk))
            self.assertEqual(workspace['current_user_role'], role)

    def test_workspace_create_returns_owner_role(self):
        response = self.client.post('/api/auth/workspaces/', {'name': 'New workspace'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['current_user_role'], 'Owner')

    def test_authenticated_api_flow_matches_planning_contract(self):
        # Real JWT login and the exact requests made by the planning UI.
        self.client.force_authenticate(None)
        login = self.client.post('/api/auth/login/', {'email': self.owner.email, 'password': 'Strong!Pass123'}, format='json')
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+login.data['access'])
        workspaces = self.client.get('/api/auth/workspaces/')
        self.assertEqual(workspaces.data[0]['current_user_role'], 'Owner')
        created = self.client.post(self.url, {'title': 'Login UI', 'story_points': 5}, format='json')
        self.assertEqual(created.status_code, 201)
        tid = created.data['id']
        edited = self.client.patch(f'/api/tasks/{tid}/', {'story_points': 8}, format='json')
        self.assertEqual(edited.status_code, 200)
        fetched = self.client.get(self.url)
        self.assertEqual(fetched.data[0]['story_points'], 8)
