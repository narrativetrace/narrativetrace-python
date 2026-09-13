# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``run_cli``/``main`` — driven with injected deps (:class:`CliDeps`) so no test spawns a real
process or touches the real filesystem, mirroring the TypeScript runtime's ``cli.test.ts``."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from narrativetrace.doctor.cli_bin import CliDeps, main, run_cli
from narrativetrace.doctor.types import DoctorSnapshot


def _snapshot(**overrides: object) -> DoctorSnapshot:
    base: dict[str, object] = {
        "cwd": "/project",
        "python_version": "3.12.4",
        "env": {},
        "root_pyproject": {"project": {"name": "demo"}},
        "narrativetrace_config": {},
        "source_files": {},
        "output_files": {},
        "approved_dir_files": {},
        "installed_packages": {},
        "pytest11_entry_points": {},
    }
    base.update(overrides)
    return DoctorSnapshot(**base)  # type: ignore[arg-type]


def _deps(snapshot: DoctorSnapshot | None = None) -> tuple[CliDeps, list[str], list[str]]:
    logs: list[str] = []
    errors: list[str] = []
    resolved = snapshot if snapshot is not None else _snapshot()
    deps = CliDeps(
        cwd="/project",
        env={},
        build_snapshot=lambda cwd, env: resolved,
        log=logs.append,
        error=errors.append,
    )
    return deps, logs, errors


class TestRunCliUsage:
    def test_no_command_prints_usage_and_exits_two(self) -> None:
        deps, logs, errors = _deps()
        assert run_cli([], deps) == 2
        assert "Usage" in errors[0]
        assert logs == []

    def test_help_flag_prints_usage_and_exits_zero(self) -> None:
        deps, logs, _ = _deps()
        assert run_cli(["--help"], deps) == 0
        assert "narrativetrace doctor" in logs[0]

    def test_unknown_command_exits_two(self) -> None:
        deps, _, errors = _deps()
        assert run_cli(["frobnicate"], deps) == 2
        assert "Unknown command: frobnicate" in errors[0]


class TestRunCliDoctor:
    def test_doctor_help_prints_usage_and_exits_zero(self) -> None:
        deps, logs, _ = _deps()
        assert run_cli(["doctor", "--help"], deps) == 0
        assert "Read-only" in logs[0]

    def test_unknown_flag_exits_two(self) -> None:
        deps, _, errors = _deps()
        assert run_cli(["doctor", "--bogus"], deps) == 2
        assert "Unknown argument(s) for doctor: --bogus" in errors[0]

    def test_no_readable_pyproject_exits_two(self) -> None:
        deps, _, errors = _deps(_snapshot(root_pyproject=None))
        assert run_cli(["doctor"], deps) == 2
        assert "Could not run" in errors[0]

    def test_human_output_by_default(self) -> None:
        source = {"tests/test_x.py": "assert '[REDACTED]' in out"}
        deps, logs, _ = _deps(_snapshot(source_files=source))
        exit_code = run_cli(["doctor"], deps)
        assert exit_code in (0, 1)
        assert "narrativetrace doctor" in logs[0]

    def test_json_output_when_flagged(self) -> None:
        source = {"tests/test_x.py": "assert '[REDACTED]' in out"}
        deps, logs, _ = _deps(_snapshot(source_files=source))
        run_cli(["doctor", "--json"], deps)
        payload = json.loads(logs[0])
        assert len(payload["findings"]) == 11

    def test_exit_code_matches_the_report(self) -> None:
        deps, _, _ = _deps(_snapshot(python_version="3.9.0"))
        assert run_cli(["doctor"], deps) == 1


class TestMain:
    def test_main_runs_against_the_real_process_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A thin smoke test of the real console-script wiring (`build_snapshot`/`os.environ`),
        against a scratch project rather than this repository's own tree.

        `os.getcwd` is patched rather than the process actually `chdir`-ing: a real chdir moves
        the whole process off the checkout for the rest of this test, which nothing in this suite
        may depend on (see test_cli.py's own note on the same hazard — mutation testing's
        trampoline re-resolves its configured, relative source path against the live process cwd
        on every call into mutated code, `main` included).
        """
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        exit_code = main(["doctor", "--json"])
        assert exit_code in (0, 1)

    def test_main_writes_errors_to_real_stderr(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The real `_log_stderr`/`print(..., file=sys.stderr)` wiring, not the injected fake used
        by every other test in this module."""
        monkeypatch.setattr(os, "getcwd", lambda: "/nonexistent-for-this-test")
        exit_code = main(["frobnicate"])
        assert exit_code == 2
        assert "Unknown command: frobnicate" in capsys.readouterr().err
