# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The single real pytest invocation `unit-tests`, `coverage`, `property`, `fuzz-tier-a`, and
`conformance` are all sliced from — paying for test execution exactly once, per SCHEMA.md's
"Derived categories" convention (mirrors the Java/TypeScript ports' own one-run-many-slices
design).

Slicing is by pytest's own JUnit `classname` attribute (the dotted module path, hyphens in a
`packages/<dist>/` directory name preserved verbatim — e.g.
``packages.narrativetrace-security-tests.tests.test_traceparent_properties``), matched by
real, already-established naming conventions documented in `documentation/security-testing.md`
and this repo's own test-naming conventions: `test_*_props.py` for Hypothesis property tests,
the `narrativetrace-security-tests` package for the Tier A hostile-corpus suite, and a
`conformance` substring for the schema-conformance tests. No test file is invented or
double-counted; a file matching none of these predicates is simply part of the plain
`unit-tests` row only.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET  # nosec B405 # nosemgrep - see parse_junit's own note below
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_PROPERTY_MODULE = re.compile(r"\btest_\w*_props\b")
_CONFORMANCE_MODULE = re.compile(r"\btest_(\w*_)?conformance\b")


@dataclass(frozen=True)
class JUnitCase:
    """One JUnit `<testcase>` — the unit this module slices categories by."""

    classname: str
    name: str
    time_seconds: float
    outcome: str  # "passed" | "failed" | "skipped"


def parse_junit(path: Path) -> tuple[tuple[JUnitCase, ...], float]:
    """Every testcase in `path`, plus the suite's own recorded `time` (real JUnit wall time,
    never derived by summing testcase times, which double-counts nothing but also never
    matches a suite that ran cases in parallel).

    `xml.etree.ElementTree` is flagged by both Bandit (B405/B314) and Semgrep
    (`use-defused-xml`) as unsafe for "untrusted" XML — the real risk both rules guard is
    entity-expansion/external-entity attacks from XML an adversary controls. `path` is always
    this same process's own `pytest --junitxml=...` output from a run this module just started
    (`verify_all.run_command`), never a file from outside this repo's own toolchain, so that
    risk does not apply here.
    """
    root = ET.parse(path).getroot()  # nosec B314 # nosemgrep - see the docstring above
    suite = root.find("testsuite")
    suite_seconds = float(suite.attrib["time"]) if suite is not None else 0.0
    entries = tuple(_to_entry(case) for case in root.findall(".//testcase"))
    return entries, suite_seconds


def _to_entry(case: ET.Element) -> JUnitCase:
    if case.find("failure") is not None or case.find("error") is not None:
        outcome = "failed"
    elif case.find("skipped") is not None:
        outcome = "skipped"
    else:
        outcome = "passed"
    return JUnitCase(
        classname=case.attrib.get("classname", ""),
        name=case.attrib.get("name", ""),
        time_seconds=float(case.attrib.get("time", "0")),
        outcome=outcome,
    )


def is_property_module(classname: str) -> bool:
    """`test_*_props.py` — the ordinary Hypothesis-property naming convention this repo's own
    tests already follow ("property tests `test_*_props.py`"). Deliberately distinct
    from `narrativetrace-security-tests`' own `test_*_properties.py` files (fuzz-tier-a): "props"
    is never a substring of "properties" (the character after "prop" differs, "s" vs "e"), so the
    two naming conventions never collide."""
    return bool(_PROPERTY_MODULE.search(classname))


def is_security_tests_module(classname: str) -> bool:
    """The whole `narrativetrace-security-tests` package — Tier A per
    `documentation/security-testing.md` ("Hypothesis properties fed by the shared hostile
    corpus... every `poe check`/`poe test`"), sliced as one package the same way the TypeScript
    port slices its sibling `security-tests` package."""
    return classname.startswith("packages.narrativetrace-security-tests.")


def is_conformance_module(classname: str) -> bool:
    """`test_conformance.py` / `test_identity_conformance.py` — the writer-validated
    schema/identity conformance suite (`packages/narrativetrace-pytest/tests/test_conformance.py`,
    `packages/narrativetrace/tests/test_identity_conformance.py`), named by the same
    self-describing convention as the property files above. A boundary match, not a bare
    substring test: `test_(\\w*_)?conformance` requires "conformance" to be its own
    underscore-delimited word, so a hypothetical `test_nonconformance.py` (fused, no separating
    underscore) would not be swept in here by accident."""
    return bool(_CONFORMANCE_MODULE.search(classname))


def matching(
    entries: tuple[JUnitCase, ...], predicate: Callable[[str], bool]
) -> tuple[JUnitCase, ...]:
    """Every entry whose `classname` satisfies `predicate` (e.g. `is_property_module`)."""
    return tuple(e for e in entries if predicate(e.classname))


def summarize(entries: tuple[JUnitCase, ...]) -> dict[str, int]:
    """`tests_passed`/`tests_failed`/`tests_skipped`/`test_classes` — SCHEMA.md's typical
    `unit-tests`/`property`/`fuzz-tier-a`/`conformance` metric keys, computed from real counts,
    `{}` (via an empty tuple) when nothing matched rather than a fabricated zero-count row."""
    return {
        "tests_passed": sum(1 for e in entries if e.outcome == "passed"),
        "tests_failed": sum(1 for e in entries if e.outcome == "failed"),
        "tests_skipped": sum(1 for e in entries if e.outcome == "skipped"),
        "test_classes": len({e.classname for e in entries}),
    }


def total_seconds(entries: tuple[JUnitCase, ...]) -> float:
    """The real summed per-testcase time for exactly this slice — never the whole run's time."""
    return sum(e.time_seconds for e in entries)


def all_green(entries: tuple[JUnitCase, ...]) -> bool:
    """`False` if anything in this slice failed; an empty slice is vacuously green (a category
    a runtime hasn't wired any matching test file for yet is `not-implemented`, not a false
    failure caused by this predicate)."""
    return all(e.outcome != "failed" for e in entries)


@dataclass(frozen=True)
class CoverageTotals:
    """`coverage.py`'s own `totals` object, the three fields SCHEMA.md's `coverage` row needs."""

    coverage_pct: float
    lines_covered: int
    lines_missed: int


def read_coverage_totals(path: Path) -> CoverageTotals:
    """Reads `coverage json`'s own `totals` block — never re-derived from the terminal report,
    which is the human-readable rendering of the same numbers, not their source of truth."""
    totals = json.loads(path.read_text(encoding="utf-8"))["totals"]
    return CoverageTotals(
        coverage_pct=totals["percent_covered"],
        lines_covered=totals["covered_lines"],
        lines_missed=totals["missing_lines"],
    )
