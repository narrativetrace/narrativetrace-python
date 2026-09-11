# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`poe verify-all` — runs EVERY verification this repo has, gate and heavy alike, and writes
`reports/verification/<date>.json` + `<date>.md` conforming to the cross-port contract in the
Java golden repo's `reports/verification/SCHEMA.md` (pro repo TODO §35E).

This is LONG-RUNNING BY DESIGN (mutation testing across two packages, a full coverage run, a
budgeted fuzz sweep, and — host load permitting — a benchmark suite are each historically
tens of seconds to tens of minutes on this project's own dev machine). A category's failure
never aborts the run: every category function below is wrapped in the same top-level safety
net, so one crashing tool still leaves every other category's real result in the report.
`overall_status` is `"failed"` iff at least one row is `"failed"` — `skipped`/`not-implemented`
never taint it (SCHEMA.md).
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from scripts.verify_all_arch_stress import (
    build_architecture_row,
    build_stress_long_row,
    build_stress_short_row,
    run_lint_imports,
    run_stress_long,
    run_stress_short,
)
from scripts.verify_all_exec import (
    CommandOutcome,
    host_descriptor,
    load_average_1min,
    repo_version,
    run_command,
    short_commit,
    tool_version,
)
from scripts.verify_all_heavy import (
    build_allocation_row,
    build_benchmarks_row,
    build_benchmarks_skipped_row,
    build_fuzz_tier_b_row,
    build_mutation_row,
    run_benchmarks,
    run_fuzz_tier_b,
    run_glossary_mutation,
    run_narrativetrace_mutation,
)
from scripts.verify_all_schema import (
    CategoryResult,
    VerificationRun,
    render_markdown,
    write_verification_json,
)
from scripts.verify_all_security import (
    build_sast_row,
    build_sca_row,
    build_secrets_row,
    run_bandit,
    run_gitleaks,
    run_osv_scanner,
    run_pip_audit,
    run_semgrep,
)
from scripts.verify_all_static import (
    build_clarity_row,
    build_complexity_row,
    build_format_row,
    build_lint_row,
    build_translation_row,
    build_types_row,
    run_clarity_scan,
    run_mypy,
    run_ruff_check_json,
    run_ruff_format_check,
    run_translation_check,
    run_xenon,
)
from scripts.verify_all_testrun import (
    CoverageTotals,
    JUnitCase,
    is_conformance_module,
    is_property_module,
    is_security_tests_module,
    matching,
    parse_junit,
    read_coverage_totals,
    summarize,
    total_seconds,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "build" / "verify-all-logs"

# This repo's own dev host is an 8-core machine: a 1-minute load average above this makes a
# timing run measure the host, not the code, so benchmarks/allocation are skipped rather than
# reporting a phantom regression.
_LOAD_AVERAGE_SKIP_THRESHOLD = 6.0


def _crash_row(category: str, exc: BaseException) -> CategoryResult:
    """The fallback row a category gets when its own builder raised — never a missing row, and
    never a silent pass; `verify-all` itself is the one thing every category here trusts."""
    return CategoryResult(
        category=category,
        tool="verify-all",
        status="failed",
        metrics={},
        duration_seconds=0.0,
        note=f"verify-all crashed building this row: {exc!r}",
    )


def _safe(
    category_ids: tuple[str, ...], producer: Callable[[], list[CategoryResult]]
) -> list[CategoryResult]:
    """Runs one category-producing step; any exception it raises becomes a `failed` row per
    category it would have produced, rather than aborting every category still to come."""
    try:
        return producer()
    except Exception as exc:
        # never take down every other category's real result.
        return [_crash_row(category, exc) for category in category_ids]


# --------------------------------------------------------------------------------- test sweep


def _run_full_test_sweep() -> tuple[tuple[JUnitCase, ...], float, CoverageTotals, CommandOutcome]:
    """The one real pytest invocation `unit-tests`, `coverage`, `property`, `fuzz-tier-a`, and
    `conformance` are all sliced from — paying for test execution exactly once."""
    junit_path = LOG_DIR / "unit-tests.xml"
    coverage_json = LOG_DIR / "coverage.json"
    outcome = run_command(
        [
            "pytest",
            "--cov",
            "--cov-report=term-missing",
            f"--cov-report=json:{coverage_json}",
            f"--junitxml={junit_path}",
            "-q",
        ],
        LOG_DIR / "unit-tests.log",
        cwd=REPO_ROOT,
    )
    entries, suite_seconds = parse_junit(junit_path)
    coverage = read_coverage_totals(coverage_json)
    return entries, suite_seconds, coverage, outcome


def _test_derived_rows(
    entries: tuple[JUnitCase, ...],
    suite_seconds: float,
    coverage: CoverageTotals,
    pytest_version: str,
) -> list[CategoryResult]:
    unit_tests = CategoryResult(
        category="unit-tests",
        tool=f"pytest {pytest_version} (+ pytest-cov)",
        status="passed" if all(e.outcome != "failed" for e in entries) else "failed",
        metrics=dict(summarize(entries)),
        duration_seconds=suite_seconds,
        note='packages + examples suite (addopts: -m "not stress" --benchmark-skip); '
        "property/fuzz-tier-a/conformance below are sliced from this same run",
    )
    coverage_row = CategoryResult(
        category="coverage",
        tool="coverage.py (pytest-cov, 95% branch fail-under)",
        status="passed" if coverage.coverage_pct >= 95.0 else "failed",
        metrics={
            "coverage_pct": coverage.coverage_pct,
            "lines_covered": coverage.lines_covered,
            "lines_missed": coverage.lines_missed,
        },
        duration_seconds=0.0,
        note="derived from the same pytest run as unit-tests above — 0 additional invocations",
    )
    property_entries = matching(entries, is_property_module)
    property_row = CategoryResult(
        category="property",
        tool="Hypothesis (test_*_props.py, repo-wide)",
        status="passed" if all(e.outcome != "failed" for e in property_entries) else "failed",
        metrics=dict(summarize(property_entries)),
        duration_seconds=total_seconds(property_entries),
        note="sliced from the unit-tests row's own run — 0 additional invocations",
    )
    fuzz_a_entries = matching(entries, is_security_tests_module)
    fuzz_a_row = CategoryResult(
        category="fuzz-tier-a",
        tool="Hypothesis hostile-corpus properties (packages/narrativetrace-security-tests)",
        status="passed" if all(e.outcome != "failed" for e in fuzz_a_entries) else "failed",
        metrics=dict(summarize(fuzz_a_entries)),
        duration_seconds=total_seconds(fuzz_a_entries),
        note="sliced from the unit-tests row's own run (documentation/security-testing.md Tier A) "
        "— 0 additional invocations",
    )
    conformance_entries = matching(entries, is_conformance_module)
    conformance_row = CategoryResult(
        category="conformance",
        tool="jsonschema (packages/narrativetrace-pytest/tests/test_conformance.py + "
        "packages/narrativetrace/tests/test_identity_conformance.py)",
        status="passed" if all(e.outcome != "failed" for e in conformance_entries) else "failed",
        metrics=dict(summarize(conformance_entries)),
        duration_seconds=total_seconds(conformance_entries),
        note="validates the real writer's bytes on disk against schema/*.schema.json; sliced "
        "from the unit-tests row's own run — 0 additional invocations",
    )
    return [unit_tests, property_row, fuzz_a_row, conformance_row, coverage_row]


# --------------------------------------------------------------------------------- static rows


def _static_rows() -> list[CategoryResult]:
    ruff_version = tool_version(["ruff", "--version"])
    mypy_version = tool_version(["mypy", "--version"])
    format_outcome = run_ruff_format_check(REPO_ROOT, LOG_DIR)
    lint_outcome, violations = run_ruff_check_json(REPO_ROOT, LOG_DIR)
    xenon_outcome = run_xenon(REPO_ROOT, LOG_DIR)
    types_outcome = run_mypy(REPO_ROOT, LOG_DIR)
    translation_outcome = run_translation_check(REPO_ROOT, LOG_DIR)
    clarity_outcome = run_clarity_scan(REPO_ROOT, LOG_DIR)
    return [
        build_format_row(format_outcome, ruff_version),
        build_lint_row(lint_outcome, violations, ruff_version),
        build_complexity_row(xenon_outcome, violations),
        build_types_row(types_outcome, mypy_version),
        build_translation_row(translation_outcome),
        build_clarity_row(
            clarity_outcome, REPO_ROOT / "build" / "narrativetrace" / "clarity-results.json"
        ),
    ]


# ------------------------------------------------------------------------------- security rows


def _security_rows() -> list[CategoryResult]:
    secrets_outcome, secrets_report = run_gitleaks(REPO_ROOT, LOG_DIR)
    bandit_outcome, bandit_report = run_bandit(REPO_ROOT, LOG_DIR)
    semgrep_outcome, semgrep_report = run_semgrep(REPO_ROOT, LOG_DIR)
    osv_outcome, osv_report = run_osv_scanner(REPO_ROOT, LOG_DIR)
    pip_audit_outcome, pip_audit_report = run_pip_audit(REPO_ROOT, LOG_DIR)
    return [
        build_secrets_row(secrets_outcome, secrets_report),
        build_sast_row(bandit_outcome, bandit_report, semgrep_outcome, semgrep_report),
        build_sca_row(osv_outcome, osv_report, pip_audit_outcome, pip_audit_report),
    ]


# ------------------------------------------------------------------- architecture + stress rows


def _arch_stress_rows() -> list[CategoryResult]:
    architecture_outcome = run_lint_imports(REPO_ROOT, LOG_DIR)
    stress_short_outcome, stress_short_junit = run_stress_short(REPO_ROOT, LOG_DIR)
    stress_long_outcome, stress_long_junit = run_stress_long(REPO_ROOT, LOG_DIR)
    return [
        build_architecture_row(architecture_outcome),
        build_stress_short_row(stress_short_outcome, stress_short_junit),
        build_stress_long_row(stress_long_outcome, stress_long_junit),
    ]


# --------------------------------------------------------------------------------- heavy rows


def _mutation_row() -> list[CategoryResult]:
    nt = run_narrativetrace_mutation(REPO_ROOT, LOG_DIR)
    glossary = run_glossary_mutation(REPO_ROOT, LOG_DIR)
    return [build_mutation_row(nt, glossary)]


def _fuzz_tier_b_row() -> list[CategoryResult]:
    return [build_fuzz_tier_b_row(run_fuzz_tier_b(REPO_ROOT, LOG_DIR))]


def _benchmark_rows() -> list[CategoryResult]:
    """`allocation` is always `not-implemented` in this ecosystem (see
    `verify_all_heavy.build_allocation_row`'s own doc); `benchmarks` runs for real unless the
    host's 1-minute load average is already too high to trust a timing measurement."""
    load_average = load_average_1min()
    if load_average > _LOAD_AVERAGE_SKIP_THRESHOLD:
        return [
            build_benchmarks_skipped_row(load_average, _LOAD_AVERAGE_SKIP_THRESHOLD),
            build_allocation_row(),
        ]
    outcome, junit_path = run_benchmarks(REPO_ROOT, LOG_DIR)
    return [build_benchmarks_row(outcome, junit_path), build_allocation_row()]


# --------------------------------------------------------------------------------------- main

_STEPS: tuple[tuple[tuple[str, ...], Callable[[], list[CategoryResult]]], ...] = (
    (("format", "lint", "complexity", "types", "translation", "clarity"), _static_rows),
    (("secrets", "sast", "sca"), _security_rows),
    (("architecture", "stress-short", "stress-long"), _arch_stress_rows),
    (("mutation",), _mutation_row),
    (("fuzz-tier-b",), _fuzz_tier_b_row),
    (("benchmarks", "allocation"), _benchmark_rows),
)


def _print_banner() -> None:
    bar = "=" * 100
    print(bar)
    print("verify-all: running every verification this repo has, gate and heavy alike.")
    print("LONG-RUNNING BY DESIGN (mutation testing, a full coverage run, a budgeted fuzz")
    print("sweep). A category's failure never aborts the run — see reports/verification/")
    print("SCHEMA.md for how to read the report this writes.")
    print(bar)


def _log_row(row: CategoryResult, started_at: float) -> None:
    elapsed = int(time.monotonic() - started_at)
    print(
        f"[{elapsed}s elapsed] {row.category:<14} {row.status:<15} "
        f"({row.duration_seconds:.1f}s)  {row.note or ''}"
    )


def _run_all_categories(started_at: float) -> list[CategoryResult]:
    rows: list[CategoryResult] = []

    def sweep() -> list[CategoryResult]:
        entries, suite_seconds, coverage, _outcome = _run_full_test_sweep()
        pytest_version = tool_version(["pytest", "--version"])
        return _test_derived_rows(entries, suite_seconds, coverage, pytest_version)

    for row in _safe(("unit-tests", "property", "fuzz-tier-a", "conformance", "coverage"), sweep):
        rows.append(row)
        _log_row(row, started_at)
    for category_ids, producer in _STEPS:
        for row in _safe(category_ids, producer):
            rows.append(row)
            _log_row(row, started_at)
    return rows


def _write_report(started_at_utc: datetime, rows: list[CategoryResult]) -> Path:
    run = VerificationRun(
        runtime="python",
        version=repo_version(REPO_ROOT),
        commit=short_commit(REPO_ROOT),
        host=host_descriptor(),
        started_at=started_at_utc.isoformat(),
        ended_at=datetime.now(UTC).isoformat(),
        categories=tuple(rows),
    )
    date_str = started_at_utc.date().isoformat()
    json_path = REPO_ROOT / "reports" / "verification" / f"{date_str}.json"
    md_path = REPO_ROOT / "reports" / "verification" / f"{date_str}.md"
    write_verification_json(run, json_path)
    md_path.write_text(render_markdown(json_path), encoding="utf-8")
    print(f"\n{render_markdown(json_path)}")
    print(f"verify-all: wrote {json_path} and {md_path}")
    return md_path


def main() -> int:
    _print_banner()
    started_at_utc = datetime.now(UTC)
    started_at = time.monotonic()
    rows = _run_all_categories(started_at)
    md_path = _write_report(started_at_utc, rows)
    failed = [row for row in rows if row.status == "failed"]
    if failed:
        names = ", ".join(row.category for row in failed)
        print(f"\nverify-all: {len(failed)} of {len(rows)} categories failed ({names})")
        print(f"see {md_path}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
