# Collaboration, WebSockets and Analytics

Sprint 2 collaboration and analytics on the existing Django REST Framework,
React, PostgreSQL and JWT application. PostgreSQL stays authoritative; Redis
distributes WebSocket events across ASGI workers.

**Related requirements:** FR-COL-01 to FR-COL-04, NFR scalability and
reliability targets.
**Related GitHub issues:** #17 real-time board, #18 comments with mentions,
#19 activity feed and notifications, #20 analytics dashboard, #24 WebSocket
reliability, #25 50 concurrent connections.

## Start locally

From the repository root run `docker compose up --build` and open
`http://localhost:5173`. Compose starts PostgreSQL, Redis, Daphne and Vite; the
backend container applies migrations before serving. Stop with
`docker compose down`.

To run the backend on the host instead: install `backend/requirements.txt`,
start PostgreSQL and Redis, run `python manage.py migrate`, then from
`backend/` run `daphne -b 127.0.0.1 -p 8000 config.asgi:application`.
`CHANNEL_LAYER_BACKEND=memory` selects an in-process channel layer for
development and tests — it gives no cross-process fan-out, so use Redis
whenever more than one worker runs.

## WebSockets

Connect to `/ws/projects/<project-id>/board/` with subprotocols `t14` and
`bearer.<access-token>`. The ASGI middleware validates the JWT and the consumer
checks workspace membership once per connection. `/ws/notifications/` delivers
notification events only to their recipient.

Close codes on the project socket:

| Code | Meaning |
| --- | --- |
| 4401 | No valid token |
| 4403 | Authenticated but not a member of the project's workspace |
| 4429 | Connection quota reached |
| 1013 | Server could not complete the join; retry later |

The notification socket only needs a valid token, so it closes with 4401 or
not at all.

Task and comment changes publish events after the REST transaction commits, so
a client never sees an event for a write that later rolled back. Task events
carry the changed task and the actor. The board ignores its own events because
the REST response already updated it.

### Reliability (issue #24)

`frontend/src/useProjectSocket.js` sends a ping every 25s and treats a missing
pong after 10s as a dead link. Reconnects use exponential backoff capped at 30s
with 0.75–1.25x jitter, up to 8 attempts before the UI reports `offline`; the
retry counter resets after 60s of a stable connection. After reconnecting, the
client reloads tasks, comments and activity over REST to recover anything
missed while disconnected. Board edits always go over REST and surface an error
when offline.

### Scalability (issue #25)

Redis sorted-set leases bound concurrent sockets and are shared by every ASGI
worker, so a crashed worker's slots expire instead of leaking — a dead
connection's lease lapses even when `disconnect()` never runs. Tunable via
`WS_MAX_CONNECTIONS_PER_PROJECT` (default 100),
`WS_MAX_CONNECTIONS_PER_USER` (default 50) and
`WS_CONNECTION_LEASE_SECONDS` (default 90). `CHANNEL_CAPACITY` and
`CHANNEL_MESSAGE_EXPIRY` configure the Redis channel layer itself.
`backend/tests/load/load_websockets.py` drives the 50-connection check.

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| GET, POST | `/api/tasks/<task-id>/comments/` | List or create comments; `@email` mentions resolve to active workspace members |
| PATCH, DELETE | `/api/tasks/<task-id>/comments/<comment-id>/` | Author or workspace Owner/Admin edits or deletes |
| GET | `/api/projects/<project-id>/members/search/?q=` | Member suggestions for comment mentions |
| GET | `/api/projects/<project-id>/activity/` | Paginated feed; filters `user`, `type`, `date_from`, `date_to` |
| GET | `/api/projects/<project-id>/context/` | Project name, description and workspace id for the collaboration views |
| GET | `/api/notifications/?unread=true` | Caller's inbox; `unread` accepts `true` or `false` |
| POST | `/api/notifications/<id>/read/` | Mark one of the caller's notifications read |
| POST | `/api/notifications/read-all/` | Mark all of the caller's notifications read |
| GET | `/api/notifications/unread-count/` | Current unread count |
| GET | `/api/projects/<project-id>/analytics/` | Status, priority, assignee, overdue, contributor and daily metrics |

Every view requires JWT authentication plus project/workspace membership.
Mentions of non-members are rejected, and repeating the same address in one
comment creates a single `Mention` row. Notification rows are scoped to their
recipient, and an actor is never notified about their own action.

Comment bodies are sanitized to plain text by the shared SEC-003 control in
`backend/common/validators.py` — see `ISSUE21_INPUT_SANITIZATION.md`. The
module no longer calls `bleach` directly.

Activity and notification lists page 20 at a time (`page_size`, max 100).
Analytics accepts `date_from` and `date_to` as `YYYY-MM-DD` and covers at most
366 days.

## Tests

From `backend/`:

```
python manage.py test collaboration --settings=config.test_settings
```

14 tests covering permissions, comments and mentions, activity pagination and
filters, notification scoping, and WebSocket authentication and broadcast.
Analytics aggregation is covered separately in `projects/test_analytics.py`.
The isolated settings use in-memory SQLite and the in-process channel layer;
drop `--settings` to run against Docker PostgreSQL.
