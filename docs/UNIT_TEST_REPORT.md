# Unit Test Report — Team 14 Project Management System
**Document ID:** PMS-UTR-1.0  
**Academic Basis:** PES University Jackfruit Mini Project - Software Engineering (UE24CS341A)  
**Execution Date:** 2026-11-14

---

## 1. Executive Summary
This Unit Test Report documents the testing of individual modular units, algorithms, models, serializers, validators, and frontend React components across the Team 14 Project Management System.

- **Backend Unit Tests Executed:** 260
- **Backend Unit Tests Passed:** 260
- **Frontend Unit/Component Tests Executed:** 29
- **Frontend Unit/Component Tests Passed:** 29
- **Combined Unit Test Pass Rate:** **100%**

---

## 2. Backend Unit Test Execution Breakdown

### A. Accounts Application Units (`backend/accounts/`)
- **`tests_issue9_password_hashing.py` (12 Tests)**: Tests password validator functions, PBKDF2 iteration counts, Argon2 salt derivation, and rejection of insecure/common passwords.
- **`tests_issue10_viewer_readonly.py` (18 Tests)**: Tests individual permission classes (`IsWorkspaceMember`, `IsProjectMember`, `IsViewerReadOnly`) ensuring read methods return True and write methods return False.
- **`tests_issue11_token_validation.py` (22 Tests)**: Tests JWT token generation functions, token signature verification, token expiration bounds, and claims extraction.
- **`tests_issue22_access_revocation.py` (24 Tests)**: Unit tests for membership revocation signal handlers, token revocation listeners, and instantaneous queryset filtering.
- **`tests_issue23_security_logging.py` (20 Tests)**: Unit tests for `log_security_event()` formatting, dictionary redaction helpers, header masking, and graceful exception handling.
- **`accounts.tests.py` (29 Tests)**: Unit tests on `User`, `Workspace`, `WorkspaceMembership`, and `WorkspaceInvitation` model methods, serializer validations, and slug generators.

### B. Projects Application Units (`backend/projects/`)
- **`projects.tests.py` (38 Tests)**: Tests model methods on `Project`, `Task`, `TaskDependency`, circular dependency detection algorithm, status transition state machine, and priority constraints.
- **`projects.test_analytics.py` (5 Tests)**: Unit tests for mathematical calculations of project completion percentage, overdue task counters, and task priority distribution.

### C. Sprints Application Units (`backend/sprints/`)
- **`sprints.test_backlog.py` (12 Tests)**: Unit tests for backlog ranking sort order, drag-and-drop index reassignment, and backlog serializer validation.
- **`sprints.test_sprints.py` (20 Tests)**: Unit tests for Sprint model date validators, status enum transitions (`PLANNING` -> `ACTIVE` -> `COMPLETED`), and active sprint uniqueness constraints.
- **`sprints.test_time_logging.py` (18 Tests)**: Unit tests for `TimeEntry` model methods, positive-integer minute validations, and assignee verification logic.
- **`sprints.test_reporting.py` (18 Tests)**: Unit tests for burndown data generation algorithms, ideal linear burndown trajectory formula, and velocity point aggregation across completed sprints.

### D. Collaboration Application Units (`backend/collaboration/`)
- **`collaboration.test_comments.py` (5 Tests)**: Unit tests for Comment serializers, regex-based `@username` parser, and comment mention dispatchers.
- **`collaboration.test_activity_notifications.py` (5 Tests)**: Unit tests for `Activity` and `Notification` model creations, read/unread status toggles, and notification payload formatters.

### E. Common Application Units (`backend/common/`)
- **`common.test_sanitization.py` (8 Tests)**: Unit tests for Bleach-based HTML tag sanitizer, attribute whitelist validator, and script tag stripping.

---

## 3. Frontend Unit & Component Test Execution Breakdown (`frontend/src/`)

- **`Planning.test.jsx` (6 Tests)**:
  - Unit tests for column rendering (`Backlog`, `To Do`, `In Progress`, `Done`).
  - Unit tests for task card badge formatting, priority indicators, and empty column states.
- **`Planning.sprints.test.jsx` (9 Tests)**:
  - Component tests for Sprint creation modal form inputs and error banners.
  - Unit tests for date range picker validation and sprint state updates.
- **`SprintCharts.test.jsx` (8 Tests)**:
  - Unit tests for Recharts line chart coordinate mapping and tooltip renderers.
  - Component tests for Velocity bar charts and empty data fallbacks.
- **`TimeLogs.test.jsx` (6 Tests)**:
  - Form validation unit tests: invalid, zero, and negative minute rejections.
  - Component tests for time log history table rows and total duration sum formatting.

---

## 4. Execution Evidence Reference
- Backend Unit Test Raw Log: `docs/evidence/backend_test_output.txt`
- Frontend Unit Test Raw Log: `docs/evidence/frontend_test_and_coverage.txt`
