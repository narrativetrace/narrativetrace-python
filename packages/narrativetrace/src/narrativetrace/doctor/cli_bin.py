# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace`` console entry point: verb dispatch over the free CLI (``doctor`` today).

Follows the ``narrativetrace-approve``/``narrativetrace-clarity`` CLIs' shape: stdlib
``argparse``-free hand-rolled dispatch (mirrors the TypeScript runtime's ``cli.ts``/``cli-bin.ts``
split — ``run_cli`` here takes injectable dependencies so tests never spawn a real process or touch
the real filesystem), ``main(argv=None) -> int`` returning the process exit code, no third-party CLI
framework (the core distribution stays dependency-free).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from narrativetrace.doctor.doctor import run_doctor
from narrativetrace.doctor.environment import build_snapshot
from narrativetrace.doctor.render import render_human, render_json

if TYPE_CHECKING:
    from narrativetrace.doctor.types import DoctorSnapshot, Env

_USAGE = """narrativetrace — one CLI over NarrativeTrace's open artifact formats

Usage:
  narrativetrace doctor [--json]

Commands:
  doctor    Read-only project diagnosis: toolchain, configuration, and known traps. Zero network.

Options:
  --json    Machine-readable output instead of human text.
  --help    Show this message."""

_DOCTOR_USAGE = """narrativetrace doctor [--json]

Read-only. Checks toolchain/install state, configuration, and known traps against the current
project. Exit 0 = clean, 1 = findings, 2 = could not run."""


@dataclass(frozen=True, slots=True)
class CliDeps:
    """Injectable seam (mirrors the TypeScript runtime's ``CliDeps``) so a test drives
    :func:`run_cli` without a real process, a real cwd, or a real filesystem walk."""

    cwd: str
    env: Env
    build_snapshot: Callable[[str, Env], DoctorSnapshot]
    log: Callable[[str], None]
    error: Callable[[str], None]


def _run_doctor_command(rest: Sequence[str], deps: CliDeps) -> int:
    """Runs ``doctor`` once argv has been recognized as that command. Returns the exit code."""
    if "--help" in rest or "-h" in rest:
        deps.log(_DOCTOR_USAGE)
        return 0
    as_json = "--json" in rest
    unknown = [arg for arg in rest if arg != "--json"]
    if unknown:
        deps.error(f"Unknown argument(s) for doctor: {', '.join(unknown)}\n\n{_DOCTOR_USAGE}")
        return 2
    snapshot = deps.build_snapshot(deps.cwd, deps.env)
    if snapshot.root_pyproject is None:
        deps.error(f"Could not run: no readable pyproject.toml found at {deps.cwd}")
        return 2
    report = run_doctor(snapshot)
    deps.log(render_json(report) if as_json else render_human(report))
    return report.exit_code


def run_cli(argv: Sequence[str], deps: CliDeps) -> int:
    """Parses ``argv`` and runs the requested command. Returns the process exit code."""
    if not argv:
        deps.error(_USAGE)
        return 2
    verb, *rest = argv
    if verb in ("--help", "-h"):
        deps.log(_USAGE)
        return 0
    if verb != "doctor":
        deps.error(f"Unknown command: {verb}\n\n{_USAGE}")
        return 2
    return _run_doctor_command(rest, deps)


def _log_stdout(message: str) -> None:
    print(message)  # the CLI's own stdout, not debug output


def _log_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def main(argv: Sequence[str] | None = None, *, cwd: str | None = None) -> int:
    """The ``narrativetrace`` console script entry point.

    ``cwd`` defaults to the real process cwd (``os.getcwd()``); pass it explicitly to run against
    a different project root without touching process-global state. The process cwd is not a test
    input to fake by monkeypatching -- ``os.getcwd()`` is read by other code in the process too
    (mutmut's mutation trampoline re-resolves its configured, relative source path against it on
    every call into mutated code, ``main`` included, and crashes if a monkeypatch points it
    somewhere that path doesn't exist -- see ``test_doctor_cli_bin.py``'s note on the same hazard).
    """
    args = list(sys.argv[1:] if argv is None else argv)
    deps = CliDeps(
        cwd=cwd if cwd is not None else os.getcwd(),
        env=os.environ,
        build_snapshot=build_snapshot,
        log=_log_stdout,
        error=_log_stderr,
    )
    return run_cli(args, deps)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
