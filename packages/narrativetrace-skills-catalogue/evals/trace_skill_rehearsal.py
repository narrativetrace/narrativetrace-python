# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared harness for rehearsing the narrativetrace-verify and narrativetrace-debug graders BEFORE
any trial is spent: a scratch copy of a case's fixture, the real pytest plugin and approve verb run
inside it, and a transcript built in the shape the vendor CLI really streams.

The graders call ``uv run pytest`` in a trial; here :func:`patched_test_runner` swaps that for this
interpreter's pytest with the plugin loaded and the fixture's own sources on the path — the same
plugin and renderers, no network, no wheel build.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def scaffold(fixture: str, into: Path) -> Path:
    """A scratch copy of ``fixtures/<fixture>``, as the runner makes one."""
    project = into / fixture
    shutil.copytree(FIXTURES / fixture, project)
    return project


def _environment(project: Path, extra: dict[str, str] | None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("NARRATIVETRACE_")}
    paths = [str(project / "src"), str(project / ".vendor" / "shopkit" / "src")]
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env.update(extra or {})
    return env


def run_pytest(project: Path, *args: str, env: dict[str, str] | None = None) -> tuple[bool, str]:
    """The project's own suite, through the narrativetrace plugin, in ``project``."""
    done = subprocess.run(  # nosec B603 - this interpreter, fixed arguments
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "narrativetrace",
            "-p",
            "no:cacheprovider",
            *args,
        ],
        cwd=project,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_environment(project, env),
        timeout=600,
        check=False,
    )
    return done.returncode == 0, done.stdout + done.stderr


def approve(project: Path) -> None:
    """The real approve verb, promoting every review copy under ``test-narratives``."""
    subprocess.run(  # nosec B603 - this interpreter, a fixed module
        [sys.executable, "-c", "from narrativetrace.cli import main; main([])"],
        cwd=project,
        check=True,
        capture_output=True,
        env=_environment(project, None),
    )


def pin(project: Path) -> None:
    """Approval mode on in ``pyproject.toml``, the review run, then the promotion — the pin."""
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text(encoding="utf-8") + "\n[tool.narrativetrace]\napproval = true\n",
        encoding="utf-8",
    )
    run_pytest(project)
    approve(project)


@contextmanager
def patched_test_runner(grader_module: object, project: Path) -> Iterator[None]:
    """Runs the grader's ``run_tests`` through :func:`run_pytest` for the duration."""
    original: Callable[..., tuple[bool, str]] = grader_module.run_tests  # type: ignore[attr-defined]

    def run_tests(*args: str, env: dict[str, str] | None = None) -> tuple[bool, str]:
        return run_pytest(project, *args, env=env)

    grader_module.run_tests = run_tests  # type: ignore[attr-defined]
    try:
        yield
    finally:
        grader_module.run_tests = original  # type: ignore[attr-defined]


class Stream:
    """A transcript in the runner's shape: a turn marker, then stream-json events."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self._ids = 0

    def user(self, turn: int, text: str) -> Stream:
        self.lines.append(json.dumps({"nt_turn": turn, "role": "user", "text": text}))
        return self

    def say(self, text: str) -> Stream:
        message = {"role": "assistant", "content": [{"type": "text", "text": text}]}
        self.lines.append(json.dumps({"type": "assistant", "message": message}))
        return self

    def context(self, text: str) -> Stream:
        """Text the harness put in front of the agent — a loaded skill's page."""
        message = {"role": "user", "content": [{"type": "text", "text": text}]}
        self.lines.append(json.dumps({"type": "user", "message": message}))
        return self

    def tool(self, name: str, tool_input: dict[str, object], result: str = "") -> Stream:
        self._ids += 1
        call_id = f"toolu_{self._ids}"
        use = {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}
        self.lines.append(
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [use]}})
        )
        answer = {"type": "tool_result", "tool_use_id": call_id, "content": result}
        self.lines.append(
            json.dumps({"type": "user", "message": {"role": "user", "content": [answer]}})
        )
        return self

    def bash(self, command: str, result: str = "") -> Stream:
        return self.tool("Bash", {"command": command}, result)

    def write_to(self, path: Path) -> Path:
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        return path
