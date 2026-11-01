# Collaboration, WebSockets and Analytics

This implements Sprint 2 collaboration and analytics on the existing Django REST
Framework, React, PostgreSQL and JWT application. PostgreSQL remains authoritative;
Redis distributes WebSocket events across ASGI workers.

## Start locally

From the repository root run `docker compose up --build` and open
`http://localhost:5173`. Compose starts PostgreSQL, Redis, Daphne and Vite; the
API container applies migrations before starting. Stop it with `docker compose down`.

For a host backend, install `backend/requirements.txt`, start PostgreSQL and Redis,
run `python manage.py migrate`, then run
`daphne -b 127.0.0.1 -p 8000 config.asgi:application` from `backend/`.
`CHANNEL_LAYER_BACKEND=memory` selects an in-process layer for development and
tests; it does not provide cross-process fan-out.

## WebSockets

Connect to `/ws/projects/<project-id>/board/` using subprotocols `t14` and
`bearer.<access-token>`. The ASGI middleware validates the JWT; the consumer
checks workspace membership once per connection. `/ws/notifications/` sends
private notification events only to their recipient.

Task and comment changes publish events after the REST transaction commits. Task
events include the changed task and actor. The browser reconnects with capped
exponential backoff and jitter, retries up to ten times, sends a ping every 25
seconds, and reconnects if a pong is missed for 55 seconds. After reconnect it
reloads tasks, comments and activity from REST to recover saved state. Board edits
use REST requests and report errors while offline.

`CHANNEL_CAPACITY` and `CHANNEL_MESSAGE_EXPIRY` configure the Redis channel layer.

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| GET, POST | `/api/tasks/<task-id>/comments/` | List or create comments; `@email` mentions resolve to active workspace members |
| PATCH, DELETE | `/api/tasks/<task-id>/comments/<comment-id>/` | Author or workspace Owner/Admin edits or deletes |
| GET | `/api/projects/<project-id>/members/search/?q=` | Member suggestions for comment mentions |
| GET | `/api/projects/<project-id>/activity/` | Paginated feed; filters: `user`, `type`, `date_from`, `date_to` |
| GET | `/api/notifications/?unread=1` | Current user's notification inbox |
| POST | `/api/notifications/<id>/read/` | Mark one of the caller's notifications read |
| POST | `/api/notifications/read-all/` | Mark all of the caller's notifications read |
| GET | `/api/notifications/unread-count/` | Current unread count |
| GET | `/api/projects/<project-id>/analytics/` | Aggregated status, priority, assignee, overdue, contributor and daily metrics |

All views require JWT authentication and project/workspace membership. Comment
bodies are stripped of HTML; mentions of non-members are rejected, and duplicate
addresses create one Mention row. Notification rows are scoped to the recipient,
and actors do not receive notifications for their own actions.

## Tests

From `backend/`, run `python manage.py test` against Docker PostgreSQL. For an
isolated local fallback, run
`python manage.py test --settings=config.test_settings`; that uses in-memory
SQLite and Channels. The tests cover permissions, comment sanitation and mentions,
analytics aggregation, activity pagination, WebSocket authentication and event
broadcast.
