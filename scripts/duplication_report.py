# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Duplication report (`poe duplication-report`; also the `poe duplication-check` ratchet's own
first step, mirroring the Java runtime's `duplicationCheck.dependsOn(":duplicationReport")`).

Runs jscpd — a Copy/Paste Detector, the JavaScript-ecosystem tool this port uses in place of the
Java runtime's PMD CPD — over the main and test source trees separately and writes this port's
own `duplication.json` (`build/reports/duplication/duplication.json`) plus a one-line console
summary every commit. `scripts/duplication_check.py` reads that JSON and enforces the duplication
ratchet described in `documentation/duplication.md`; it is wired into `poe check`.

jscpd itself is never a dependency of this workspace's own `pyproject.toml` graph — it runs
through `npx jscpd@<pinned version>`, the same "run through the runtime's own toolchain, npx
elsewhere" rule every NarrativeTrace runtime's duplication tooling follows (Swift's own
`scripts/duplication-report.sh` is the precedent this module mirrors most closely, translated
from shell+Swift into one Python module). The pinned version lives in `JSCPD_VERSION` below, the
one place it is written; `documentation/duplication.md` points back here rather than keeping its
own copy.

Node is missing from this workspace's own CI image (`ghcr.io/astral-sh/uv:python3.12-bookworm`,
verified 2026-09-12: a fresh container has no `node`/`npx` on `PATH`) — both `ci.yml` and
the CI configuration install it (apt's `nodejs`/`npm`, which clears jscpd's own `>=18`
floor) before
`poe check` runs. A machine that skips that step gets the same graceful-skip contract
`scripts/run_security_tool.py` (security scanners) and `scripts/quality_gate_status.py`
(pre-commit format/lint) already established for a missing tool: a loud warning and exit 0
locally, but a hard failure in CI (`CI` set) or under `NARRATIVETRACE_DUPLICATION_REQUIRED=true` —
release rule 2, "a graceful-skip tool must prove it has ever run". Every outcome is recorded under
`build/reports/duplication/jscpd.status` as `ran-clean` or `skipped: <reason>` (no file at all
reads back as `never-ran`), the same three-state contract those two modules use for their own
concerns.

The whole jscpd invocation (`_run_jscpd`, `run_report`) is thin, untested glue over the CLI,
matching `DuplicationReportSupport.kt`'s own convention of testing the pure decision logic
(`normalize`, `aggregate`, `union_duplicated_lines`, `covered_line_count`, `summary_line`, the
JSON (de)serialization) rather than a live jscpd run — the real tool is proven by the actual gate,
not a unit test that would just re-run it.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DUPLICATION_REPORTS_DIR = REPO_ROOT / "build" / "reports" / "duplication"

# Pinned exact version (owner ruling, 2026-09-12) — the one place this version lives;
# documentation/duplication.md points back here rather than keeping its own copy.
JSCPD_VERSION = "5.2.0"

# Token floor (owner ruling, 2026-09-12): below this, jscpd's matches are noise — a handful of
# tokens two unrelated functions share by coincidence — rather than a genuine structural copy.
# Identifiers and literals are always ignored (see `_run_jscpd`), so what clears this floor is
# shape, not text.
MIN_TOKENS = 60

TOOL = "jscpd"
LANGUAGE = "python"


# --------------------------------------------------------------------------- #
# duplication.json model
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DuplicationOccurrence:
    """One occurrence of a duplicated block, relative to the repository root
    (`packages/<dist>/src/.../module.py`)."""

    file: str
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class DuplicationCluster:
    """One jscpd clone: an identical token sequence found at every one of `occurrences`. jscpd
    reports clones pairwise (always exactly two occurrences), unlike PMD CPD's arbitrary-arity
    match — see documentation/duplication.md, "Where this differs from the Java runtime"."""

    tokens: int
    lines: int
    occurrences: tuple[DuplicationOccurrence, ...]


@dataclass(frozen=True, slots=True)
class DuplicationTreeResult:
    """One source tree's scan (main or test): totals plus the clusters found in it, sorted by
    token count descending.

    `lines_total`/`lines_duplicated` measure duplication as a union over *line positions*, not
    tokens: PMD CPD (the Java runtime's tool) exposes a cross-file token index that lets it union
    at token granularity; jscpd does not, so this port unions at the finest exact grain jscpd's
    own report gives — line ranges, per file (see `union_duplicated_lines`). `min_tokens` on the
    enclosing `DuplicationScanResult` still governs which candidate clones jscpd considers at all;
    only the aggregate percentage's unit changes. Documented in full in
    documentation/duplication.md.
    """

    lines_total: int
    lines_duplicated: int
    percent: float
    clusters: tuple[DuplicationCluster, ...]


@dataclass(frozen=True, slots=True)
class DuplicationScanResult:
    """The whole `duplication.json` document: the family-wide schema every NarrativeTrace
    runtime's duplication tooling emits, for this runtime's own language and tool."""

    tool: str
    tool_version: str
    language: str
    min_tokens: int
    main: DuplicationTreeResult
    test: DuplicationTreeResult


# --------------------------------------------------------------------------- #
# jscpd raw report -> this port's own shape (pure, tested directly)
# --------------------------------------------------------------------------- #


def normalize(raw: dict[str, Any], root_dir: Path) -> DuplicationTreeResult:
    """Parses jscpd's raw `duplicates`/`statistics` JSON (`raw`, jscpd's own `--reporters json`
    shape — arbitrary JSON read back, not a value this module constructs itself, so typed as
    `dict[str, Any]` rather than kept precisely typed), turns every duplicate into a
    `DuplicationCluster` with occurrence paths relativized against `root_dir`, and unions their
    line ranges into `lines_duplicated`."""
    clusters = [_to_cluster(duplicate, root_dir) for duplicate in raw.get("duplicates", [])]
    lines_duplicated = union_duplicated_lines(clusters)
    lines_total = int(raw["statistics"]["total"]["lines"])
    return aggregate(lines_total, lines_duplicated, clusters)


def _to_cluster(duplicate: dict[str, Any], root_dir: Path) -> DuplicationCluster:
    return DuplicationCluster(
        tokens=int(duplicate["tokens"]),
        lines=int(duplicate["lines"]),
        occurrences=(
            _to_occurrence(duplicate["firstFile"], root_dir),
            _to_occurrence(duplicate["secondFile"], root_dir),
        ),
    )


def _to_occurrence(mark: dict[str, Any], root_dir: Path) -> DuplicationOccurrence:
    return DuplicationOccurrence(
        file=relativize(str(mark["name"]), root_dir),
        start_line=int(mark["start"]),
        end_line=int(mark["end"]),
    )


def relativize(absolute_path: str, root_dir: Path) -> str:
    """jscpd is invoked with `--absolute` so every occurrence path is unambiguous even when two
    scanned roots share a sub-path; this turns that absolute path back into the
    repository-root-relative form `config/duplication/exemptions.txt` globs match against."""
    root = str(root_dir.resolve())
    normalized_root = root if root.endswith("/") else root + "/"
    if not absolute_path.startswith(normalized_root):
        return absolute_path
    return absolute_path[len(normalized_root) :]


def aggregate(
    lines_total: int, lines_duplicated: int, clusters: list[DuplicationCluster]
) -> DuplicationTreeResult:
    """Aggregates already-deduplicated totals and raw clusters into the tree-level result. Pure —
    no I/O, no jscpd types. `lines_duplicated` must already be a union count (see
    `union_duplicated_lines`), not a per-cluster sum: a data-table file where every row
    structurally matches every other row produces dozens of overlapping clones over nearly the
    same lines, and a naive per-cluster sum multiplies that far past the file's own size — the
    same failure the Java runtime's first scan measured as over 300% duplication from the
    token-count equivalent of this bug. `percent` can therefore never exceed 100%."""
    percent = (
        0.0 if lines_total == 0 else _round_to_one_decimal(lines_duplicated / lines_total * 100)
    )
    sorted_clusters = tuple(sorted(clusters, key=lambda cluster: cluster.tokens, reverse=True))
    return DuplicationTreeResult(lines_total, lines_duplicated, percent, sorted_clusters)


def union_duplicated_lines(clusters: list[DuplicationCluster]) -> int:
    """How many distinct `(file, line)` positions `clusters`' occurrences cover, counting a
    position once no matter how many clusters or occurrences include it — the union, not the sum.
    Clusters are pairs (jscpd's own shape), but a busy data table still produces many overlapping
    pairwise clones over the same lines, which is exactly what this union guards against."""
    ranges_by_file: dict[str, list[tuple[int, int]]] = {}
    for cluster in clusters:
        for occurrence in cluster.occurrences:
            ranges_by_file.setdefault(occurrence.file, []).append(
                (occurrence.start_line, occurrence.end_line)
            )
    return sum(covered_line_count(ranges) for ranges in ranges_by_file.values())


def covered_line_count(ranges: list[tuple[int, int]]) -> int:
    """How many distinct integer lines the closed `ranges` cover within one file, counting a line
    once no matter how many ranges include it."""
    if not ranges:
        return 0
    sorted_ranges = sorted(ranges)
    covered = 0
    current_start, current_end = sorted_ranges[0]
    for start, end in sorted_ranges[1:]:
        if start > current_end + 1:
            covered += current_end - current_start + 1
            current_start, current_end = start, end
        elif end > current_end:
            current_end = end
    return covered + (current_end - current_start + 1)


def _round_to_one_decimal(value: float) -> float:
    """Round-half-up to one decimal (matches the Java/Swift runtimes' own rounding), not Python's
    banker's-rounding `round()`."""
    return math.floor(value * 10 + 0.5) / 10


# --------------------------------------------------------------------------- #
# duplication.json (de)serialization — camelCase keys: the family-wide schema every
# NarrativeTrace runtime's duplication tooling emits, documentation/duplication.md.
# --------------------------------------------------------------------------- #


def to_json_dict(scan: DuplicationScanResult) -> dict[str, object]:
    return {
        "tool": scan.tool,
        "toolVersion": scan.tool_version,
        "language": scan.language,
        "minTokens": scan.min_tokens,
        "main": _tree_to_dict(scan.main),
        "test": _tree_to_dict(scan.test),
    }


def _tree_to_dict(tree: DuplicationTreeResult) -> dict[str, object]:
    return {
        "linesTotal": tree.lines_total,
        "linesDuplicated": tree.lines_duplicated,
        "percent": tree.percent,
        "clusters": [_cluster_to_dict(cluster) for cluster in tree.clusters],
    }


def _cluster_to_dict(cluster: DuplicationCluster) -> dict[str, object]:
    return {
        "tokens": cluster.tokens,
        "lines": cluster.lines,
        "occurrences": [
            {
                "file": occurrence.file,
                "startLine": occurrence.start_line,
                "endLine": occurrence.end_line,
            }
            for occurrence in cluster.occurrences
        ],
    }


def write_json(scan: DuplicationScanResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_json_dict(scan), sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> DuplicationScanResult:
    """Raises if `path` is missing or not valid JSON — this schema's own round-trip is proven in
    `test_duplication_report.py`; `duplication_check.main` never calls this before `run_report`
    has just written it."""
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return DuplicationScanResult(
        tool=data["tool"],
        tool_version=data["toolVersion"],
        language=data["language"],
        min_tokens=int(data["minTokens"]),
        main=_tree_from_dict(data["main"]),
        test=_tree_from_dict(data["test"]),
    )


def _tree_from_dict(data: dict[str, Any]) -> DuplicationTreeResult:
    clusters = tuple(_cluster_from_dict(cluster) for cluster in data["clusters"])
    return DuplicationTreeResult(
        lines_total=int(data["linesTotal"]),
        lines_duplicated=int(data["linesDuplicated"]),
        percent=float(data["percent"]),
        clusters=clusters,
    )


def _cluster_from_dict(data: dict[str, Any]) -> DuplicationCluster:
    occurrences = tuple(
        DuplicationOccurrence(
            file=occurrence["file"],
            start_line=int(occurrence["startLine"]),
            end_line=int(occurrence["endLine"]),
        )
        for occurrence in data["occurrences"]
    )
    return DuplicationCluster(
        tokens=int(data["tokens"]), lines=int(data["lines"]), occurrences=occurrences
    )


def summary_line(scan: DuplicationScanResult) -> str:
    """The one console summary line: main's percent/cluster count/largest cluster (what
    `duplication_check.decide` acts on), then test's (reported only, never gated)."""
    main, test = scan.main, scan.test
    if main.clusters:
        largest = max(main.clusters, key=lambda cluster: cluster.tokens)
        locations = " ↔ ".join(f"{o.file}:{o.start_line}" for o in largest.occurrences)
        largest_description = f"largest {largest.tokens} tokens {locations}"
    else:
        largest_description = "no clusters"
    return (
        f"duplication: main {main.percent:.1f}% of lines in {len(main.clusters)} clusters "
        f"({largest_description}) · test {test.percent:.1f}% in {len(test.clusters)} clusters "
        "(reported, not gated)"
    )


# --------------------------------------------------------------------------- #
# The missing-Node gate — same three-state contract as
# scripts/run_security_tool.py (security scanners) and scripts/quality_gate_status.py
# (pre-commit format/lint), one env var per concern (release rule 2: a graceful-skip tool must
# prove it has ever run).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MissingToolDecision:
    """What the caller must do when Node/npx can't be found: fail, or warn with `message`."""

    fail: bool
    message: str


def duplication_scan_required() -> bool:
    """Whether this context demands the jscpd scan actually ran: CI, or the explicit opt-in
    flag."""
    return os.environ.get("NARRATIVETRACE_DUPLICATION_REQUIRED") == "true" or bool(
        os.environ.get("CI")
    )


def decide_missing_node(required: bool) -> MissingToolDecision:
    """The decision for a missing Node/npx, given whether the scan is `required` here."""
    if required:
        return MissingToolDecision(
            fail=True,
            message=(
                "Node/npx could not be found and the duplication scan is required in this "
                "context (CI, or NARRATIVETRACE_DUPLICATION_REQUIRED=true)."
            ),
        )
    return MissingToolDecision(
        fail=False,
        message=(
            "Node/npx not found on PATH — duplication report SKIPPED. A skipped report is NOT a "
            "clean scan: nothing was measured."
        ),
    )


def record_skipped(reports_dir: Path, tool: str, reason: str) -> None:
    """Records that `tool`'s scan was skipped for `reason`; readable back via `scan_status`."""
    _write_status(reports_dir, tool, f"skipped: {reason}")


def record_ran_clean(reports_dir: Path, tool: str) -> None:
    """Records that `tool` actually ran and produced a fresh scan; readable back via
    `scan_status`."""
    _write_status(reports_dir, tool, "ran-clean")


def scan_status(reports_dir: Path, tool: str) -> str:
    """`tool`'s most recent recorded outcome: `ran-clean`, `skipped: ...`, or `never-ran` when no
    scan has recorded a status at all — three states, so silence cannot masquerade as coverage."""
    status_file = reports_dir / f"{tool}.status"
    return status_file.read_text(encoding="utf-8").strip() if status_file.is_file() else "never-ran"


def _write_status(reports_dir: Path, tool: str, status: str) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{tool}.status").write_text(status + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# The jscpd invocation itself — thin, untested glue (see the module docstring).
# --------------------------------------------------------------------------- #


def main_source_dirs() -> list[str]:
    """Every distribution's `src` tree — the only trees `duplication_check.decide` ratchets."""
    return sorted(str(path) for path in REPO_ROOT.glob("packages/*/src") if path.is_dir())


def test_source_dirs() -> list[str]:
    """Every distribution's `tests` tree, plus `examples` — reported, never gates."""
    dirs = sorted(str(path) for path in REPO_ROOT.glob("packages/*/tests") if path.is_dir())
    examples = REPO_ROOT / "examples"
    if examples.is_dir():
        dirs.append(str(examples))
    return dirs


def _run_jscpd(source_dirs: list[str], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # nosec B603, B607 # fixed argv, pinned version, no untrusted input
        [
            "npx",
            "--yes",
            f"jscpd@{JSCPD_VERSION}",
            "--min-tokens",
            str(MIN_TOKENS),
            "--ignore-identifiers",
            "--ignore-literals",
            "--format",
            LANGUAGE,
            "--reporters",
            "json",
            "--absolute",
            "--silent",
            "--output",
            str(output_dir),
            *source_dirs,
        ],
        check=True,
        cwd=REPO_ROOT,
    )
    raw_path = output_dir / "jscpd-report.json"
    result: dict[str, Any] = json.loads(raw_path.read_text(encoding="utf-8"))
    return result


def run_report() -> int:
    """Runs jscpd over the main and test trees, writes `duplication.json` and prints the summary
    line. Returns 0 unless Node/npx is missing AND the scan is required in this context (see
    `decide_missing_node`) — a missing Node is otherwise a loud, recorded, non-fatal skip."""
    if shutil.which("npx") is None:
        decision = decide_missing_node(duplication_scan_required())
        record_skipped(DUPLICATION_REPORTS_DIR, TOOL, "no Node/npx on PATH")
        print(f"warning: {decision.message}", file=sys.stderr)
        return 1 if decision.fail else 0

    main_raw = _run_jscpd(main_source_dirs(), DUPLICATION_REPORTS_DIR / "main-raw")
    test_raw = _run_jscpd(test_source_dirs(), DUPLICATION_REPORTS_DIR / "test-raw")
    main = normalize(main_raw, REPO_ROOT)
    test = normalize(test_raw, REPO_ROOT)
    scan = DuplicationScanResult(TOOL, JSCPD_VERSION, LANGUAGE, MIN_TOKENS, main, test)
    write_json(scan, DUPLICATION_REPORTS_DIR / "duplication.json")
    record_ran_clean(DUPLICATION_REPORTS_DIR, TOOL)
    print(summary_line(scan))
    return 0


def main() -> int:
    return run_report()


if __name__ == "__main__":
    sys.exit(main())
