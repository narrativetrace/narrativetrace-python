# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Byte-compatible JSON export for clarity results.

``ClarityJsonExporter`` — a hand-rolled compact emitter the quality gate parses instead
of Markdown. Scores are 2-dp (HALF_UP, matching Java's ``String.format("%.2f")``), severities are
upper-case, and duplicate scenario names are preserved as separate array entries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from narrativetrace_clarity._numeric import two_dp as _score

if TYPE_CHECKING:
    from collections.abc import Sequence

    from narrativetrace_clarity.models import ClarityIssue, ClarityResult


def export(results: Sequence[tuple[str, ClarityResult]]) -> str:
    """Exports an ordered list of (scenario name, result) pairs as a JSON document."""
    parts = ['{"version":"1.0","scenarios":[']
    parts.append(",".join(_scenario(name, result) for name, result in results))
    parts.append("]}")
    return "".join(parts)


def _scenario(name: str, result: ClarityResult) -> str:
    fields = [
        f'{{"name":"{_escape(name)}"',
        f',"overallScore":{_score(result.overall_score)}',
        f',"methodNameScore":{_score(result.method_name_score)}',
        f',"classNameScore":{_score(result.class_name_score)}',
        f',"parameterNameScore":{_score(result.parameter_name_score)}',
        f',"structuralScore":{_score(result.structural_score)}',
        f',"cohesionScore":{_score(result.cohesion_score)}',
        ',"issues":[',
        ",".join(_issue(issue) for issue in result.issues),
        "]}",
    ]
    return "".join(fields)


def _issue(issue: ClarityIssue) -> str:
    return (
        f'{{"category":"{_escape(issue.category)}"'
        f',"element":"{_escape(issue.element)}"'
        f',"suggestion":"{_escape(issue.suggestion)}"'
        f',"severity":"{issue.severity.name}"'
        f',"occurrences":{issue.occurrences}'
        f',"impactScore":{_score(issue.impact_score)}}}'
    )


_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


def _escape(text: str) -> str:
    out: list[str] = []
    for char in text:
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif ord(char) < 0x20:
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    return "".join(out)
