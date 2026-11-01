# Issue #14: Sprint creation and backlog assignment

Implements FR-SPR-02 on top of merged issue #13 (main 68aa1cd6d0a7ea76e827acf1a96a1e6af00dbebf).

## Behavior

- Create a project sprint with a required name, start date, and end date.
- Dates must be valid and end date must be on or after start date. Same-day sprints are allowed.
- Select backlog items when creating a sprint or move them into an existing planned sprint.
- Assignment requires unassigned Backlog tasks from the same project. The entire batch succeeds or fails together.
- Assigned tasks become To Do and disappear from the unassigned backlog; the existing board displays them normally.
- Return unstarted tasks from a planned sprint to the backlog.
- Start a planned sprint only if it contains at least one task (SRS business rule).
- Active sprints cannot accept/remove planning items through these endpoints. Completion and charts are outside this issue.
- Display sprint items, dates, status, total story points, and number of unestimated items.
- Preserve issue #13 estimate editing and workspace role handling. Viewers can read; Owners, Admins, and Members can write.
- All planning mutations use transactions, lock the project first, and lock affected rows to serialize sprint assignment operations.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| POST | /api/v1/sprints/ | Create with project, name, start_date, end_date, optional item_ids |
| GET | /api/v1/projects/{project_id}/sprints/ | List project sprints and assigned items |
| POST | /api/v1/sprints/{sprint_id}/items/ | Assign item_ids to a planned sprint |
| DELETE | /api/v1/sprints/{sprint_id}/items/{task_id}/ | Return an unstarted task to backlog |
| POST | /api/v1/sprints/{sprint_id}/start/ | Start a nonempty planned sprint |

The Task serializer exposes sprint as read-only; use planning endpoints to change membership.
Existing backlog listing now filters both Backlog status and sprint=null.

## Database upgrade

Run `python manage.py migrate`. New migrations:

- sprints.0001_initial: Sprint model and date-range constraint.
- projects.0005_task_sprint: nullable Task.sprint relation.

Keep the existing projects.0004_task_story_points migration. Do not reset the database or remove Docker volumes. Existing tasks acquire a null sprint while retaining estimates and other fields.

## Validation

- 173 backend tests passed with temporary SQLite settings and fast password hashing.
- 12 frontend tests passed, including all four existing issue #13 tests.
- Vite production build passed.
- Migration consistency check passed.
- Upgrade from issue #13 database tested: existing tasks and story points retained.
- Live HTTP flow against Django with SQLite passed: JWT login, role lookup, sprint creation, empty-start rejection, assignment, totals, removal, reassignment, start, and Viewer restriction.
- Browser rendering and PostgreSQL concurrency behavior require local verification; automated browser installation was unavailable in the preparation environment.

## Manual acceptance check

1. Sign in as Owner/Member, open a project, and select Backlog & sprints.
2. Create two backlog items with estimates 5 and 8.
3. Select them; create a sprint with valid dates. Verify 13 points and two items.
4. Verify the unassigned list no longer contains them and the board shows To Do.
5. Return one task to backlog while the sprint is Planned. Reassign it via the destination dropdown.
6. Edit an assigned estimate and verify the sprint total refreshes.
7. Refresh/reopen the project and verify persistence.
8. Create an empty sprint; Start sprint must show a helpful error.
9. Start the nonempty sprint; verify Active status and removal of its planning controls.
10. Check Viewer access and narrow-window layout.
