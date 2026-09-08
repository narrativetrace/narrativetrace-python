# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``glossary-scan`` console entry point: a static, no-execution harvest over sources.

``GlossaryScannerMain``. Runs :func:`~narrativetrace_glossary.static_scan.scan_paths`
over the given source roots and feeds the result through
:func:`~narrativetrace_glossary.suite_harvest.run_suite_harvest` — the same merge/write-back/report
sequence the pytest-suite hook uses, so a deliberate ``glossary-scan`` run and an opted-in test run
merge identically.

Unlike ``narrativetrace-clarity``'s CLI, this is a write tool a human runs deliberately (item 6's
"glossary writes opt-in" prerequisite), not a CI gate: it always exits 0. Violations and new terms
are reported to stdout either way, so a caller who wants a hard failure can grep the output or read
``glossary-usage.json``.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from narrativetrace_glossary.json_reader import read_glossary_json
from narrativetrace_glossary.models import Glossary
from narrativetrace_glossary.static_scan import scan_paths
from narrativetrace_glossary.suite_harvest import GLOSSARY_JSON_FILE, run_suite_harvest
from narrativetrace_glossary.summary_formatter import format_violation_details
from narrativetrace_glossary.usage_report import USAGE_REPORT_FILE

if TYPE_CHECKING:
    from collections.abc import Sequence

_DEFAULT_OUTPUT_DIR = "build/narrativetrace"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="glossary-scan")
    parser.add_argument("sources", nargs="+", help="Python files or directories to scan")
    parser.add_argument("--glossary-dir", default=".", help="directory holding glossary.json")
    parser.add_argument("--output-dir", default=_DEFAULT_OUTPUT_DIR)
    return parser


def _existing_glossary(glossary_dir: Path) -> Glossary:
    path = glossary_dir / GLOSSARY_JSON_FILE
    if not path.is_file():
        return Glossary()
    return read_glossary_json(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    """Scans sources, merges into the committed glossary, and reports. Always exits 0."""
    args = _build_parser().parse_args(argv)
    glossary_dir = Path(args.glossary_dir)
    candidates = scan_paths(args.sources, _existing_glossary(glossary_dir))
    result = run_suite_harvest(candidates, glossary_dir=glossary_dir, output_dir=args.output_dir)

    print(result.summary)
    details = format_violation_details(result.violations)
    if details:
        print(details)
    print(f"Glossary: {glossary_dir / GLOSSARY_JSON_FILE}")
    print(f"Usage report: {Path(args.output_dir) / USAGE_REPORT_FILE}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
