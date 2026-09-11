# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The fixed cross-port verification-report contract (`poe verify-all`).

The contract is written once, in the Java golden repo's `reports/verification/SCHEMA.md`
(pro repo TODO §35E) — this module is this port's implementation of it, not a second
definition: same field names, same four statuses, same 21 category ids. A category this
runtime lacks still gets a row (`status: "not-implemented"`), never a missing one. A port MAY
add metric keys a category genuinely has that Java's doesn't; it MUST NOT rename or drop a
field named in the schema, or invent a category id or status outside the fixed vocabularies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# Exactly these 21 ids, one row each, always — SCHEMA.md's "Category vocabulary".
CATEGORIES: tuple[str, ...] = (
    "unit-tests",
    "coverage",
    "mutation",
    "property",
    "fuzz-tier-a",
    "fuzz-tier-b",
    "benchmarks",
    "allocation",
    "architecture",
    "stress-short",
    "stress-long",
    "conformance",
    "secrets",
    "sast",
    "sca",
    "lint",
    "format",
    "types",
    "complexity",
    "translation",
    "clarity",
)

# Exactly these four values — SCHEMA.md's "Status vocabulary".
STATUSES: tuple[str, ...] = ("passed", "failed", "skipped", "not-implemented")

Status = Literal["passed", "failed", "skipped", "not-implemented"]


@dataclass(frozen=True)
class CategoryResult:
    """One row of `categories` — exactly the fields SCHEMA.md's "Category row" names, no more."""

    category: str
    tool: str
    status: Status
    metrics: dict[str, float | int]
    duration_seconds: float
    note: str | None

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"not a fixed category id: {self.category!r}")
        if self.status not in STATUSES:
            raise ValueError(f"not a fixed status: {self.status!r}")


@dataclass(frozen=True)
class VerificationRun:
    """One run of the report — SCHEMA.md's "Top-level object", minus `overall_status`
    (computed from `categories` at write time, never carried as separate state that could
    drift from the rows it summarizes)."""

    runtime: str
    version: str
    commit: str
    host: str
    started_at: str
    ended_at: str
    categories: tuple[CategoryResult, ...]


def overall_status(categories: tuple[CategoryResult, ...]) -> Literal["passed", "failed"]:
    """`"failed"` iff at least one row failed — a `skipped`/`not-implemented` row never taints
    it, per SCHEMA.md's "Top-level object" table."""
    return "failed" if any(c.status == "failed" for c in categories) else "passed"


def _category_to_json(row: CategoryResult) -> dict[str, object]:
    return {
        "category": row.category,
        "tool": row.tool,
        "status": row.status,
        "metrics": dict(row.metrics),
        "duration_seconds": row.duration_seconds,
        "note": row.note,
    }


def to_report_json(run: VerificationRun) -> dict[str, object]:
    """The exact top-level object SCHEMA.md commits to."""
    return {
        "runtime": run.runtime,
        "version": run.version,
        "commit": run.commit,
        "host": run.host,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "overall_status": overall_status(run.categories),
        "categories": [_category_to_json(row) for row in run.categories],
    }


def write_verification_json(run: VerificationRun, path: Path) -> None:
    """Writes `path`, creating parent directories as needed — the one writer of the report
    JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_report_json(run), indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def read_verification_json(path: Path) -> dict[str, Any]:
    """Raises if `path` is missing or not valid JSON — never called before the write it reads
    back. Typed as `dict[str, Any]`, not `dict[str, object]`: this is arbitrary JSON read back
    for rendering, not a value this module constructs and can keep precisely typed itself."""
    result: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return result


def _status_badge(status: str) -> str:
    return f"**{status.upper()}**" if status == "failed" else status


def _metrics_cell(metrics: dict[str, Any]) -> str:
    if not metrics:
        return "—"
    return "; ".join(f"{key}={value}" for key, value in metrics.items())


def _render_row(row: dict[str, Any]) -> str:
    duration = float(row["duration_seconds"])
    note = row["note"] or ""
    metrics = _metrics_cell(row["metrics"])
    return (
        f"| {row['category']} | {row['tool']} | {_status_badge(row['status'])} | "
        f"{duration:.1f} | {metrics} | {note} |"
    )


def render_markdown(path: Path) -> str:
    """Renders the human table straight from `path` — reads the just-written JSON back rather
    than taking a `VerificationRun` the caller already has, so the Markdown is provably a
    rendering of the committed JSON, never a second, independently computed account of the same
    run (mirrors the Java/TypeScript ports' own renderers)."""
    root = read_verification_json(path)
    lines = [
        f"# Verification run — {root['runtime']} {root['version']}",
        "",
        f"- commit: `{root['commit']}`",
        f"- host: {root['host']}",
        f"- started: {root['started_at']}",
        f"- ended: {root['ended_at']}",
        f"- **overall status: {root['overall_status']}**",
        "",
        "| Category | Tool | Status | Duration (s) | Metrics | Note |",
        "|---|---|---|---|---|---|",
        *(_render_row(row) for row in root["categories"]),
    ]
    return "\n".join(lines) + "\n"
