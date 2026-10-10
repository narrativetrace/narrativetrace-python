# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Grades the published init prompt's step 6 -- "Run the program" -- for a project whose program is
a web SERVER: the project the agent left behind serves, and each request's own trace reaches the
server's output. Run with cwd set to the scaffolded fixture copy, from a case's graders/verify.sh:

    python3 -I run_the_server.py <TracedServiceName> <module:app> <route with {id}>

Why a server and not ``run_the_program.sh``: a FastAPI project's program does not exit, and what the
framework table promises for it (``config.asgi-middleware``) is a trace PER REQUEST, exported at the
request boundary. So the grader starts ``uv run uvicorn <module:app>`` on a free local port, waits
until it listens, sends two requests with two distinct ids, stops it, and reads everything it wrote.

What passes (:func:`verdict`): both requests answer 200, the output carries a rendered trace line
naming the service for EACH id, and the two ids are printed equally often. That last clause is the
request scope: an app that prints one shared, ever-growing trace prints the first request's call
again with the second, so the first id outnumbers the second. Printing each request's trace twice
(say, to stdout and through a logger) is still request-scoped and still passes.

Bounded, always: a cold ``uv run`` resolves and downloads the packages, so the wait for the port is
generous, but a server that never listens -- or exits -- fails this case rather than hanging the
harness.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Final

IDS: Final = ("grader-a7", "grader-b9")
STARTUP_SECONDS: Final = 900.0
REQUEST_SECONDS: Final = 30.0
STOP_SECONDS: Final = 10.0


def verdict(output: str, service: str, statuses: tuple[int, ...]) -> str | None:
    """Why the server's ``output`` fails the case, or ``None`` when it passes."""
    if any(status != 200 for status in statuses):
        return f"expected every request to answer 200, got {list(statuses)}"
    counts = _trace_lines_per_id(output, service)
    missing = [request_id for request_id, n in counts.items() if n == 0]
    if missing:
        return (
            f"expected a rendered trace line naming {service} for each request; none for {missing}"
        )
    if len(set(counts.values())) != 1:
        return (
            f"expected each request's own trace, printed once per request; the ids were printed "
            f"{counts} times -- an earlier request's call came back with a later one, so the "
            "trace is not request-scoped"
        )
    return None


def _trace_lines_per_id(output: str, service: str) -> dict[str, int]:
    """How many rendered trace lines naming ``service`` carry each request id."""
    line = re.compile(rf"(^|[^A-Za-z0-9_]){re.escape(service)}\.[A-Za-z_][A-Za-z0-9_]*\(")
    traced = [text for text in output.splitlines() if line.search(text)]
    return {request_id: sum(request_id in text for text in traced) for request_id in IDS}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(1.0)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _wait_until_listening(server: subprocess.Popen[bytes], port: int) -> str | None:
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
        if server.poll() is not None:
            return f"the server exited with {server.returncode} before it listened"
        if _listening(port):
            return None
        time.sleep(0.5)
    return f"the server did not listen on port {port} within {STARTUP_SECONDS:.0f}s"


def _get(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_SECONDS) as response:  # nosec B310 - a fixed http://127.0.0.1 URL
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except OSError:
        return 0


def _stop(server: subprocess.Popen[bytes]) -> None:
    """Stops the whole process group (``uv run`` starts the interpreter as its own child) the way a
    person does -- Ctrl+C first. SIGINT ends Python through ``KeyboardInterrupt``, so a print still
    in a block-buffered stdout is flushed at exit; uvicorn re-raises a SIGTERM after its graceful
    shutdown and the default action kills the interpreter with that output still in its buffer."""
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        if server.poll() is not None:
            return
        os.killpg(server.pid, sig)
        try:
            server.wait(timeout=STOP_SECONDS)
        except subprocess.TimeoutExpired:
            continue


def serve_and_request(app: str, route: str, log: Path) -> tuple[str | None, tuple[int, ...]]:
    """Starts the server, sends one request per id, stops it; the log holds what it printed."""
    port = _free_port()
    with log.open("wb") as sink:
        server = subprocess.Popen(  # nosec B603 B607 - a fixed argv, in the trial's scratch project
            ["uv", "run", "uvicorn", app, "--host", "127.0.0.1", "--port", str(port)],
            stdout=sink,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            problem = _wait_until_listening(server, port)
            if problem is not None:
                return problem, ()
            base = f"http://127.0.0.1:{port}"
            statuses = tuple(_get(base + route.format(id=request_id)) for request_id in IDS)
            time.sleep(1.0)  # the exporter runs at the request boundary, after the response
            return None, statuses
        finally:
            _stop(server)


def main(argv: list[str]) -> int:
    if len(argv) != 3 or "{id}" not in argv[2]:
        print("usage: run_the_server.py <TracedServiceName> <module:app> <route with {id}>")
        return 2
    service, app, route = argv
    with tempfile.TemporaryDirectory() as work:
        log = Path(work) / "server-output.txt"
        problem, statuses = serve_and_request(app, route, log)
        output = log.read_text(encoding="utf-8", errors="replace")
    problem = problem or verdict(output, service, statuses)
    if problem is not None:
        print(f"run_the_server.py: {problem}", file=sys.stderr)
        print("--- what the server printed ---", file=sys.stderr)
        print(output, file=sys.stderr)
        return 1
    print(f"run_the_server.py: each request printed its own trace naming {service}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
