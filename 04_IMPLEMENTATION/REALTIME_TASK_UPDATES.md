# Real-time task board updates

The task API remains the source of truth. After a task is created, edited,
moved, assigned, or deleted, the backend broadcasts a compact event to the
project's connected workspace members. The board reloads its task list when it
receives another member's event and ignores its own event because its REST
response already updated the board.

## Run the ASGI server

Install `backend/requirements.txt`, configure the PostgreSQL variables from
`.env.example`, then start the backend from `backend/`:

```sh
python manage.py migrate
daphne -b 127.0.0.1 -p 8000 config.asgi:application
```

In debug mode the channel layer uses in-memory channels, which is enough for a
single local server process. The Compose backend runs Daphne with the Redis
channel layer so multiple ASGI workers can deliver the same project events.
Configure channel capacity and message expiry with `CHANNEL_CAPACITY` and
`CHANNEL_MESSAGE_EXPIRY`.

## Connection limits and load test

Redis also holds expiring connection leases so a crashed ASGI worker does not
permanently consume a connection slot. `WS_MAX_CONNECTIONS_PER_PROJECT`
defaults to 100, `WS_MAX_CONNECTIONS_PER_USER` defaults to 50, and
`WS_CONNECTION_LEASE_SECONDS` defaults to 90. The browser refreshes its lease
with each 25-second heartbeat. A connection refused by either limit closes
with WebSocket code 4429. In-memory development and tests bypass distributed
quotas.

Start the database, Redis, and ASGI backend from the repository root:

```sh
docker compose up -d --build db redis backend
```

Run the load test from `backend/` after creating a project task and an access
token for a workspace member. The task is temporarily renamed and then restored.
Set `PROJECT_ID`, `TASK_ID`, and `ACCESS_TOKEN` for 50 sockets using one member,
or provide `ACCESS_TOKENS_FILE` with one JWT per line to distribute sockets
across members. Then run:

```sh
python -m pip install -r tests/load/requirements.txt
python tests/load/load_websockets.py
```

Optional environment variables are `CLIENTS` (default 50), `API_BASE_URL`,
`WS_BASE_URL`, and `CONNECT_TIMEOUT`. The script reports successful
connections, delivered task updates, and min/median/p95/max end-to-end delivery
latency. Use the same machine and Redis/backend configuration when comparing
runs. The target is 50/50 connected and all 50 updates delivered with p95
under 1 second. No benchmark number is claimed here until the Redis-backed
load test has actually run; an in-memory channel layer is not a valid
scalability measurement.

## Check updates manually

1. Sign in as two workspace members in separate browser windows.
2. Open the same project board in both windows.
3. Create a task, change its status, or assign it in one window.
4. The second board should reload its task data and show the change without a
   page refresh.

WebSocket connections use the existing SimpleJWT access token as the
`bearer.<token>` WebSocket subprotocol. Project membership is checked before a
connection joins the project's event group.
