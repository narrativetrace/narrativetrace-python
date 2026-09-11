# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Subprocess/host glue shared by every `poe verify-all` category runner.

Mirrors `scripts/run_security_tool.py`'s own subprocess conventions (fixed argv, no shell) and
the TypeScript port's `tools/verify-all-exec.ts`: one place that runs a command, times it, and
always saves its full output to a log file — a summary line on the console is not enough to
diagnose a failure once `verify-all` has moved on to the next category.
"""

from __future__ import annotations

import os
import platform
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

Status = str  # "passed" | "failed" | "skipped" | "not-implemented" — see verify_all_schema


@dataclass(frozen=True)
class CommandOutcome:
    """What one real subprocess invocation actually did."""

    exit_code: int
    output: str
    seconds: float
    log_file: Path


def run_command(
    args: list[str],
    log_file: Path,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> CommandOutcome:
    """Runs `args` to completion, capturing combined stdout+stderr, and always writes the full
    output to `log_file` before returning — created ahead of the run so a tool that writes its
    own report into the same directory never races a missing parent."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    result = subprocess.run(  # nosec B603 # fixed argv, no shell, args built by this repo's own callers
        args, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    seconds = time.monotonic() - start
    output = (result.stdout or "") + (result.stderr or "")
    log_file.write_text(output, encoding="utf-8")
    return CommandOutcome(
        exit_code=result.returncode, output=output, seconds=seconds, log_file=log_file
    )


def with_log_hint(note: str | None, outcome: CommandOutcome, status: Status) -> str | None:
    """Appends the saved log path to `note` whenever `status` is not a clean pass — a passed
    row stays as clean as the schema's worked examples; a failed/skipped one always points
    somewhere a reader can dig further."""
    if status == "passed":
        return note
    hint = f"full output: {outcome.log_file}"
    return f"{note}; {hint}" if note else hint


def short_commit(repo_root: Path) -> str:
    """The short commit this run executed at — `"unknown"` rather than failing the run over it."""
    try:
        result = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        out = result.stdout.strip()
        return out if out else "unknown"
    except OSError:
        return "unknown"


def host_descriptor() -> str:
    """`<hostname>-<arch>` — enough to explain a timing anomaly, nothing sensitive."""
    return f"{socket.gethostname()}-{platform.machine()}"


def repo_version(repo_root: Path) -> str:
    """The version this checkout declares — the workspace root `pyproject.toml`'s
    `[project].version`, the whole product's version (mirrors Java's single
    `gradle.properties` property, not one distribution's own manifest)."""
    text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    if match is None:
        raise ValueError("root pyproject.toml carries no [project].version")
    return match.group(1)


def tool_version(args: list[str], pattern: str = r"(\d+\.\d+(?:\.\d+)?)") -> str:
    """Runs a `--version`-shaped command and extracts the first version-looking token from its
    output — `"unknown"` rather than failing the run over a tool's own `--version` quirks."""
    try:
        result = subprocess.run(  # nosec B603 # fixed argv, no shell, args are this repo's own tool names
            args, capture_output=True, text=True, check=False
        )
        match = re.search(pattern, result.stdout + result.stderr)
        return match.group(1) if match else "unknown"
    except OSError:
        return "unknown"


def load_average_1min() -> float:
    """The 1-minute load average, or `0.0` on a platform that doesn't expose one (never fails
    the run over a timing precondition check)."""
    try:
        return os.getloadavg()[0]
    except (OSError, AttributeError):
        return 0.0
