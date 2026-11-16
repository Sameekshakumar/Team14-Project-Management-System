# System Validation Report — Team 14 Project Management System
**Document ID:** PMS-SVR-1.0  
**Academic Basis:** PES University Jackfruit Mini Project - Software Engineering (UE24CS341A)  
**Execution Date:** 2026-11-14

---

## 1. Executive Summary
This System Validation Report documents end-to-end integration workflows, cross-module communication, real-time WebSocket protocol handling, production builds, and architectural security validation against the system requirements outlined in the Software Requirements Specification (SRS v1.0).

---

## 2. Integrated Workflows Verified

### Flow 1: Complete User Lifecycle & Tenancy Validation
1. **Registration & JWT Issuance**: New user submits registration payload; system validates unique email, hashes password, saves to database, and issues valid access and refresh tokens.
2. **Workspace Creation & Role Assignment**: User creates a Workspace (assigned `Owner` role); invites a new member as `Member` and another as `Viewer`.
3. **Cross-Workspace Tenancy Boundary**: Non-member access attempts to the workspace return HTTP 403/404, validating strict multi-tenant isolation.
4. **Immediate Access Revocation**: Owner removes a member. The removed user immediately receives HTTP 403 Forbidden on their next API request using their existing JWT token.

### Flow 2: Project, Task & Agile Sprint Orchestration
1. **Project & Task Creation**: Project created under workspace; tasks added with story points, priority, and assignees.
2. **Circular Dependency Prevention**: Adding a dependency where Task A depends on Task B and Task B depends on Task A is rejected with a 400 Bad Request cycle error.
3. **Sprint Lifecycle**: Sprint created; backlog items allocated to sprint; sprint transition from `PLANNING` to `ACTIVE`. Multiple simultaneous active sprints in the same project are rejected.
4. **Sprint Completion & Backlog Rollover**: Sprint completed; unfinished tasks automatically roll over to the product backlog.

### Flow 3: Work Time Tracking & Metrics Integrity
1. **Assignee Time Logging**: Task assignee logs work minutes with notes; task's aggregated work time updates automatically.
2. **Permission Boundary**: Non-assignees and Viewers attempting to log time are rejected with HTTP 403 Forbidden.
3. **Data Integrity**: Submissions with zero or negative minutes are rejected with HTTP 400 validation errors.
4. **Analytics & Burndown Calculation**: Daily ideal line and actual remaining points computed accurately; velocity across completed sprints aggregated accurately.

### Flow 4: Real-Time WebSocket Collaboration & Notifications
1. **WebSocket Handshake Authentication**: Client connects to `/ws/projects/{project_id}/` passing JWT token; connection is validated and accepted.
2. **Project Authorization Check**: Unauthenticated clients and users who are not project members are rejected during handshake (connection closed 4001/4003).
3. **Live Task Update Broadcasting**: When User A updates a task status via REST API, the Channels consumer broadcasts a `task_updated` message to all connected project members via the Redis/In-Memory channel layer.
4. **Mentions & Activity Feed**: When User A comments on a task mentioning `@UserB`, comment is logged to the project activity feed and a private in-app notification is delivered to User B.

---

## 3. System Integrity & Build Validation

| Validation Check | Tool / Mechanism | Result | Status |
|---|---|---|---|
| **Django System Checks** | `manage.py check` | 0 issues identified, 0 silenced | **PASS** |
| **Database Migration Integrity** | `manage.py makemigrations --check --dry-run` | No uncommitted model changes; schema in sync | **PASS** |
| **Frontend Production Build** | `vite build` | 656 modules transformed, production assets compiled in 5.59s | **PASS** |
| **Docker Compose Services** | `docker-compose.yml` inspection | PostgreSQL (16), Redis (7-alpine), Daphne backend, Vite frontend services defined | **PASS** |

---

## 4. Evidence References
- System Check Evidence: `docs/evidence/django_check_output.txt`
- Migrations Integrity Evidence: `docs/evidence/django_migrations_check.txt`
- Frontend Build Evidence: `docs/evidence/frontend_build_output.txt`
- Backend Execution Evidence: `docs/evidence/backend_test_output.txt`
