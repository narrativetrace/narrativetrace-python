# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Row builders + runners for the four heavy/scheduled-cadence categories: `mutation`
(`poe mutate-gate` + `poe mutate-glossary-gate`, combined into one row per SCHEMA.md's
multi-module precedent), `fuzz-tier-b` (`poe fuzz`), `benchmarks`, and `allocation`
(not-implemented — no allocation-rate/GC-profiler benchmark distinct from wall-clock throughput
exists in this ecosystem's suite).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from scripts.verify_all_exec import CommandOutcome, run_command, with_log_hint
from scripts.verify_all_schema import CategoryResult, Status
from scripts.verify_all_testrun import parse_junit, summarize

# --------------------------------------------------------------------------------------- mutation

_KILL_RATE_LINE = re.compile(
    r"mutation kill rate: [\d.]+% \((\d+)/(\d+) scored, (\d+) ledgered equivalent\(s\) excluded, "
    r"(\d+) mutants total\)"
)


@dataclass(frozen=True)
class MutationPackageResult:
    """One `poe mutate*-gate` package's outcome: the real gate's exit code, its own printed
    score line, and mutmut's own raw `mutmut-cicd-stats.json` counts (`None` when the run
    crashed before either was ever produced)."""

    name: str
    outcome: CommandOutcome
    killed: int | None
    scored: int | None
    excluded: int | None
    total: int | None
    survived: int | None
    no_tests: int | None
    timeout: int | None


def _read_stats(stats_path: Path) -> dict[str, int] | None:
    try:
        stats: dict[str, int] = json.loads(stats_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return stats


def run_mutation_package(
    repo_root: Path, log_dir: Path, name: str, poe_task: str, stats_path: Path
) -> MutationPackageResult:
    outcome = run_command(["poe", poe_task], log_dir / f"mutation-{name}.log", cwd=repo_root)
    line = _KILL_RATE_LINE.search(outcome.output)
    stats = _read_stats(stats_path)
    return MutationPackageResult(
        name=name,
        outcome=outcome,
        killed=int(line.group(1)) if line else None,
        scored=int(line.group(2)) if line else None,
        excluded=int(line.group(3)) if line else None,
        total=int(line.group(4)) if line else None,
        survived=stats.get("survived") if stats else None,
        no_tests=stats.get("no_tests") if stats else None,
        timeout=stats.get("timeout") if stats else None,
    )


def run_narrativetrace_mutation(repo_root: Path, log_dir: Path) -> MutationPackageResult:
    stats_path = repo_root / "packages/narrativetrace/mutants/mutmut-cicd-stats.json"
    return run_mutation_package(repo_root, log_dir, "narrativetrace", "mutate-gate", stats_path)


def run_glossary_mutation(repo_root: Path, log_dir: Path) -> MutationPackageResult:
    stats_path = repo_root / "packages/narrativetrace-glossary/mutants/mutmut-cicd-stats.json"
    return run_mutation_package(
        repo_root, log_dir, "narrativetrace-glossary", "mutate-glossary-gate", stats_path
    )


def _sum_optional(a: int | None, b: int | None) -> int | None:
    return None if a is None or b is None else a + b


def _mutation_metrics(
    nt: MutationPackageResult, glossary: MutationPackageResult
) -> dict[str, float | int]:
    killed = _sum_optional(nt.killed, glossary.killed)
    scored = _sum_optional(nt.scored, glossary.scored)
    total = _sum_optional(nt.total, glossary.total)
    survived = _sum_optional(nt.survived, glossary.survived)
    no_coverage = _sum_optional(nt.no_tests, glossary.no_tests)
    timeout = _sum_optional(nt.timeout, glossary.timeout)
    metrics: dict[str, float | int] = {}
    if killed is not None:
        metrics["mutants_killed"] = killed
    if survived is not None:
        metrics["mutants_survived"] = survived
    if no_coverage is not None:
        metrics["mutants_no_coverage"] = no_coverage
    if timeout is not None:
        metrics["mutants_timeout"] = timeout
    if killed is not None and scored and scored > 0:
        metrics["mutation_score"] = round(100 * killed / scored, 2)
    if total is not None:
        metrics["mutants_total"] = total
    return metrics


def _mutation_note(nt: MutationPackageResult, glossary: MutationPackageResult) -> str | None:
    parts = []
    for pkg in (nt, glossary):
        if pkg.killed is None:
            parts.append(
                f"{pkg.name}: crashed before producing a score (exit {pkg.outcome.exit_code})"
            )
        else:
            parts.append(f"{pkg.name}: {pkg.killed}/{pkg.scored} scored, {pkg.excluded} excluded")
    return "; ".join(parts)


def build_mutation_row(
    nt: MutationPackageResult, glossary: MutationPackageResult
) -> CategoryResult:
    status: Status = (
        "passed" if nt.outcome.exit_code == 0 and glossary.outcome.exit_code == 0 else "failed"
    )
    duration = nt.outcome.seconds + glossary.outcome.seconds
    note = with_log_hint(_mutation_note(nt, glossary), nt.outcome, status)
    return CategoryResult(
        category="mutation",
        tool="mutmut (narrativetrace + narrativetrace-glossary; 80% kill-rate floor each)",
        status=status,
        metrics=_mutation_metrics(nt, glossary),
        duration_seconds=duration,
        note=note,
    )


# ------------------------------------------------------------------------------------ fuzz-tier-b

_ATHERIS_LINE = re.compile(r"poe fuzz \(atheris, target 1\): (\d+) executions in ([\d.]+)s")
_HYPOTHESIS_LINE = re.compile(r"poe fuzz: (\d+) examples across (\d+) properties in ([\d.]+)s")
_ATHERIS_AVAILABLE = re.compile(r"TIER B: atheris IS importable")


def run_fuzz_tier_b(repo_root: Path, log_dir: Path) -> CommandOutcome:
    return run_command(["poe", "fuzz"], log_dir / "fuzz-tier-b.log", cwd=repo_root)


def build_fuzz_tier_b_row(outcome: CommandOutcome) -> CategoryResult:
    status: Status = "passed" if outcome.exit_code == 0 else "failed"
    atheris_ran = bool(_ATHERIS_AVAILABLE.search(outcome.output))
    hypothesis_match = _HYPOTHESIS_LINE.search(outcome.output)
    atheris_match = _ATHERIS_LINE.search(outcome.output)
    metrics: dict[str, float | int] = {}
    if hypothesis_match:
        metrics["examples"] = int(hypothesis_match.group(1))
        metrics["properties_run"] = int(hypothesis_match.group(2))
    if atheris_match:
        metrics["executions"] = int(atheris_match.group(1))
    metrics["targets_total"] = 2
    metrics["targets_fuzzed"] = 1 if atheris_ran else 0
    tool = (
        "atheris (target 1, real coverage-guided) + Hypothesis budgeted sweep (both targets)"
        if atheris_ran
        else "Hypothesis budgeted sweep, atheris fallback (not importable on this platform)"
    )
    note = None if hypothesis_match else "poe fuzz's own summary line could not be parsed back"
    return CategoryResult(
        category="fuzz-tier-b",
        tool=tool,
        status=status,
        metrics=metrics,
        duration_seconds=outcome.seconds,
        note=with_log_hint(note, outcome, status),
    )


# ---------------------------------------------------------------------------------- benchmarks

_BENCH_REGRESSION_THRESHOLD = "mean:20%"


def run_benchmarks(repo_root: Path, log_dir: Path) -> tuple[CommandOutcome, Path]:
    junit_path = log_dir / "benchmarks.xml"
    outcome = run_command(
        [
            "pytest",
            "--benchmark-only",
            "--benchmark-autosave",
            "--benchmark-compare",
            f"--benchmark-compare-fail={_BENCH_REGRESSION_THRESHOLD}",
            f"--junitxml={junit_path}",
            "-q",
        ],
        log_dir / "benchmarks.log",
        cwd=repo_root,
    )
    return outcome, junit_path


def build_benchmarks_row(outcome: CommandOutcome, junit_path: Path) -> CategoryResult:
    try:
        entries, _ = parse_junit(junit_path)
    except (OSError, KeyError, ValueError):
        entries = ()
    summary = summarize(entries)
    status: Status = "passed" if outcome.exit_code == 0 else "failed"
    metrics: dict[str, float | int] = (
        {
            "benchmarks_run": summary["tests_passed"] + summary["tests_failed"],
            "regressions": summary["tests_failed"],
        }
        if entries
        else {}
    )
    tool = f"pytest-benchmark (autosave/compare, compare-fail={_BENCH_REGRESSION_THRESHOLD})"
    return CategoryResult(
        category="benchmarks",
        tool=tool,
        status=status,
        metrics=metrics,
        duration_seconds=outcome.seconds,
        note=with_log_hint(None, outcome, status),
    )


def build_benchmarks_skipped_row(load_average: float, threshold: float) -> CategoryResult:
    note = (
        f"skipped: 1-minute load average {load_average:.2f} exceeds {threshold:.1f} on this "
        "8-core host — a timing job on a loaded host measures the host, not the code"
    )
    return CategoryResult(
        category="benchmarks",
        tool="pytest-benchmark",
        status="skipped",
        metrics={},
        duration_seconds=0.0,
        note=note,
    )


# ---------------------------------------------------------------------------------- allocation


def build_allocation_row() -> CategoryResult:
    """Always `not-implemented`, independent of host load: there is no tool at all for this
    category in this ecosystem's suite (a capability gap, not a "didn't run this time" — the
    load-average check that can turn `benchmarks` into `skipped` doesn't apply to a category
    with nothing to run in the first place)."""
    note = (
        "no allocation-rate/GC-profiler benchmark distinct from throughput exists for this "
        "port — packages/*/tests/test_bench_*.py + scripts/bench_gate.py (see the benchmarks "
        "row) measure wall-clock time only"
    )
    return CategoryResult(
        category="allocation",
        tool="none",
        status="not-implemented",
        metrics={},
        duration_seconds=0.0,
        note=note,
    )
