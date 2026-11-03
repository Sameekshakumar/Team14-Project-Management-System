# Issue #16 — Burndown and velocity charts

Implements FR-SPR-04 on top of main commit `52ec758cc63a136691126aa3e41a4a676176a582` (issue #15 merged).

## Behaviour

The project has a **Sprint charts** tab with a sprint selector, burndown line chart, velocity bar chart, and readable data tables. Reports reload every 15 seconds while mounted, on window focus, and with **Refresh charts**. The chart tab is readable by workspace Owners, Admins, Members and Viewers. The existing backend workspace permissions remain authoritative.

- Remaining story points = estimated points on sprint tasks whose status is not Done.
- Completed points = estimated points on sprint tasks whose status is Done.
- Blank estimates contribute zero and are counted as unestimated tasks.
- Starting a nonempty sprint saves its initial committed points and today's observation.
- Changes to task status or estimates, and task deletions through the existing task API, update today's observation for active sprints in the same transaction. Past days are retained. Days without a change carry forward the last observation; future actuals are unavailable.
- Each date is a daily latest-state observation, not an event-by-event graph. Several changes on one date update one point. The ideal line declines from the initial commitment over the scheduled sprint dates.
- **Complete sprint**, in Backlog & sprints, closes an active sprint and freezes its completed points and final observation. Unfinished tasks remain attached; automatic carryover is outside this issue. Completion requires write permission and confirmation in the UI.
- Velocity includes completed sprints only. Its average is the arithmetic mean of their frozen completed points. Planned and active sprints are excluded. Later task edits do not rewrite closed-sprint reports.
- Existing active sprints receive a current observation during migration. Their original commitment and earlier actual values are unknown, so no historical values or ideal line are invented.

No chart scheduler or new JavaScript dependency is needed. Recharts is already part of main. Direct database/admin edits outside these task endpoints do not capture observations; use the project UI/API to update tasks.

## API

All routes require JWT authentication and workspace membership.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/v1/sprints/<sprint_id>/burndown/` | Daily actual/ideal values, current totals, history start |
| GET | `/api/v1/projects/<project_id>/velocity/` | Completed sprint totals and average velocity |
| POST | `/api/v1/sprints/<sprint_id>/complete/` | Close an active sprint; requires write access |

## Migration

`0003_sprint_reporting` adds four nullable reporting fields to Sprint and the SprintDailySnapshot table, with one snapshot per sprint/date. Its data migration observes existing active sprints without changing tasks or time entries. Run `python manage.py migrate`. Do not delete existing migrations or your PostgreSQL volume.

## Automated verification

- 208 backend tests pass across sprints, projects, accounts and collaboration, including 11 reporting/migration tests.
- 29 frontend tests pass across four suites, including charts and completion controls.
- `npm run build` succeeds. Vite emits a nonblocking bundle-size warning.
- `makemigrations --check --dry-run` detects no missing migration.
- Reporting tests cover status/estimate updates, reopening, deletions, daily history, legacy observations, completion freeze, average velocity, workspace isolation, viewer restrictions, JWT access and migration preservation of tasks/time entries.
- Verification here used SQLite, an in-memory channel layer and fast test password hashing. PostgreSQL/browser integration must also be checked locally with the steps below. Frontend tests mock Recharts layout; the production build uses the real library.

## Local verification

From backend, with the virtual environment active:

```bat
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py test sprints projects accounts collaboration --settings=config.test_settings --noinput
```

For the PostgreSQL integration run, with Docker running and the existing `.env`:

```bat
python manage.py test sprints projects accounts collaboration --noinput
```

From frontend:

```bat
npm ci
npm test
npm run build
npm run dev
```

In another terminal run the backend with `python manage.py runserver`.

1. Sign in as a workspace writer and open a project.
2. Create two new backlog items estimated at 5 and 8 points. Select both and create a sprint, with today as the start and a later end date. Start it.
3. Open Sprint charts, select it, and confirm 13 remaining points and an ideal line from 13 to 0. On the first day, a single actual dot is expected.
4. In Board, mark the 5-point task Done. Reopen Sprint charts or refresh: 8 remaining, 5 completed.
5. In Backlog & sprints change the other estimate from 8 to 3: remaining becomes 3, original commitment stays 13.
6. Reopen the completed task in Board: remaining becomes 8. Mark it Done again: remaining returns to 3.
7. In Backlog & sprints choose Complete sprint and confirm. Velocity now shows 5, not 13 or 8. The unfinished 3-point task remains attached.
8. A second completed sprint with 8 completed points gives an average of 6.5 when these are the project's only completed sprints.
9. A Viewer can read both charts but cannot start or complete sprints. Empty projects and planned sprints show guidance instead of fabricated data.
10. Recheck existing Board, Time logs and notifications before opening the PR.
