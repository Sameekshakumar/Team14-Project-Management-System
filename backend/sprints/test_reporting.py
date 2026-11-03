from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase
from accounts.models import Workspace, WorkspaceMembership
from projects.models import Project, Task
from .models import Sprint, SprintDailySnapshot
from .reporting import capture_snapshot


class ReportingTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(email='charts-owner@test.test')
        self.member = User.objects.create_user(email='charts-member@test.test')
        self.viewer = User.objects.create_user(email='charts-viewer@test.test')
        self.outsider = User.objects.create_user(email='charts-outside@test.test')
        self.workspace = Workspace.objects.create(name='Charts', owner=self.owner)
        for user, role in [(self.member, 'Member'), (self.viewer, 'Viewer')]:
            WorkspaceMembership.objects.create(user=user, workspace=self.workspace, role=role)
        self.project = Project.objects.create(name='Charts', workspace=self.workspace)
        self.today = timezone.localdate()
        self.sprint = Sprint.objects.create(project=self.project, name='Sprint 1', start_date=self.today, end_date=self.today+timedelta(days=7))
        self.first = Task.objects.create(project=self.project, sprint=self.sprint, title='First', story_points=5, status='To Do')
        self.second = Task.objects.create(project=self.project, sprint=self.sprint, title='Second', story_points=8, status='To Do')
        self.base = f'/api/v1/sprints/{self.sprint.pk}'
        self.velocity_url = f'/api/v1/projects/{self.project.pk}/velocity/'
        self.client.force_authenticate(self.member)

    def start(self):
        r = self.client.post(self.base+'/start/')
        self.assertEqual(r.status_code, 200, r.data)
        return r

    def update(self, task, **fields):
        r = self.client.patch(f'/api/tasks/{task.pk}/', fields, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        return r

    def chart(self):
        r = self.client.get(self.base+'/burndown/')
        self.assertEqual(r.status_code, 200, r.data)
        return r.data

    def test_start_status_estimate_and_reopen_recalculate(self):
        self.assertEqual(self.start().data['committed_story_points'], 13)
        self.assertEqual(self.chart()['current']['remaining_points'], 13)
        self.update(self.first, status='Done')
        self.assertEqual(self.chart()['current']['remaining_points'], 8)
        self.update(self.second, story_points=3)
        self.assertEqual(self.chart()['current']['remaining_points'], 3)
        self.update(self.first, status='In Progress')
        data = self.chart()
        self.assertEqual(data['current']['remaining_points'], 8)
        self.assertEqual(data['committed_story_points'], 13)
        self.assertEqual(SprintDailySnapshot.objects.count(), 1)
        self.assertEqual(data['points'][0]['ideal_points'], 13)
        self.assertEqual(data['points'][-1]['ideal_points'], 0)
        self.assertIsNone(data['points'][-1]['remaining_points'])

    def test_prior_days_preserved_and_inactive_days_carried_forward(self):
        yesterday = self.today-timedelta(days=1)
        self.sprint.start_date = yesterday
        self.sprint.save()
        with patch('sprints.reporting.timezone.localdate', return_value=yesterday):
            self.start()
        self.update(self.first, status='Done')
        points = {p['date']: p for p in self.chart()['points']}
        self.assertEqual(points[yesterday.isoformat()]['remaining_points'], 13)
        self.assertEqual(points[self.today.isoformat()]['remaining_points'], 8)
        self.assertEqual(SprintDailySnapshot.objects.count(), 2)
        with patch('sprints.reporting.timezone.localdate', return_value=self.today+timedelta(days=1)):
            points = {p['date']: p for p in self.chart()['points']}
        self.assertEqual(points[(self.today+timedelta(days=1)).isoformat()]['remaining_points'], 8)

    def test_legacy_history_is_unknown_before_first_observation(self):
        self.sprint.status = 'Active'
        self.sprint.start_date = self.today-timedelta(days=3)
        self.sprint.save()
        capture_snapshot(self.sprint.pk)
        data = self.chart()
        self.assertIsNone(data['committed_story_points'])
        self.assertTrue(all(p['ideal_points'] is None for p in data['points']))
        self.assertIsNone(data['points'][0]['remaining_points'])
        self.assertEqual(data['history_available_from'], self.today)

    def test_completion_freezes_velocity_and_burndown(self):
        self.start()
        self.update(self.first, status='Done')
        self.assertEqual(self.client.get(self.velocity_url).data['sprints'], [])
        r = self.client.post(self.base+'/complete/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['completed_story_points'], 5)
        self.assertEqual(r.data['status'], 'Completed')
        before = self.chart()
        self.update(self.first, story_points=21, status='To Do')
        self.update(self.second, status='Done')
        self.assertEqual(self.chart(), before)
        velocity = self.client.get(self.velocity_url).data
        self.assertEqual(velocity['average_velocity'], 5)
        self.assertEqual(velocity['sprints'][0]['committed_points'], 13)
        self.assertEqual(velocity['sprints'][0]['completed_points'], 5)
        self.assertEqual(self.client.post(self.base+'/complete/').status_code, 409)
        self.assertEqual(self.client.post(self.base+'/start/').status_code, 409)
        self.assertEqual(self.client.delete(self.base+f'/items/{self.second.pk}/').status_code, 409)

    def test_velocity_average_and_project_isolation(self):
        self.start()
        self.update(self.first, status='Done')
        self.client.post(self.base+'/complete/')
        Sprint.objects.create(project=self.project, name='Sprint 2', start_date=self.today, end_date=self.today, status='Completed', completed_story_points=8, completed_at=timezone.now())
        other = Project.objects.create(name='Other', workspace=self.workspace)
        Sprint.objects.create(project=other, name='Foreign', start_date=self.today, end_date=self.today, status='Completed', completed_story_points=99)
        data = self.client.get(self.velocity_url).data
        self.assertEqual(len(data['sprints']), 2)
        self.assertEqual(data['average_velocity'], 6.5)

    def test_planned_empty_and_unknown_estimates(self):
        self.assertEqual(self.chart()['points'], [])
        self.assertEqual(self.client.post(self.base+'/complete/').status_code, 409)
        self.update(self.first, story_points=None)
        self.update(self.second, story_points=0)
        self.start()
        self.assertEqual(self.chart()['current'], {'remaining_points': 0, 'completed_points': 0, 'total_points': 0, 'unestimated_count': 1})
        self.assertEqual(self.client.post(self.base+'/complete/').data['completed_story_points'], 0)

    def test_delete_updates_active_snapshot(self):
        self.start()
        self.assertEqual(self.client.delete(f'/api/tasks/{self.second.pk}/').status_code, 204)
        self.assertEqual(self.chart()['current']['remaining_points'], 5)
        self.assertEqual(self.sprint.daily_snapshots.get().remaining_points, 5)

    def test_cascading_parent_deletion_updates_child_sprint(self):
        parent = Task.objects.create(project=self.project, title='Parent')
        self.second.parent = parent
        self.second.save()
        self.start()
        self.assertEqual(self.client.delete(f'/api/tasks/{parent.pk}/').status_code, 204)
        self.assertEqual(self.sprint.daily_snapshots.get().remaining_points, 5)

    def test_viewer_readonly_and_membership_enforced(self):
        self.start()
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.get(self.base+'/burndown/').status_code, 200)
        self.assertEqual(self.client.get(self.velocity_url).status_code, 200)
        self.assertEqual(self.client.post(self.base+'/complete/').status_code, 403)
        for user in [self.outsider, self.member]:
            WorkspaceMembership.objects.filter(user=self.member).delete()
            self.client.force_authenticate(user)
            for url in [self.base+'/burndown/', self.velocity_url]:
                self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(self.base+'/complete/').status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.base+'/burndown/').status_code, 401)
        self.assertEqual(self.client.get(self.velocity_url).status_code, 401)
        self.assertEqual(self.client.post(self.base+'/complete/').status_code, 401)

    def test_real_jwt_chart_and_complete_flow(self):
        self.owner.set_password('ChartTests!123')
        self.owner.save()
        self.client.force_authenticate(None)
        login = self.client.post('/api/auth/login/', {'email': self.owner.email, 'password': 'ChartTests!123'}, format='json')
        self.assertEqual(login.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer '+login.data['access'])
        self.start()
        self.update(self.second, status='Done')
        self.assertEqual(self.chart()['current']['remaining_points'], 5)
        self.assertEqual(self.client.post(self.base+'/complete/').status_code, 200)
        self.assertEqual(self.client.get(self.velocity_url).data['average_velocity'], 8)


from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ReportingMigrationTests(TransactionTestCase):
    def test_upgrade_seeds_existing_active_sprint_without_rewriting_history(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            before = [node for node in latest if node[0] != 'sprints'] + [('sprints', '0002_timeentry')]
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            User = old.get_model('accounts', 'User')
            Workspace = old.get_model('accounts', 'Workspace')
            Project = old.get_model('projects', 'Project')
            Task = old.get_model('projects', 'Task')
            Sprint = old.get_model('sprints', 'Sprint')
            TimeEntry = old.get_model('sprints', 'TimeEntry')
            user = User.objects.create(email='migration@test.test', password='unused')
            workspace = Workspace.objects.create(name='Existing', owner=user)
            project = Project.objects.create(name='Existing', workspace=workspace)
            today = timezone.localdate()
            sprint = Sprint.objects.create(project=project, name='Old active', status='Active', start_date=today-timedelta(days=3), end_date=today+timedelta(days=4))
            task = Task.objects.create(project=project, sprint=sprint, title='Existing work', story_points=5, status='Done')
            Task.objects.create(project=project, sprint=sprint, title='Unknown estimate', status='To Do')
            entry = TimeEntry.objects.create(task=task, user=user, minutes=45, note='Preserve this')
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            new = executor.loader.project_state(latest).apps
            upgraded = new.get_model('sprints', 'Sprint').objects.get(pk=sprint.pk)
            self.assertIsNone(upgraded.committed_story_points)
            self.assertIsNone(upgraded.started_at)
            snapshots = new.get_model('sprints', 'SprintDailySnapshot').objects.filter(sprint_id=sprint.pk)
            self.assertEqual(snapshots.count(), 1)
            snapshot = snapshots.get()
            self.assertEqual((snapshot.date, snapshot.total_points, snapshot.completed_points, snapshot.remaining_points, snapshot.unestimated_count), (today, 5, 5, 0, 1))
            self.assertEqual(new.get_model('sprints', 'TimeEntry').objects.get(pk=entry.pk).minutes, 45)
            self.assertEqual(new.get_model('projects', 'Task').objects.get(pk=task.pk).title, 'Existing work')
        finally:
            MigrationExecutor(connection).migrate(latest)
