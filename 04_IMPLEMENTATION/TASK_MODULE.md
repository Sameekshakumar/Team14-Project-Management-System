# Project & Task Management Module

## Overview

This module implements the Project and Task Management functionality for Team 14's
Project Management System.

**Scope:** Projects within a workspace, tasks with subtasks and assignment, a Kanban
board with drag-and-drop status changes, and task dependencies with cycle detection.

**Related requirements:** FR-TASK-01 to FR-TASK-04, NFR-003, and the SRS 6.5 business
rule on completing blocked tasks.

**Related GitHub issues:** #5, #6, #7, #8, #12

## Technology Stack

- Backend: Django REST Framework (`backend/projects/`)
- Frontend: React with Vite (`frontend/src/`)
- Database: PostgreSQL
- Authentication: JWT, reusing the Auth module's workspace roles

## Data Model

| Model | Purpose |
| --- | --- |
| `Project` | A project inside a workspace. Unique name per workspace. |
| `Task` | A task inside a project. Self-referencing `parent` gives one level of subtasks. |
| `TaskDependency` | Directed edge: `task` cannot be completed until `depends_on` is Done. |

Field widths and the status enum follow the SRS data dictionary: `task_title` is 150
characters and `status` is one of `Backlog`, `To Do`, `In Progress`, `Done`.

## API Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET, POST | `/api/auth/workspaces/` | List or create workspaces |
| GET, POST | `/api/workspaces/<workspace_id>/projects/` | List or create projects |
| GET, PATCH, PUT, DELETE | `/api/workspaces/<workspace_id>/projects/<project_id>/` | Manage one project |
| GET, POST | `/api/projects/<project_id>/tasks/` | List or create tasks |
| GET, PATCH, PUT, DELETE | `/api/tasks/<task_id>/` | Manage one task |
| GET, POST | `/api/tasks/<task_id>/dependencies/` | List or add dependencies |
| DELETE | `/api/tasks/<task_id>/dependencies/<dependency_id>/` | Remove a dependency |

## Role Enforcement

Role is resolved through the Auth module's `get_user_workspace_role()`, so this module
adds no parallel permission system.

| Action | Owner | Admin | Member | Viewer |
| --- | --- | --- | --- | --- |
| View projects, tasks, dependencies | Yes | Yes | Yes | Yes |
| Create or edit projects and tasks | Yes | Yes | Yes | No |
| Add or remove dependencies | Yes | Yes | Yes | No |
| Delete a project | Yes | Yes | No | No |

Non-members receive 403. A project or task belonging to another workspace returns 404
rather than 403, so the API does not disclose that it exists.

## Validation Rules

- Project and task names are trimmed and cannot be empty.
- Project names are unique within a workspace.
- A task may only be assigned to a member of its project's workspace.
- Subtasks are limited to one level; a subtask cannot itself have subtasks.
- A task cannot be its own parent, and a task with subtasks cannot become a subtask.
- `status` accepts only the four SRS values.
- `workspace` and `project` are taken from the URL, never from the request body.

## Dependency Rules (FR-TASK-04)

A dependency is rejected when it would create a cycle. Detection walks the dependency
graph outward from the proposed prerequisite; if the originating task is reachable, the
edge would close a loop. Self-dependencies are additionally blocked by a database
`CheckConstraint`.

Per SRS 6.5, a task cannot be moved to `Done` while any prerequisite is still open. The
error response names the blocking tasks. Blocked tasks may still move between the other
columns.

## Screen Flow (NFR-003)

NFR-003 requires that a new user can create and assign a task in no more than four
primary screens. The implemented flow uses three:

| # | Screen | Component | What happens |
| --- | --- | --- | --- |
| 1 | Sign in / register | `AuthScreen` in `App.jsx` | Registration returns tokens directly, so no separate login step is needed |
| 2 | Workspace & project dashboard | `Dashboard` in `App.jsx` | Both are created here, matching the single dashboard described in SRS 3.1 |
| 3 | Task board | `Board.jsx` | The task is created and assigned in one submit |

`TaskFlowScreenCountTests` walks the API calls these screens make and asserts the count
stays within budget, so the claim is re-checked whenever the flow changes.

## Kanban Board (FR-TASK-03)

Tasks are grouped into the four status columns. Cards are moved with the native HTML5
drag-and-drop events, which avoids adding a drag-and-drop dependency. Each card also
carries a status selector, because native drag-and-drop is pointer-only and the board
must remain operable from the keyboard.

A move is applied optimistically and rolled back if the server rejects it, which is what
happens when a blocked task is dragged to `Done`. Subtasks are listed on their parent
card rather than drawn as separate cards.

## Testing

Run the backend test suite from `backend/` using the project's virtual environment:

```
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test
```

**Latest recorded result: 99 tests passed**, covering authentication and workspaces
(36) plus projects, tasks, dependencies and the screen-count flow (63).

## Known Gaps

- The Kanban board's rendering and the drag gesture itself have not been confirmed in a
  browser; the underlying API calls have been verified end to end.
- `CORS_ALLOWED_ORIGINS` is hard-coded to port 5173. If Vite starts on another port,
  browser requests to the API are blocked.
- `.env.example` specifies `POSTGRES_PORT=5432`, but Docker Compose publishes 5433.
