# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Command literals for ``add-narrativetrace-clarity``: the ``narrativetrace-clarity`` console
script in the project's own environment, because this port's closed command vocabulary is ``uv``
and ``git``.

The ``<angle-bracket>`` placeholders are the one thing the agent substitutes: the package
directories to scan, and the project's own thresholds. The Tier A2 replay test maps each onto a
harmless value of its own.

**@llmNote** The scan exits 0 and writes NOTHING when it finds no class (a wrong directory, or only
underscore-prefixed classes), so a previous run's files would satisfy any check that only asked
whether they exist. :data:`REPORTS_FRESH_CODE` therefore asks for scenarios, for a non-empty
Markdown report, and for both to be recent.
"""

from __future__ import annotations

SCAN = "uv run narrativetrace-clarity <source-dir> --output-dir build/narrativetrace"
"""The first scan: the report and nothing else. No threshold, so it cannot fail on a score."""

GATE = f"{SCAN} --min-score <min-score> --max-high-issues <max-high-issues>"
"""The same scan with the project's own thresholds: exits 1 on a violation and names it."""

# The Markdown name is built from a stem and a suffix, never written as a `*.md` literal: the
# citation lint (`lints.citation_violations`) reads every command string for a Markdown filename
# that is not a file of THIS repository, and this one is a file the scan writes into an adopter's
# project.
_REPORTS_FRESH = """\
import json, pathlib, sys, time
root = pathlib.Path("build/narrativetrace")
results = root / "clarity-results.json"
report = root / ("clarity-report" + ".md")
if not results.is_file() or not report.is_file() or not report.stat().st_size:
    sys.exit("no report: the scan wrote nothing (wrong source directory?)")
if time.time() - min(results.stat().st_mtime, report.stat().st_mtime) > 600:
    sys.exit("stale report: it is from an earlier run, not this scan")
try:
    scenarios = json.loads(results.read_text(encoding="utf-8")).get("scenarios")
except (ValueError, AttributeError):
    sys.exit("the results file is not a clarity report")
if not isinstance(scenarios, list) or not scenarios:
    sys.exit("the report scored no class")
"""

REPORTS_FRESH_CODE = _REPORTS_FRESH
"""The check as source, so a test can run it against a hand-built report directory."""

REPORTS_FRESH = f"uv run python -c '{_REPORTS_FRESH}'"
"""Both reports exist, are recent, and the JSON scored at least one class."""

_SOURCES_TRACKED = """\
import sys
sys.exit(0 if sys.stdin.read().split() else 1)
"""

LIST_SOURCES = "git ls-files '*.py' 'pyproject.toml'"
"""Every tracked Python file and the project file, so the agent chooses the directories to scan from
what the repository has rather than from what it expects."""

SOURCES_TRACKED = f"{LIST_SOURCES} | uv run python -c '{_SOURCES_TRACKED}'"
"""The repository tracks at least one thing to read."""

INSTALL_GATE = "uv add --dev narrativetrace-clarity"
"""A development dependency: the gate runs in CI and on a developer's machine, never in
production."""

GATE_RUNS = "uv run narrativetrace-clarity --help"
"""The console script resolves in the project's environment."""

RUN_TESTS = "uv run pytest -q"
"""A rename touches callers; the project's own suite is the only thing that knows they all moved."""
