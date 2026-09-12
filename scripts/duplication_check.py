# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Duplication ratchet gate (`poe duplication-check`, wired into `poe check`).

Backs the per-commit duplication gate — a ratchet against a committed baseline, not a fixed
percentage (see documentation/duplication.md for why: the "right" number depends on the token
floor and on how much test scaffolding legitimately repeats, so a fixed threshold is either loose
enough to never fire or tight enough to block unrelated work). Mirrors the Java runtime's
`duplicationCheck` Gradle task (`dependsOn(":duplicationReport")`): `main()` below runs
`scripts.duplication_report.run_report()` first (writes `duplication.json` every commit), then
ratchets its main-tree percentage and largest non-exempt cluster against
`config/duplication/{baseline.properties,exemptions.txt}`.

Only the main tree gates; the test tree is reported by `duplication_report` and never reaches
`decide` below. When Node/npx is missing, `run_report` has already resolved whether that is a
local warn-and-skip or a CI/required hard failure — `main()` only needs to not treat "skipped" as
"nothing to ratchet against, so fail": a skip already printed its own warning.

`read_baseline`/`read_exemptions`/`is_exempt`/`decide` are pure (no I/O beyond the two file reads)
and are what the test suite exercises directly — the same split
`DuplicationCheckSupport.kt`/`DuplicationCheckSupport.swift` draw between the pure ratchet logic
and the untested glue that calls it.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.duplication_report import (
    DUPLICATION_REPORTS_DIR,
    TOOL,
    DuplicationCluster,
    DuplicationTreeResult,
    read_json,
    run_report,
    scan_status,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config" / "duplication"

# Percentage-point slack absorbing scan-to-scan noise between runs (owner ruling 2026-09-12).
PERCENT_TOLERANCE = 0.3


@dataclass(frozen=True, slots=True)
class DuplicationBaseline:
    """The committed `config/duplication/baseline.properties` — main tree only; tests never
    gate."""

    main_percent: float
    main_largest_cluster: int
    recorded: str
    commit: str


@dataclass(frozen=True, slots=True)
class DuplicationExemption:
    """One `config/duplication/exemptions.txt` entry: a deliberate pair, with the reason it
    exists."""

    glob_a: str
    glob_b: str
    reason: str


@dataclass(frozen=True, slots=True)
class DuplicationCheckResult:
    passed: bool
    message: str


def read_baseline(path: Path) -> DuplicationBaseline:
    if not path.is_file():
        raise ValueError(f"{path}: no duplication baseline — run duplication-report and commit one")
    properties: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ValueError(f"{path}: malformed line (expected 'key=value'): {stripped}")
        key, _, value = stripped.partition("=")
        properties[key.strip()] = value.strip()

    def required(key: str) -> str:
        if key not in properties:
            raise ValueError(f"{path}: missing '{key}'")
        return properties[key]

    return DuplicationBaseline(
        main_percent=float(required("main.percent")),
        main_largest_cluster=int(required("main.largestCluster")),
        recorded=properties.get("recorded", ""),
        commit=properties.get("commit", ""),
    )


def read_exemptions(path: Path) -> list[DuplicationExemption]:
    """Parses `exemptions.txt`: blank-line-separated entries, each a `# reason` line (one or
    more, concatenated) immediately followed by one `globA :: globB` pair line. Default-deny: a
    pair line with no reason above it is a malformed file, not a silent pass."""
    if not path.is_file():
        return []
    exemptions: list[DuplicationExemption] = []
    pending_reason: str | None = None
    for index, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            pending_reason = None
        elif line.startswith("#"):
            pending_reason = _append_reason(pending_reason, line)
        else:
            exemptions.append(_parse_exemption_pair(path, index, line, pending_reason))
            pending_reason = None
    return exemptions


def _append_reason(pending_reason: str | None, comment_line: str) -> str:
    text = comment_line.removeprefix("#").strip()
    return f"{pending_reason} {text}" if pending_reason else text


def _parse_exemption_pair(
    path: Path, index: int, line: str, pending_reason: str | None
) -> DuplicationExemption:
    if pending_reason is None:
        raise ValueError(f"{path}:{index}: exemption pair has no '# reason' line above it: {line}")
    parts = [part.strip() for part in line.split("::")]
    if len(parts) != 2 or any(not part for part in parts):
        raise ValueError(f"{path}:{index}: expected 'globA :: globB', got: {line}")
    return DuplicationExemption(parts[0], parts[1], pending_reason)


def _glob_to_regex(glob: str) -> re.Pattern[str]:
    """Translates one exemption glob to a regex: `**` crosses path separators (matches zero or
    more characters, including `/`), `*` and `?` behave like a shell glob within one path segment
    (never crossing `/`), and every other character is matched literally."""
    parts: list[str] = []
    index = 0
    length = len(glob)
    while index < length:
        if glob[index : index + 2] == "**":
            parts.append(".*")
            index += 2
        elif glob[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif glob[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(glob[index]))
            index += 1
    return re.compile("".join(parts))


def matches_glob(glob: str, path: str) -> bool:
    return _glob_to_regex(glob).fullmatch(path) is not None


def is_exempt(cluster: DuplicationCluster, exemptions: list[DuplicationExemption]) -> bool:
    """A cluster is exempt when every occurrence's path matches one of a pair's two globs."""
    return any(
        all(
            matches_glob(exemption.glob_a, occurrence.file)
            or matches_glob(exemption.glob_b, occurrence.file)
            for occurrence in cluster.occurrences
        )
        for exemption in exemptions
    )


def decide(
    main: DuplicationTreeResult,
    baseline: DuplicationBaseline,
    exemptions: list[DuplicationExemption],
) -> DuplicationCheckResult:
    """The ratchet: fails when main's percentage rose past `PERCENT_TOLERANCE` over the baseline,
    or when a non-exempt cluster is bigger than the baseline's recorded largest — either one, on
    its own, is new duplication the baseline never accounted for."""
    percent_failed = main.percent - baseline.main_percent > PERCENT_TOLERANCE
    offending = [
        cluster
        for cluster in main.clusters
        if cluster.tokens > baseline.main_largest_cluster and not is_exempt(cluster, exemptions)
    ]
    if not percent_failed and not offending:
        return _passing_result(main, baseline, exemptions)
    return _failing_result(main, baseline, percent_failed, offending)


def _passing_result(
    main: DuplicationTreeResult,
    baseline: DuplicationBaseline,
    exemptions: list[DuplicationExemption],
) -> DuplicationCheckResult:
    # Anchored on non-exempt clusters: a data table exempted by path must not set the bar a real
    # copy elsewhere is measured against.
    non_exempt_tokens = [
        cluster.tokens for cluster in main.clusters if not is_exempt(cluster, exemptions)
    ]
    largest = max(non_exempt_tokens, default=0)
    return DuplicationCheckResult(
        True,
        f"duplication-check: main {main.percent:.1f}% within baseline "
        f"{baseline.main_percent:.1f}% (+/-{PERCENT_TOLERANCE}), largest non-exempt cluster "
        f"{largest} tokens (baseline {baseline.main_largest_cluster})",
    )


def _failing_result(
    main: DuplicationTreeResult,
    baseline: DuplicationBaseline,
    percent_failed: bool,
    offending: list[DuplicationCluster],
) -> DuplicationCheckResult:
    problems: list[str] = []
    if percent_failed:
        problems.append(
            f"main duplication rose to {main.percent:.1f}% (baseline {baseline.main_percent:.1f}% "
            f"+ {PERCENT_TOLERANCE} tolerance)"
        )
    problems.extend(_offending_cluster_message(cluster, baseline) for cluster in offending)
    message = (
        "duplication-check failed:\n  "
        + "\n  ".join(problems)
        + "\nLower the baseline (config/duplication/baseline.properties) with the commit that "
        "removes the duplication, or add a reasoned 'globA :: globB' pair to "
        "config/duplication/exemptions.txt if it is deliberate — see documentation/duplication.md."
    )
    return DuplicationCheckResult(False, message)


def _offending_cluster_message(cluster: DuplicationCluster, baseline: DuplicationBaseline) -> str:
    locations = " ↔ ".join(f"{o.file}:{o.start_line}" for o in cluster.occurrences)
    return (
        f"new cluster {cluster.tokens} tokens (baseline largest "
        f"{baseline.main_largest_cluster}): {locations}"
    )


def main() -> int:
    report_exit_code = run_report()
    if report_exit_code != 0:
        return report_exit_code
    if scan_status(DUPLICATION_REPORTS_DIR, TOOL) != "ran-clean":
        print(
            "duplication-check SKIPPED: no fresh scan to ratchet (see the report step above).",
            file=sys.stderr,
        )
        return 0

    scan = read_json(DUPLICATION_REPORTS_DIR / "duplication.json")
    baseline = read_baseline(CONFIG_DIR / "baseline.properties")
    exemptions = read_exemptions(CONFIG_DIR / "exemptions.txt")
    result = decide(scan.main, baseline, exemptions)
    print(result.message)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
