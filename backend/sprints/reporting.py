"""Daily observations, not reconstructed history from current task state."""
from datetime import timedelta
from math import ceil
from django.db import transaction
from django.utils import timezone
from projects.models import Task
from .models import Sprint, SprintDailySnapshot


def point_totals(sprint):
    rows = list(sprint.items.values_list('story_points', 'status'))
    total = sum(points or 0 for points, _ in rows)
    completed = sum(points or 0 for points, status in rows if status == Task.STATUS_DONE)
    return {'total_points': total, 'remaining_points': total - completed,
            'completed_points': completed, 'unestimated_count': sum(points is None for points, _ in rows)}


@transaction.atomic
def capture_snapshot(sprint_id):
    # API callers hold the project lock before writing tasks or sprint state.
    sprint = Sprint.objects.select_for_update().filter(pk=sprint_id).first()
    if sprint is None or sprint.status != 'Active':
        return None
    snapshot, _ = SprintDailySnapshot.objects.update_or_create(
        sprint=sprint, date=timezone.localdate(), defaults=point_totals(sprint))
    return snapshot


def burndown_data(sprint):
    snapshots = list(sprint.daily_snapshots.all())
    today = timezone.localdate()
    last_observed = timezone.localdate(sprint.completed_at) if sprint.completed_at else today
    first = snapshots[0].date if snapshots else None
    points = []
    if first:
        begin = min(sprint.start_date, first)
        end = max(sprint.end_date, last_observed, snapshots[-1].date)
        span = (end - begin).days
        # Bound empty calendar sampling for unusually long sprint ranges.
        step = max(1, ceil(max(span, 1) / 365))
        dates = {begin + timedelta(days=offset) for offset in range(0, span + 1, step)}
        dates.update([begin, end, first, last_observed])
        dates.update(row.date for row in snapshots)
        observed = None
        index = 0
        duration = max(1, (sprint.end_date - sprint.start_date).days)
        for day in sorted(dates):
            while index < len(snapshots) and snapshots[index].date <= day:
                observed = snapshots[index]
                index += 1
            remaining = observed.remaining_points if observed and day <= last_observed else None
            ideal = None
            if sprint.committed_story_points is not None:
                fraction = max(0, min(1, (day - sprint.start_date).days / duration))
                # A same-day sprint reaches its target on that date.
                if sprint.start_date == sprint.end_date and day >= sprint.end_date:
                    fraction = 1
                ideal = round(sprint.committed_story_points * (1 - fraction), 2)
            points.append({'date': day.isoformat(), 'remaining_points': remaining, 'ideal_points': ideal})
    current = point_totals(sprint)
    if sprint.status == 'Completed' and snapshots:
        last = snapshots[-1]
        current = {key: getattr(last, key) for key in current}
    return {
        'sprint': str(sprint.pk), 'name': sprint.name, 'status': sprint.status,
        'start_date': sprint.start_date, 'end_date': sprint.end_date,
        'history_available_from': first, 'committed_story_points': sprint.committed_story_points,
        'current': current, 'points': points,
    }
