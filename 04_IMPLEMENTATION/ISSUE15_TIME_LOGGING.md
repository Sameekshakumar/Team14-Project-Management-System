# Issue #15 — Time logging against tasks

Implements FR-SPR-03 on merged issue #14, main commit 04a787698741dc7a1be7d219d26ed854e58b9700.

## Behavior and permissions

- Time logs tab lists project tasks; select a task to view its history and total minutes.
- Record positive whole minutes (1–2147483647) and an optional note (at most 1000 characters).
- User identity, task association and timestamp are server-controlled.
- Only the assigned user or workspace Owner may log time. Projects inherit workspace roles; project created_by does not grant an Owner role.
- Admins may log time only when assigned, unless they are the actual workspace Owner. Viewers cannot write even if assigned.
- Workspace members can read task time history. Outsiders and removed members cannot read or write it.
- Historical entries remain credited to their original author after reassignment. Entries are append-only through this API; edit/delete are outside this issue.
- Logging is independent of task/sprint status, so users can record completed work too.
- No timers, time-entry editing, daily caps, burndown or velocity charts are introduced.

## API

GET /api/v1/tasks/{task_id}/time-entries/
POST /api/v1/tasks/{task_id}/time-entries/

POST body: {"minutes": 30, "note": "Implemented login form"}

GET returns HTTP 200; POST returns HTTP 201. Both return:

- task: task ID
- total_minutes: sum of all entries for the task
- can_log_time: current authenticated user's write permission
- entries: latest-first entries with id, task, user, user_email, minutes, note and created_at

The successful POST returns refreshed history and total in the same response. The frontend uses the backend permission result instead of independently guessing roles. The backend always rechecks permission on write. Writes run in a transaction with a task-row lock.

## Migration

sprints.0002_timeentry creates the TimeEntry model with a positive-minutes database constraint. Run manage.py migrate. Existing issue #13/#14 data is unchanged. No .env or dependency changes are required.

## Validation performed

- 197 backend tests passed using the repository config.test_settings (SQLite and in-memory channel layer), including collaboration and analytics tests.
- 18 frontend tests passed, retaining issue #13/#14 regression tests.
- Vite production build and migration consistency check passed.
- Regression tests cover JWT login, saved entries and cumulative totals.
- Tests cover assignee/Owner access; Admin, Viewer, outsider and removed-member restrictions; reassignment; invalid minutes; spoofed identity; per-task totals; and failed-save UI handling.

PostgreSQL locking and visual browser behavior must still be verified locally.

## Manual acceptance checks

1. Open an existing project and choose Time logs. Select a task.
2. As Owner or assigned user, log 30 minutes with a note, then 45 minutes. Verify 75 minutes (1h 15m) and two entries.
3. Refresh, reopen the project/tab/task, and verify persistence.
4. Select another task; verify totals/history are specific to that task.
5. Zero, negative, fractional or empty minutes must not create an entry.
6. A Viewer can read but cannot add entries. An unassigned Member/Admin cannot add entries; the task assignee can.
7. Confirm Board and Backlog & sprints still work.
