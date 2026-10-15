# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``bounded.sh``: the graders' one time limit, portable to a platform with no GNU ``timeout``
(macOS; the Java reference has the same guard). Each case runs under a ``PATH`` holding only
the tools the case lists,
so "no ``timeout`` on this machine" is real rather than assumed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
# Beside the case directories, or one level down in mutmut's ``mutants/`` copy (which copies only
# the ``test*.py`` files).
_EVALS = next(d for d in (_HERE, _HERE.parent) if (d / "add-narrative-tracing").is_dir())
_BOUNDED = _EVALS / "add-narrative-tracing" / "bounded.sh"


def _path_with(tmp_path: Path, *tools: str) -> str:
    """A PATH directory linking only ``tools`` -- never ``timeout`` unless a case names it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in tools:
        found = shutil.which(tool)
        if found is None:
            pytest.skip(f"{tool} is not installed here")
        (bin_dir / tool).symlink_to(found)
    return str(bin_dir)


def _bounded(path: str, seconds: int, *command: str) -> subprocess.CompletedProcess[str]:
    script = f'. "{_BOUNDED}"; bounded {seconds} "$@"'
    return subprocess.run(  # nosec B603 - /bin/sh, this repository's own helper, fixed arguments
        ["/bin/sh", "-c", script, "sh", *command],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": path},
        timeout=30,
        check=False,
    )


def test_without_gnu_timeout_a_command_that_finishes_keeps_its_own_exit_code(
    tmp_path: Path,
) -> None:
    path = _path_with(tmp_path, "perl", "true", "false")

    assert _bounded(path, 5, "true").returncode == 0
    assert _bounded(path, 5, "false").returncode == 1


def test_without_gnu_timeout_a_command_past_its_limit_is_stopped_non_zero(tmp_path: Path) -> None:
    path = _path_with(tmp_path, "perl", "sleep")

    done = _bounded(path, 1, "sleep", "20")

    assert done.returncode != 0
    assert "command not found" not in done.stderr


def test_with_gnu_timeout_available_it_is_the_one_used(tmp_path: Path) -> None:
    if shutil.which("timeout") is None:
        pytest.skip("this machine has no GNU timeout")
    path = _path_with(tmp_path, "timeout", "sleep")

    assert _bounded(path, 1, "sleep", "20").returncode == 124


def test_no_grader_calls_the_gnu_timeout_directly() -> None:
    """A grader that calls ``timeout N ...`` itself dies on macOS; ``bounded`` is the one way."""
    graders = (_BOUNDED.parent, *_BOUNDED.parent.parent.rglob("graders"))
    offenders = [
        f"{script.relative_to(_BOUNDED.parent.parent)}:{number}"
        for folder in graders
        for script in folder.glob("*.sh")
        if script != _BOUNDED
        for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), start=1)
        if not line.lstrip().startswith("#") and " timeout " in f" {line} "
    ]

    assert offenders == []


def test_the_graders_that_bound_a_command_source_the_helper() -> None:
    for name in ("run_the_program.sh", "run_the_redaction_test.sh"):
        text = (_BOUNDED.parent / name).read_text(encoding="utf-8")

        assert '. "$(dirname "$0")/bounded.sh"' in text, name
