# Original Test Cases Document (Updated) — Team 14 Project Management System
**Document ID:** PMS-TC-2.0 (Evolution from Initial PMS-TP-1.0 Section 11)  
**Academic Basis:** PES University Jackfruit Mini Project - Software Engineering (UE24CS341A)  
**Standard:** IEEE Std 829-1998 Format Basis

---

## 1. Traceability & Evolution Context
The initial Software Test Plan (`PMS-TP-1.0`, defined in `03_SRS_ARCHITECTURE_TEST/SRS_ARCHITECTURE_TEST.pdf` Section 11, Pages 30–31) outlined ten baseline test cases (`TC-01` to `TC-10`). 

During subsequent agile project implementation sprints, major functional and security components were added:
- **Sprint / Issue #9**: Strong password hashing verification (PBKDF2/Argon2) and complexity validators.
- **Sprint / Issue #10**: Strict viewer read-only permission enforcement across all endpoints.
- **Sprint / Issue #11**: Comprehensive JWT access/refresh token validation and expiration handling.
- **Sprint / Issue #13**: Backlog item ranking and sprint backlog allocation.
- **Sprint / Issue #14**: Sprint lifecycle state management (single active sprint enforcement).
- **Sprint / Issue #15**: Assignee work time logging, immutability, and zero/negative minutes validation.
- **Sprint / Issue #16**: Sprint burndown and velocity reporting calculation and Recharts rendering.
- **Sprint / Issue #21**: Input sanitization and XSS mitigation via Bleach HTML whitelist.
- **Sprint / Issue #22**: Immediate access revocation upon workspace membership removal or demotion.
- **Sprint / Issue #23**: Security event logging, brute-force auditing, and strict secret redaction.

This document updates the original test case catalog to preserve the initial 10 baseline cases while expanding them to incorporate all sprint additions.

---

## 2. Master Test Cases Specification (Baseline & Sprint Additions)

| Test ID | Module / Requirement | Test Objective / Scenario | Preconditions | Key Steps | Expected Result | Actual Result | Status |
|---|---|---|---|---|---|---|---|
| **TC-01** | FR-AUTH-01 | Register with a unique email succeeds *(Original IEEE 829 Baseline)* | Application available; email not registered | 1. Submit registration form with valid, unused email and password | 201 Created; account created; tokens and user profile returned | 201 Created with tokens & profile | **PASS** |
| **TC-02** | FR-AUTH-01 | Login returns an auth token *(Original IEEE 829 Baseline)* | Registered account exists | 1. Submit valid credentials to login endpoint | 200 OK with valid JWT access and refresh tokens | 200 OK with valid tokens | **PASS** |
| **TC-03** | FR-AUTH-04 / SEC-002 | Viewer cannot create a task *(Original IEEE 829 Baseline)* | Logged in as a Viewer on existing project | 1. Attempt POST `/api/v1/projects/{id}/tasks` as Viewer | 403 Forbidden; no task row created in database | 403 Forbidden returned | **PASS** |
| **TC-04** | FR-TASK-02 | Create and assign a task *(Original IEEE 829 Baseline)* | Logged in as Member; project exists | 1. Create a task with details and assignee | Task created; assignee set correctly | 201 Created & assigned | **PASS** |
| **TC-05** | FR-TASK-03 / FR-RTC-01 | Task move updates board and broadcasts live *(Original IEEE 829 Baseline)* | Two clients connected to same project board | 1. Client A drags task to new column<br>2. Observe Client B | Client A sees new column; Client B receives WebSocket update without manual refresh | Instant broadcast received on Client B | **PASS** |
| **TC-06** | FR-TASK-04 | Cyclic task dependency is rejected *(Original IEEE 829 Baseline)* | Two tasks A and B exist; A depends on B | 1. Attempt to make B depend on A | 400 Bad Request with cyclic-dependency error; no dependency saved | 400 Bad Request returned | **PASS** |
| **TC-07** | FR-SPR-01 / FR-SPR-02 | Backlog item moves into a sprint with points *(Original IEEE 829 Baseline)* | Backlog has at least one item | 1. Create a sprint<br>2. Move backlog item with story points into it | Sprint created; item associated with sprint; points count toward sprint total | Associated with sprint points counted | **PASS** |
| **TC-08** | FR-RTC-02 / FR-RTC-03 | Comment with mention triggers a notification *(Original IEEE 829 Baseline)* | Task exists; two members on project | 1. Member A comments on task mentioning Member B (`@username`) | Comment saved in activity feed; Member B receives in-app private notification | Saved and notified | **PASS** |
| **TC-09** | NFR-001 / NFR-006 | Task board responds within budget under load *(Original IEEE 829 Baseline)* | 50 simulated concurrent users on project | 1. Issue concurrent GET requests to task board endpoint | 95% of requests complete within 2s; no dropped connections | Response within performance budget | **PASS** |
| **TC-10** | NFR-004 | No task data lost on WebSocket disconnect *(Original IEEE 829 Baseline)* | Client connected; task update in flight | 1. Disconnect client mid-update<br>2. Reconnect and reload board | Task latest status (committed to DB) shown correctly after reconnect | State cleanly retrieved | **PASS** |
| **TC-11** | SEC-001 / Issue #9 | Password hashing algorithm and salt entropy | User registration flow | 1. Register user<br>2. Inspect database `password` field directly | Hash starts with `pbkdf2_sha256$` or `argon2`; plaintext never stored | Secure hash verified | **PASS** |
| **TC-12** | SEC-003 / Issue #11 | JWT access token expiration enforcement | Expired token | 1. Send API request with expired access token header | 401 Unauthorized; `token_not_valid` code returned | 401 Unauthorized | **PASS** |
| **TC-13** | SEC-004 / Issue #11 | Refresh token rotation and blacklist | Valid refresh token | 1. Call `/api/v1/auth/token/refresh/`<br>2. Re-attempt with old refresh token | First returns new access token; reused refresh token is rejected | Token rotation enforced | **PASS** |
| **TC-14** | SEC-002 / Issue #10 | Viewer write lock on sprints, comments, time-logging | Viewer role in workspace | 1. Attempt POST to sprints, comments, and time-logging endpoints | All mutation verbs return 403 Forbidden | 403 Forbidden across all endpoints | **PASS** |
| **TC-15** | SEC-005 / Issue #22 | Immediate access revocation upon membership removal | Member authenticated | 1. Owner deletes membership<br>2. Removed user immediately calls API with valid token | Immediate 403 Forbidden returned without waiting for token expiration | Immediate 403 Forbidden | **PASS** |
| **TC-16** | SEC-006 / Issue #23 | Security audit logging and secret redaction | Invalid login / unauthorized call | 1. Trigger failed login and unauthorized access<br>2. Inspect log outputs | Security events logged; passwords, tokens, and Authorization headers redacted | Logged with zero secret leakage | **PASS** |
| **TC-17** | SEC-006 / Issue #23 | Logging subsystem failure resilience | Logging mock failure | 1. Simulate logger error during login failure | Auth error response returned safely without 500 internal server crash | Graceful error handled | **PASS** |
| **TC-18** | FR-SEC-01 / Issue #21 | Input sanitization against stored XSS | Authenticated user | 1. Submit project/task title containing `<script>alert('xss')</script>` | Dangerous HTML stripped/escaped via Bleach; safe text stored | Cleanly sanitized | **PASS** |
| **TC-19** | FR-SPR-02 / Issue #14 | Single active sprint enforcement | Active sprint exists | 1. Attempt to start a second sprint in same project | 400 Bad Request; only one active sprint allowed at a time | 400 Bad Request returned | **PASS** |
| **TC-20** | FR-SPR-02 / Issue #14 | Sprint completion and incomplete task rollover | Active sprint with open tasks | 1. Complete active sprint | Sprint marked `COMPLETED`; open tasks rollover to backlog | Tasks rolled over cleanly | **PASS** |
| **TC-21** | FR-SPR-03 / Issue #15 | Assignee-only work time logging | Task assigned to Member A | 1. Member A logs work minutes<br>2. Unassigned Member B attempts to log minutes | Member A's time logged (201 Created); Member B rejected (403 Forbidden) | Permitted for assignee only | **PASS** |
| **TC-22** | FR-SPR-03 / Issue #15 | Zero and negative minutes logging validation | Task assignee authenticated | 1. Submit time entry with `minutes: 0` or `minutes: -15` | 400 Bad Request validation error | 400 Bad Request returned | **PASS** |
| **TC-23** | FR-SPR-04 / Issue #16 | Burndown and velocity calculation | Sprints with completed story points | 1. GET `/api/v1/sprints/{id}/burndown/`<br>2. GET `/api/v1/projects/{id}/velocity/` | Ideal burn line and actual daily remaining points returned; velocity trend returned | Accurate reporting data returned | **PASS** |
| **TC-24** | FR-UI-01 / Issue #14 | Frontend planning board sprint drag & drop | React client running | 1. Mount `<Planning />`<br>2. Move card between backlog and sprint | DOM updates, API called, points dynamically recalculated | Component UI flow verified | **PASS** |
| **TC-25** | FR-UI-02 / Issue #16 | Frontend Recharts burndown & velocity rendering | React client running | 1. Mount `<SprintCharts />` with sprint metrics | Recharts SVG paths and velocity bars rendered in DOM without errors | Charts render cleanly | **PASS** |

---

## 3. Summary of Sprint Updates
All 25 test cases (10 original baseline cases + 15 sprint additions) were verified against the automated test suites, resulting in a **100% pass rate**.
