from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView
from projects.models import Project
from projects.permissions import require_member
from .exceptions import SprintErrorsMixin
from .models import Sprint
from .reporting import burndown_data, capture_snapshot
from .serializers import SprintSerializer
from .services import SprintConflict
from .views import locked_sprint


class SprintBurndownView(SprintErrorsMixin, APIView):
    def get(self, request, sprint_id):
        sprint = get_object_or_404(Sprint.objects.select_related('project__workspace'), pk=sprint_id)
        require_member(request.user, sprint.project.workspace)
        return Response(burndown_data(sprint))


class ProjectVelocityView(SprintErrorsMixin, APIView):
    def get(self, request, project_id):
        project = get_object_or_404(Project.objects.select_related('workspace'), pk=project_id)
        require_member(request.user, project.workspace)
        sprints = Sprint.objects.filter(project=project, status='Completed').order_by('completed_at', 'id')
        rows = [{'sprint': str(s.pk), 'name': s.name, 'completed_at': s.completed_at,
                 'committed_points': s.committed_story_points,
                 'completed_points': s.completed_story_points or 0} for s in sprints]
        return Response({'sprints': rows, 'average_velocity': round(sum(r['completed_points'] for r in rows) / len(rows), 2) if rows else 0})


class SprintCompleteView(SprintErrorsMixin, APIView):
    @transaction.atomic
    def post(self, request, sprint_id):
        sprint = locked_sprint(request.user, sprint_id)
        if sprint.status != 'Active':
            raise SprintConflict('Only an active sprint can be completed.')
        snapshot = capture_snapshot(sprint.pk)
        sprint.completed_story_points = snapshot.completed_points
        sprint.completed_at = timezone.now()
        sprint.status = 'Completed'
        sprint.save(update_fields=['status', 'completed_at', 'completed_story_points'])
        return Response(SprintSerializer(sprint).data)
