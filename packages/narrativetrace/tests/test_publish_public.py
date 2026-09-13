# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Regression coverage for `scripts/publish-public.sh`'s trace-gate NAME filter.

The trace gate greps the staged snapshot for AI-development markers (`TRACE_PATTERN`) two ways:
staged file CONTENT and staged file NAMES. The content check has always been filtered through
`.publishallow`; the NAME check was not (fixed 2026-09-13, mirroring the TypeScript port's own
`90f7860` fix) -- a cleanly-worded file at an AI-tooling path (e.g. `.claude/skills/**`, a rendered
`render/claude.py`) could never clear the gate by review, only by renaming or deletion.

This extracts the real `TRACE_PATTERN` and `name_hits=` lines out of the actual script (never a
hand-copied duplicate, so the test cannot drift from what actually gates a publish) and runs that
exact snippet against a synthetic staged tree, proving the NAME check is now filtered the same way
the CONTENT check already is -- and still catches an unreviewed hit.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


def _repo_root() -> Path:
    """The workspace root, found by walking up rather than by counting directories.

    mutmut runs this suite from a `packages/narrativetrace/mutants/` copy, one level deeper than
    the source tree, so a fixed `parents[N]` would resolve wrong there and fail collection for the
    whole mutation run.
    """
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


REPO_ROOT = _repo_root()
SCRIPT = REPO_ROOT / "scripts" / "publish-public.sh"
# `scripts/publish-public.sh` is itself private machinery (.publishignore strips it): the
# `--verify` step of a real publish run builds and tests the STAGED (published) snapshot standalone,
# where this file legitimately does not exist. Skip the whole module there rather than failing
# collection -- there is nothing to regression-test against a script that was never shipped.
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


TRACE_PATTERN_LINE = _extract(r"^TRACE_PATTERN='[^']*'$")
# The two-line `name_hits=` assignment: from its opening `$(cd "$STAGE"` through the first
# `|| true)"` that closes it (the fallback-empty-string idiom every gate in this script shares).
NAME_HITS_SNIPPET = _extract(r'name_hits="\$\(cd "\$STAGE".*?\|\| true\)"')


def _run_name_hits(tmp_path: Path, allow_contents: str) -> str:
    """Run the real script's `name_hits=` computation against a synthetic staged tree."""
    stage = tmp_path / "stage"
    (stage / ".claude" / "skills").mkdir(parents=True)
    (stage / ".claude" / "skills" / "add.md").write_text("hi", encoding="utf-8")
    (stage / "plain.md").write_text("hi", encoding="utf-8")

    allow = tmp_path / ".publishallow"
    allow.write_text(allow_contents, encoding="utf-8")

    script = "\n".join(
        [
            "set -euo pipefail",
            f'STAGE="{stage}"',
            f'allow="{allow}"',
            TRACE_PATTERN_LINE,
            NAME_HITS_SNIPPET,
            'printf "%s" "$name_hits"',
        ]
    )
    result = subprocess.run(  # nosec B603, B607 # fixed argv (bash -c + this test's own script
        # string built above from repo-local literals and the real script's extracted snippet),
        # no shell metacharacter expansion beyond bash -c itself, no untrusted input
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    return result.stdout


class TestNameHitsAllowlistFiltering:
    def test_an_unreviewed_ai_tool_named_path_is_still_caught(self, tmp_path: Path) -> None:
        hits = _run_name_hits(tmp_path, allow_contents="")

        assert "./.claude" in hits

    def test_a_reviewed_publishallow_entry_clears_the_same_path(self, tmp_path: Path) -> None:
        hits = _run_name_hits(tmp_path, allow_contents=r"^\./\.claude(/.*)?$" + "\n")

        assert "./.claude" not in hits

    def test_an_unrelated_plain_file_never_hits_regardless_of_the_allowlist(
        self, tmp_path: Path
    ) -> None:
        hits = _run_name_hits(tmp_path, allow_contents="")

        assert "plain.md" not in hits

    def test_the_allowlist_does_not_blanket_clear_every_name_hit(self, tmp_path: Path) -> None:
        # A reviewed entry for one path must not silently launder an unrelated hit -- the fixture
        # tree carries only the one AI-tool-named path, so this is really the same assertion as
        # the "still caught" test above with an unrelated allow entry present, proving the filter
        # is a real regex match, not `[ -s "$allow" ]` alone short-circuiting the whole gate.
        hits = _run_name_hits(tmp_path, allow_contents=r"^\./nonexistent$" + "\n")

        assert "./.claude" in hits
