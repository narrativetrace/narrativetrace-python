# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace-clarity`` console entry point and quality gate.

Scans Python sources, writes ``clarity-report.md`` / ``clarity-results.json``, and optionally
fails the build when scores fall below ``--min-score`` or high-severity issues exceed
``--max-high-issues``. An unknown ``--format`` exits with status 2.

**Vocabulary-check defaults (glossary item 6, prerequisite 5).** This package never imports
``narrativetrace-glossary`` — it already depends the other way (glossary reuses this package's
tokenizer/morphology), and a reverse import would cycle. Instead ``main`` takes an optional
``vocabulary_reader`` callback: unset, this CLI scores with the built-in dictionaries alone,
exactly as it always has; ``narrativetrace_glossary.clarity_scan`` supplies
``read_project_vocabulary`` and is what the root ``clarity`` gate actually runs, making
glossary-aware scoring the gate's default without this package ever knowing what a glossary is.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from narrativetrace_clarity.json_export import export
from narrativetrace_clarity.models import Severity
from narrativetrace_clarity.report import render_suite_report
from narrativetrace_clarity.scanner import scan_paths
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from narrativetrace_clarity.models import ClarityResult

_VALID_FORMATS = ("both", "md", "json")
_DEFAULT_OUTPUT_DIR = "build/narrativetrace"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="narrativetrace-clarity")
    parser.add_argument("sources", nargs="+", help="Python files or directories to scan")
    parser.add_argument("--format", default="both", help="both | md | json (default: both)")
    parser.add_argument("--output-dir", default=_DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-score", type=float, default=None)
    parser.add_argument("--max-high-issues", type=int, default=None)
    parser.add_argument("--warn-only", action="store_true")
    parser.add_argument(
        "--glossary-dir",
        default=".",
        help="directory holding a committed glossary.json (ignored unless a caller injects a "
        "vocabulary_reader; see narrativetrace_glossary.clarity_scan)",
    )
    return parser


def _vocabulary(
    glossary_dir: str, vocabulary_reader: Callable[[str], DomainVocabulary] | None
) -> DomainVocabulary:
    if vocabulary_reader is None:
        return EMPTY
    try:
        return vocabulary_reader(glossary_dir)
    except (OSError, ValueError) as error:
        print(
            f"narrativetrace-clarity: committed glossary at {glossary_dir} could not be read, "
            f"scoring with the built-in dictionaries only ({error})",
            file=sys.stderr,
        )
        return EMPTY


def main(
    argv: Sequence[str] | None = None,
    vocabulary_reader: Callable[[str], DomainVocabulary] | None = None,
) -> int:
    """Runs the clarity scan/gate; returns the process exit code.

    ``vocabulary_reader`` is an injection point, never a positional call site's own name lookup —
    see the module docstring for why the composition lives here rather than as an import.
    """
    args = _build_parser().parse_args(argv)
    if args.format not in _VALID_FORMATS:
        print(f"Unknown format: {args.format} (expected: both, md, or json)", file=sys.stderr)
        return 2

    vocabulary = _vocabulary(args.glossary_dir, vocabulary_reader)
    results = scan_paths(args.sources, vocabulary)
    if not results:
        print(f"No classes found in {', '.join(args.sources)}")
        return 0

    entries = list(results.items())
    _write_outputs(entries, args.format, Path(args.output_dir))
    print(f"Clarity analysis complete: {len(results)} classes scanned")
    print(f"Output: {args.output_dir}")

    violations = _gate(entries, args.min_score, args.max_high_issues)
    for violation in violations:
        print(violation, file=sys.stderr)
    return 1 if violations and not args.warn_only else 0


def _write_outputs(entries: list[tuple[str, ClarityResult]], fmt: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if fmt in ("both", "md"):
        (output_dir / "clarity-report.md").write_text(
            render_suite_report(entries), encoding="utf-8"
        )
    if fmt in ("both", "json"):
        (output_dir / "clarity-results.json").write_text(export(entries), encoding="utf-8")


def _gate(
    entries: list[tuple[str, ClarityResult]], min_score: float | None, max_high_issues: int | None
) -> list[str]:
    violations: list[str] = []
    if min_score is not None:
        violations.extend(
            f"{name}: overall {result.overall_score:.2f} below --min-score {min_score:.2f}"
            for name, result in entries
            if result.overall_score < min_score
        )
    if max_high_issues is not None:
        high = sum(
            1 for _, result in entries for issue in result.issues if issue.severity is Severity.HIGH
        )
        if high > max_high_issues:
            violations.append(
                f"{high} HIGH-severity issues exceed --max-high-issues {max_high_issues}"
            )
    return violations
