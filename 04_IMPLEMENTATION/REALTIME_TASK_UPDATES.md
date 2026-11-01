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
single local server process. For multiple backend processes, set
`CHANNEL_LAYER_BACKEND=redis` and `CHANNEL_REDIS_URL` to a reachable Redis
instance.

## Check updates manually

1. Sign in as two workspace members in separate browser windows.
2. Open the same project board in both windows.
3. Create a task, change its status, or assign it in one window.
4. The second board should reload its task data and show the change without a
   page refresh.

WebSocket connections use the existing SimpleJWT access token as the
`bearer.<token>` WebSocket subprotocol. Project membership is checked before a
connection joins the project's event group.
