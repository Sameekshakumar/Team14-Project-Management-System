# Issue #13: backlog items with story-point estimates

Implements FR-SPR-01. Backlog entries use the existing Task model and board;
no duplicate task table is introduced. Estimates are optional nonnegative
integers. Null means unestimated; zero is valid.

New API: GET/POST /api/v1/projects/{project_id}/backlog-items/.
Estimate updates use PATCH /api/tasks/{task_id}/.

The planning screen imports the existing API client. Both backlog() and
createBacklog() are included. WorkspaceSerializer now returns the real
current_user_role on the LIST endpoint consumed by the UI, not just on the
detail endpoint. Owner/Admin/Member can write; Viewer reads only. Server-side
workspace checks enforce access regardless of UI state.

Migration: projects.0004_task_story_points. It is safe to leave an earlier
application of this same migration in the local development database.
Never delete database volumes to reinstall this feature.

## Verification

Backend: python manage.py test sprints projects accounts --noinput
Frontend: npm test, npm run build
Migration drift: python manage.py makemigrations --check --dry-run

The new tests include real JWT login, the workspace list role contract,
backlog creation, estimate edit/refetch, invalid input and role enforcement.
Frontend component tests exercise creation, edit, Viewer controls and
null-versus-zero estimates.

Manually create an item with 5 points, edit it to 8, refresh, and verify the
same item appears in the existing Kanban Backlog column. Check an unestimated
item and a zero-point item separately.

Issue #14 sprint creation, #15 time logging and #16 charts are not included.
The tab name 'Backlog & sprints' is shared navigation; this package adds only
the backlog screen. Shared Jenkins/Channels/containerization work is outside
this issue.
