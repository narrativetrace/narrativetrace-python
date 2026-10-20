# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The mutation baseline must not build wheels.

mutmut's `pytest_add_cli_args_test_selection` is the argument list `PytestRunner` falls back to
whenever no specific killer tests have been narrowed down yet — that covers the clean-tests
baseline, the stats-collection pass and the forced-fail check alike. A distribution test that
builds real wheels (`built_distributions` in `test_distribution_licensing.py` shells out to
`uv build`) can never reach the network for a build-backend wheel that is not already in the
local cache once the outer run is offline, so a cold-cache runner fails every one of them. Such a
test proves packaging, not code under mutation, and has no place in that selection; the ordinary
test suite still runs it.
"""

from __future__ import annotations

import importlib.util
import marshal
import os
import struct
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import pytest

NARRATIVETRACE_DIR = Path(__file__).resolve().parent.parent
_MUTMUT_CONFIG = tomllib.loads((NARRATIVETRACE_DIR / "pyproject.toml").read_text(encoding="utf-8"))[
    "tool"
]["mutmut"]


class TestTheBaselineSelectionDeselectsDistributionTests:
    def test_the_test_selection_args_deselect_the_distribution_marker(self) -> None:
        """`-m` is a single-valued pytest option — a second `-m` wins outright over the root
        addopts' own `-m "not stress"` rather than combining with it, so whatever this config adds
        must restate every marker exclusion that already applies, not just the new one."""
        args = _MUTMUT_CONFIG["pytest_add_cli_args_test_selection"]
        assert "-m" in args, args
        expression = args[args.index("-m") + 1]
        assert "not distribution" in expression
        assert "not stress" in expression

    def test_the_selection_actually_collects_no_distribution_tests(self) -> None:
        """Proves the deselection against a real pytest collection, not just the config text."""
        collected = _collect_only(
            NARRATIVETRACE_DIR, *_MUTMUT_CONFIG["pytest_add_cli_args_test_selection"]
        )
        assert collected.returncode == 0, collected.stdout + collected.stderr
        assert "TestEveryBuiltArtifact" not in collected.stdout

    def test_the_collection_ignores_a_stale_bytecode_cache(self, tmp_path: Path) -> None:
        """A cache compiled elsewhere (another mount path, an earlier checkout) can carry a header
        that matches the source's mtime and size while holding other code; Python then trusts it.
        The collect-only run must not read the project's own ``__pycache__`` at all."""
        module = tmp_path / "tests" / "test_canary.py"
        module.parent.mkdir()
        module.write_text("def test_canary():\n    pass\n", encoding="utf-8")
        poisoned = compile("raise RuntimeError('stale cache')", "/gone/test_canary.py", "exec")
        stat = module.stat()
        header = struct.pack("<III", 0, int(stat.st_mtime), stat.st_size)
        for tag in (_python_cache_tag(), f"{_python_cache_tag()}-pytest-{pytest.__version__}"):
            cache = module.parent / "__pycache__" / f"test_canary.{tag}.pyc"
            cache.parent.mkdir(exist_ok=True)
            cache.write_bytes(importlib.util.MAGIC_NUMBER + header + marshal.dumps(poisoned))

        collected = _collect_only(tmp_path, "tests/")

        assert collected.returncode == 0, collected.stdout + collected.stderr
        assert "test_canary" in collected.stdout


def _python_cache_tag() -> str:
    return f"cpython-{sys.version_info.major}{sys.version_info.minor}"


def _collect_only(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """A real ``pytest --collect-only`` that neither reads nor writes any ``__pycache__`` of the
    tree: ``PYTHONPYCACHEPREFIX`` points all bytecode (Python's and pytest's rewritten tests) at a
    fresh directory, and ``-p no:cacheprovider`` leaves ``.pytest_cache`` alone. The assertion is
    about WHAT is collected, so it must not depend on what an earlier run left on disk."""
    with tempfile.TemporaryDirectory() as bytecode:
        return subprocess.run(  # nosec B603 # fixed argv, no shell, no untrusted input
            [sys.executable, "-m", "pytest", "--collect-only", "-p", "no:cacheprovider", *args],
            cwd=cwd,
            env={**os.environ, "PYTHONPYCACHEPREFIX": bytecode},
            capture_output=True,
            text=True,
            check=False,
        )
