# Test Plan — Team 14 Project Management System

## 1. Project Overview
The Team 14 Project Management System is a full-stack, enterprise-grade project management application designed for agile teams. It allows teams to create projects and workspaces, manage backlogs, run sprints, track task dependencies, log work hours, view burndown/velocity analytics, comment on tasks, and collaborate through real-time notifications and task updates.

### Technology Stack
- **Backend**: Django 5.2, Django REST Framework 3.18, Django Channels 4.3 (ASGI with Daphne), SimpleJWT, psycopg 3.
- **Frontend**: React 18, Vite 6, Recharts, Jest 30, Babel.
- **Data & Real-time Layer**: PostgreSQL 16, Redis 7 (channel layer), In-Memory test layer.

---

## 2. Testing Objectives
1. Verify functional compliance across authentication, RBAC, workspace tenancy, project/task lifecycle, backlog, sprints, time-tracking, analytics, and collaboration modules.
2. Validate non-functional security requirements, specifically zero secret leakage in logs, robust Argon2/PBKDF2 password hashing, strict token validation, immediate access revocation, and input sanitization (XSS mitigation).
3. Validate WebSocket real-time event broadcasting and authentication controls.
4. Execute full regression testing across both frontend and backend architectures.
5. Provide reproducible evidence and documentation suitable for academic and enterprise evaluation.

---

## 3. Scope of Testing

### In-Scope
- **Authentication & Authorization**: Registration, login, password complexity, JWT access & refresh lifecycle, workspace member roles (Owner, Admin, Member, Viewer), cross-workspace isolation.
- **Access Control & Revocation**: Immediate token/session rejection upon member deletion, demotion to viewer with instantaneous write blocking.
- **Security & Data Sanitization**: Security event logging format, redaction of sensitive credentials and headers, sanitization of HTML in task/project titles and descriptions via Bleach.
- **Project & Task Management**: Project CRUD, task dependencies (circular dependency blocking), priority, status transitions, story points.
- **Sprint & Backlog Management**: Backlog organization, sprint creation, starting/completing sprints, active sprint uniqueness per project.
- **Time Logging & Reporting**: Assignee work logging, historical tracking, sprint metrics, burndown calculation, velocity trends.
- **Collaboration & Real-Time**: Task comments with @mentions, activity feed, private in-app notifications, WebSocket broadcast with authentication & project-level authorization.
- **Frontend Components & UI Logic**: React planning board, sprint management UI, burndown charts, time log forms, production bundle generation.

### Out-of-Scope
- Physical server deployment / bare-metal hardware benchmarks.
- Third-party OAuth providers (not part of the architecture).

---

## 4. Testing Strategy & Methodology
A multi-layered test pyramid approach is adopted:
1. **Unit & Isolation Testing**:
   - Backend: Django TestCase utilizing isolated in-memory SQLite (`test_settings.py`) and memory channel layer for sub-second deterministic execution.
   - Frontend: Jest with JSDOM and React Testing Library simulating user interactions on React components.
2. **Integration Testing**:
   - End-to-end API flows with SimpleJWT bearer authentication verifying multi-step user workflows (e.g., registration -> workspace creation -> project creation -> task lifecycle -> sprint completion -> reporting).
   - Real-time ASGI WebSocket testing using Channels' `WebsocketCommunicator`.
3. **Security Testing**:
   - Pen-testing style edge cases for authentication bypass, token replay, expired token reuse, cross-tenant resource injection, XSS payload neutralization, and log auditing.
4. **Static Analysis & System Checks**:
   - Django system configuration checks (`manage.py check`).
   - Migration integrity checks (`manage.py makemigrations --check --dry-run`).
   - Ruff static analysis.

---

## 5. Testing Environment
- **Operating System**: Windows (AMD64)
- **Python Version**: Python 3.11.9
- **Node.js Version**: v24.18.0
- **Package Managers**: pip 24.0, npm 11.6.2
- **Test Runners**: Django Test Runner / `coverage.py` 7.17.3, Jest 30.5.2
- **Database Configuration (Test)**: In-Memory SQLite (`:memory:`)
- **Channel Layer (Test)**: `channels.layers.InMemoryChannelLayer`

---

## 6. Tools and Frameworks
| Tool / Framework | Purpose |
|---|---|
| **Django Test Framework** | Backend unit and integration test execution |
| **SimpleJWT / Channels Test** | Token authentication and WebSocket communicator testing |
| **Coverage.py** | Python test coverage measurement |
| **Jest & Testing Library** | Frontend component testing and DOM assertion |
| **Vite** | Frontend production build verification |
| **Ruff** | Python static analysis and linting |

---

## 7. Entry and Exit Criteria

### Entry Criteria
- Source code available and branch initialized.
- Backend dependencies installed in virtual environment.
- Frontend npm dependencies installed and resolved.
- Test settings configured for isolated non-destructive execution.

### Exit Criteria
- 100% of existing backend tests executed and passing.
- 100% of frontend tests executed and passing.
- Frontend production build succeeds without fatal compiler errors.
- Django system checks and migrations checks complete with zero errors.
- Formal QA documentation and raw test evidence generated and archived.

---

## 8. Risks and Limitations
- **External Services**: Redis and PostgreSQL containers are present in Docker Compose; local execution utilizes Django's built-in isolated test architecture (`config.test_settings`) to provide zero side-effects and high reproducibility without depending on running external Docker daemon instances.
- **WebSocket Load**: Heavy multi-client concurrency load testing is reserved for isolated staging environments to prevent thread exhaustion on developer workstations.
