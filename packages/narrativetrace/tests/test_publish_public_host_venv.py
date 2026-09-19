# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A host-run `uv` step must never touch the container's shared venv.

The publish preparation script composes a public agent-guidance section by running `uv` on the
HOST, against the same bind-mounted project directory the container's own `uv` maintains. Left
unscoped, that host `uv` resolves the shared project environment: it finds a venv built for
whichever platform synced it last, deletes it, and rebuilds it for THIS platform instead — so a
host run wipes the container's Linux venv (and vice versa) until someone resyncs it there by
hand. Routing every host-run `uv` step through its own project environment instead leaves the
shared one alone.

Extracts the real `HOST_UV_ENV=` assignment and the subshell that uses it out of the actual
script (never a hand-copied duplicate, so this cannot drift from what a real publish run does)
and runs them against a synthetic shared project directory, with a fake `uv` standing in for the
real one on `PATH`: whichever project environment a `uv` invocation resolves (`$UV_PROJECT_
ENVIRONMENT`, else `.venv`), the fake one marks by touching a file inside it — proving the
routing without actually syncing a real environment.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest


def _repo_root() -> Path:
    """The workspace root, found by walking up rather than by counting directories.

    mutmut runs this suite from a `packages/narrativetrace/mutants/` copy, one level deeper than
    the source tree, so a fixed `parents[N]` would resolve wrong there and fail collection for
    the whole mutation run.
    """
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


REPO_ROOT = _repo_root()
SCRIPT = REPO_ROOT / "scripts" / "publish-public.sh"
# `scripts/publish-public.sh` is itself private machinery: the `--verify` step of a real publish
# run builds and tests the STAGED (published) snapshot standalone, where this file legitimately
# does not exist. Skip the whole module there rather than failing collection.
if not SCRIPT.is_file():
    pytest.skip(
        f"{SCRIPT} not present (private publish machinery, stripped from this snapshot)",
        allow_module_level=True,
    )
SCRIPT_TEXT = SCRIPT.read_text(encoding="utf-8")


def _extract(pattern: str) -> str:
    match = re.search(pattern, SCRIPT_TEXT, re.DOTALL | re.MULTILINE)
    assert match, f"pattern not found in {SCRIPT}: {pattern!r}"
    return match.group(0)


HOST_UV_ENV_LINE = _extract(r'^HOST_UV_ENV="\$REPO_ROOT/\.venv-host"$')
AGENTS_MD_SUBSHELL_SNIPPET = _extract(
    r'\( cd "\$REPO_ROOT" && UV_PROJECT_ENVIRONMENT=.*?publish_agents_md_section\.py "\$STAGE" \)'
)

_FAKE_UV = """#!/usr/bin/env bash
set -euo pipefail
target="${UV_PROJECT_ENVIRONMENT:-.venv}"
mkdir -p "$target"
: > "$target/touched-by-fake-uv"
"""


def _run_agents_md_subshell(tmp_path: Path) -> tuple[Path, Path]:
    """Runs the real script's agent-guidance-composing subshell against a synthetic
    `$REPO_ROOT`/`$STAGE`, a
    fake shared `.venv` already present (standing in for the container's own), and a stub `uv`
    on `PATH`. Returns `(shared_venv, host_venv)`."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    shared_venv = repo_root / ".venv"
    shared_venv.mkdir()
    (shared_venv / "pre-existing-marker").write_text(
        "linux venv, container-synced", encoding="utf-8"
    )
    stage = tmp_path / "stage"
    stage.mkdir()

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(_FAKE_UV, encoding="utf-8")
    fake_uv.chmod(fake_uv.stat().st_mode | stat.S_IEXEC)

    script = "\n".join(
        [
            "set -euo pipefail",
            f'REPO_ROOT="{repo_root}"',
            f'STAGE="{stage}"',
            HOST_UV_ENV_LINE,
            AGENTS_MD_SUBSHELL_SNIPPET,
        ]
    )
    env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"}
    subprocess.run(  # nosec B603, B607 # fixed argv (bash -c + this test's own script string
        # built above from repo-local literals and the real script's extracted snippets), no
        # shell metacharacter expansion beyond bash -c itself, no untrusted input
        ["bash", "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    return shared_venv, repo_root / ".venv-host"


class TestTheHostRunNeverTouchesTheSharedVenv:
    def test_the_shared_venv_is_untouched(self, tmp_path: Path) -> None:
        shared_venv, _host_venv = _run_agents_md_subshell(tmp_path)

        assert not (shared_venv / "touched-by-fake-uv").exists()
        assert (shared_venv / "pre-existing-marker").exists()

    def test_the_host_run_uses_its_own_venv_instead(self, tmp_path: Path) -> None:
        _shared_venv, host_venv = _run_agents_md_subshell(tmp_path)

        assert (host_venv / "touched-by-fake-uv").exists()
