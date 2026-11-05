"""Open authenticated project sockets and measure task-update delivery latency.

Required environment variables: PROJECT_ID, TASK_ID, and either ACCESS_TOKEN
or ACCESS_TOKENS_FILE (one JWT per line; tokens are cycled across clients).
Optional: CLIENTS (default 50), API_BASE_URL (default http://127.0.0.1:8000),
WS_BASE_URL (derived from API_BASE_URL by default), and CONNECT_TIMEOUT (20s).
"""

import asyncio
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

import websockets


def required(name):
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Set {name} before running this script.")
    return value


def get_tokens():
    if os.getenv("ACCESS_TOKENS_FILE"):
        with open(os.environ["ACCESS_TOKENS_FILE"], encoding="utf-8") as token_file:
            tokens = [line.strip() for line in token_file if line.strip()]
        if not tokens:
            raise SystemExit("ACCESS_TOKENS_FILE contains no tokens.")
        return tokens
    return [required("ACCESS_TOKEN")]


def patch_task_title(api_base, task_id, token, title):
    request = urllib.request.Request(
        f"{api_base}/api/tasks/{task_id}/",
        data=json.dumps({"title": title}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError(f"Task update returned HTTP {response.status}.")


def get_task(api_base, task_id, token):
    request = urllib.request.Request(
        f"{api_base}/api/tasks/{task_id}/",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


async def collect_event(index, url, token, task_id, title, ready, start_signal,
                        started_at, results, errors):
    try:
        async with websockets.connect(
            url,
            subprotocols=["t14", f"bearer.{token}"],
            ping_interval=None,
            open_timeout=float(os.getenv("CONNECT_TIMEOUT", "20")),
            close_timeout=2,
            max_size=256 * 1024,
        ) as socket:
            ready[index] = True
            await start_signal.wait()
            while True:
                message = json.loads(await asyncio.wait_for(socket.recv(), timeout=30))
                if (
                    message.get("type") == "task_updated"
                    and str(message.get("task_id")) == str(task_id)
                    and message.get("payload", {}).get("task", {}).get("title") == title
                ):
                    results[index] = time.perf_counter() - started_at[0]
                    return
    except Exception as error:
        errors[index] = f"{type(error).__name__}: {error}"


async def main():
    project_id = required("PROJECT_ID")
    task_id = required("TASK_ID")
    clients = int(os.getenv("CLIENTS", "50"))
    if clients < 1:
        raise SystemExit("CLIENTS must be at least 1.")

    api_base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    default_ws = api_base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    ws_base = os.getenv("WS_BASE_URL", default_ws).rstrip("/")
    tokens = get_tokens()
    ws_url = f"{ws_base}/ws/projects/{project_id}/board/"
    title = f"ws-load-{int(time.time())}"
    ready = [False] * clients
    results = {}
    errors = {}
    start_signal = asyncio.Event()
    started_at = [None]

    sockets = [
        asyncio.create_task(
            collect_event(
                i, ws_url, tokens[i % len(tokens)], task_id, title,
                ready, start_signal, started_at, results, errors,
            )
        )
        for i in range(clients)
    ]
    deadline = time.monotonic() + float(os.getenv("CONNECT_TIMEOUT", "20"))
    while sum(ready) + len(errors) < clients and time.monotonic() < deadline:
        await asyncio.sleep(0.05)

    connected = sum(ready)
    if connected == 0:
        await asyncio.gather(*sockets)
        raise SystemExit("No WebSocket clients connected; inspect the reported failures.")

    original_title = None
    try:
        original_title = get_task(api_base, task_id, tokens[0]).get("title")
    except Exception as error:
        errors[-1] = f"Task GET failed: {type(error).__name__}: {error}"

    started_at[0] = time.perf_counter()
    start_signal.set()
    if original_title is not None:
        try:
            await asyncio.to_thread(patch_task_title, api_base, task_id, tokens[0], title)
        except urllib.error.HTTPError as error:
            errors[-1] = f"Task PATCH failed: HTTP {error.code} {error.read().decode(errors='replace')}"
        except Exception as error:
            errors[-1] = f"Task PATCH failed: {type(error).__name__}: {error}"
    else:
        errors[-1] = "Could not fetch the task's original title; no update sent."

    if -1 in errors:
        for socket_task in sockets:
            socket_task.cancel()
        await asyncio.gather(*sockets, return_exceptions=True)
        for index, error in sorted(errors.items()):
            print(f"Failure {index}: {error}")
        sys.exit(1)

    try:
        await asyncio.wait_for(asyncio.gather(*sockets), timeout=35)
    except asyncio.TimeoutError:
        for index, task in enumerate(sockets):
            if not task.done():
                errors[index] = "Timed out waiting for the task update."
                task.cancel()
        await asyncio.gather(*sockets, return_exceptions=True)
    finally:
        try:
            await asyncio.to_thread(patch_task_title, api_base, task_id, tokens[0], original_title)
        except Exception as error:
            print(f"Warning: could not restore task title: {type(error).__name__}: {error}")
    latencies = sorted(results.values())
    p95 = latencies[max(0, (len(latencies) * 95 + 99) // 100 - 1)] if latencies else None
    print(f"Connected clients: {connected}/{clients}")
    print(f"Received task update: {len(latencies)}/{clients}")
    if latencies:
        print(f"Latency ms: min={latencies[0] * 1000:.1f}, median={statistics.median(latencies) * 1000:.1f}, p95={p95 * 1000:.1f}, max={latencies[-1] * 1000:.1f}")
    for index, error in sorted(errors.items()):
        print(f"Failure {index}: {error}")
    if connected != clients or len(latencies) != clients:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
