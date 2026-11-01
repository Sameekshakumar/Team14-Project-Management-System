import uuid
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from accounts.models import Workspace, WorkspaceMembership
from projects.models import Project, Task
from .models import Sprint


class SprintTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(email='owner@test.test')
        self.member = User.objects.create_user(email='member@test.test')
        self.viewer = User.objects.create_user(email='viewer@test.test')
        self.outsider = User.objects.create_user(email='outside@test.test')
        self.workspace = Workspace.objects.create(name='Team14', owner=self.owner)
        for user, role in [(self.member, 'Member'), (self.viewer, 'Viewer')]:
            WorkspaceMembership.objects.create(user=user, workspace=self.workspace, role=role)
        self.project = Project.objects.create(name='Demo', workspace=self.workspace)
        self.other = Project.objects.create(name='Other', workspace=self.workspace)
        self.item = Task.objects.create(project=self.project, title='First', status='Backlog', story_points=5)
        self.client.force_authenticate(self.member)
        self.payload = {'project': str(self.project.pk), 'name': 'Sprint 2', 'start_date': '2026-11-01', 'end_date': '2026-11-14'}

    def create(self, **extra):
        return self.client.post('/api/v1/sprints/', {**self.payload, **extra}, format='json')

    def test_tc07_create_assign_total_and_board(self):
        response = self.create(item_ids=[str(self.item.pk)])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['total_story_points'], 5)
        self.item.refresh_from_db()
        self.assertEqual(str(self.item.sprint_id), response.data['id'])
        self.assertEqual(self.item.status, 'To Do')
        backlog = self.client.get(f'/api/v1/projects/{self.project.pk}/backlog-items/')
        self.assertEqual(backlog.data, [])
        self.client.patch(f'/api/tasks/{self.item.pk}/', {'story_points': 8}, format='json')
        sprints = self.client.get(f'/api/v1/projects/{self.project.pk}/sprints/')
        self.assertEqual(sprints.data[0]['total_story_points'], 8)

    def test_dates_name_and_missing_fields(self):
        for data in [{'end_date': '2026-10-01'}, {'start_date': 'invalid'}, {'name': ' '}, {'name': 'x'*101}]:
            self.assertEqual(self.create(**data).status_code, 400)
        self.assertEqual(self.client.post('/api/v1/sprints/', {}, format='json').status_code, 400)
        self.assertEqual(self.create(end_date='2026-11-01').status_code, 201)

    def test_invalid_batch_rolls_back_creation(self):
        foreign = Task.objects.create(project=self.other, title='Foreign', status='Backlog')
        for ids in [[str(self.item.pk), str(foreign.pk)], [str(self.item.pk), str(uuid.uuid4())], [str(self.item.pk)]*2]:
            response = self.create(item_ids=ids)
            self.assertEqual(response.status_code, 400, response.data)
            self.assertEqual(Sprint.objects.count(), 0)
            self.item.refresh_from_db()
            self.assertIsNone(self.item.sprint_id)

    def test_attach_remove_and_empty_start(self):
        sprint_id = self.create().data['id']
        base = f'/api/v1/sprints/{sprint_id}'
        response = self.client.post(base+'/start/')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['error']['code'], 'empty_sprint')
        self.assertEqual(self.client.post(base+'/items/', {'item_ids': [str(self.item.pk)]}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(base+f'/items/{self.item.pk}/').status_code, 204)
        self.item.refresh_from_db()
        self.assertEqual((self.item.sprint_id, self.item.status), (None, 'Backlog'))
        self.assertEqual(self.client.post(base+'/start/').status_code, 409)

    def test_duplicate_and_non_backlog_rejected(self):
        first = self.create(item_ids=[str(self.item.pk)])
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.create(item_ids=[str(self.item.pk)]).status_code, 400)
        done = Task.objects.create(project=self.project, title='Done', status='Done')
        self.assertEqual(self.create(item_ids=[str(done.pk)]).status_code, 400)
        self.assertEqual(Sprint.objects.count(), 1)

    def test_active_sprint_guards_and_readonly_relation(self):
        sid = self.create(item_ids=[str(self.item.pk)]).data['id']
        base = f'/api/v1/sprints/{sid}'
        self.assertEqual(self.client.post(base+'/start/').status_code, 200)
        self.assertEqual(self.client.post(base+'/start/').status_code, 409)
        self.assertEqual(self.client.delete(base+f'/items/{self.item.pk}/').status_code, 409)
        extra = Task.objects.create(project=self.project, title='Extra', status='Backlog')
        self.assertEqual(self.client.post(base+'/items/', {'item_ids':[str(extra.pk)]}, format='json').status_code, 409)
        self.client.patch(f'/api/tasks/{extra.pk}/', {'sprint': sid}, format='json')
        extra.refresh_from_db()
        self.assertIsNone(extra.sprint_id)

    def test_viewer_outsider_removed_and_unauthenticated(self):
        sid = self.create().data['id']
        base = f'/api/v1/sprints/{sid}'
        list_url = f'/api/v1/projects/{self.project.pk}/sprints/'
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(list_url).status_code, 200)
        self.assertEqual(self.create().status_code, 403)
        self.assertEqual(self.client.post(base+'/items/', {'item_ids': [str(self.item.pk)]}, format='json').status_code, 403)
        self.assertEqual(self.client.delete(base+f'/items/{self.item.pk}/').status_code, 403)
        self.assertEqual(self.client.post(base+'/start/').status_code, 403)
        for user in [self.outsider, self.member]:
            WorkspaceMembership.objects.filter(user=self.member).delete()
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(list_url).status_code, 403)
            self.assertEqual(self.client.post(base+'/start/').status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.create().status_code, 401)

    def test_unestimated_total_and_existing_batch_atomicity(self):
        sid = self.create().data['id']
        base = f'/api/v1/sprints/{sid}'
        unestimated = Task.objects.create(project=self.project, title='Unknown', status='Backlog')
        ids = [str(self.item.pk), str(unestimated.pk)]
        self.assertEqual(self.client.post(base+'/items/', {'item_ids': ids + [str(uuid.uuid4())]}, format='json').status_code, 400)
        self.assertEqual(Sprint.objects.get(pk=sid).items.count(), 0)
        response = self.client.post(base+'/items/', {'item_ids': ids}, format='json')
        self.assertEqual(response.data['total_story_points'], 5)
        self.assertEqual(response.data['unestimated_count'], 1)

    def test_real_login_workspace_role_and_sprint_flow(self):
        self.member.set_password('SprintTest!123')
        self.member.save()
        self.client.force_authenticate(None)
        login = self.client.post('/api/auth/login/', {'email': self.member.email, 'password': 'SprintTest!123'}, format='json')
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + login.data['access'])
        roles = self.client.get('/api/auth/workspaces/')
        self.assertEqual(roles.data[0]['current_user_role'], 'Member')
        created = self.create(item_ids=[str(self.item.pk)])
        self.assertEqual(created.status_code, 201)
        board = self.client.get(f'/api/projects/{self.project.pk}/tasks/')
        self.assertEqual(board.status_code, 200)
        self.assertEqual(board.json()[0]['sprint'], created.data['id'])
        self.assertEqual(board.data[0]['status'], 'To Do')
        self.assertEqual(self.client.post(f"/api/v1/sprints/{created.data['id']}/start/").status_code, 200)

    def test_empty_and_duplicate_assignment_batches_are_rejected(self):
        sid = self.create().data['id']
        for ids in [[], [str(self.item.pk)] * 2]:
            response = self.client.post(f'/api/v1/sprints/{sid}/items/', {'item_ids': ids}, format='json')
            self.assertEqual(response.status_code, 400)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.sprint_id)

    def test_other_workspace_items_cannot_be_assigned(self):
        foreign_workspace = Workspace.objects.create(name='Private', owner=self.outsider)
        foreign_project = Project.objects.create(name='Private project', workspace=foreign_workspace)
        foreign_item = Task.objects.create(project=foreign_project, title='Private item', status='Backlog')
        self.assertEqual(self.create(item_ids=[str(foreign_item.pk)]).status_code, 400)
        self.assertEqual(self.create(project=str(foreign_project.pk)).status_code, 403)
        foreign_item.refresh_from_db()
        self.assertIsNone(foreign_item.sprint_id)
        self.assertEqual(Sprint.objects.count(), 0)
