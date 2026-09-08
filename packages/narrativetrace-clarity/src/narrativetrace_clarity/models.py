# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Result and issue value types for clarity analysis.

``ClarityResult`` and ``ClarityIssue`` (with its ``Severity`` enum). Renderers, JSON
export, and the quality gate all consume these rather than recomputing scores or rankings.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum


class Severity(Enum):
    """Issue severity with an integer weight used for impact ranking."""

    HIGH = 3
    MEDIUM = 2
    LOW = 1

    @property
    def weight(self) -> int:
        """The severity weight (HIGH 3, MEDIUM 2, LOW 1)."""
        return self.value


@dataclass(frozen=True, slots=True)
class ClarityIssue:
    """One actionable naming issue with a suggestion, severity, and impact score."""

    category: str
    element: str
    suggestion: str
    severity: Severity = Severity.MEDIUM
    occurrences: int = 1
    impact_score: float = field(default=float(Severity.MEDIUM.weight))

    def with_occurrences(self, occurrences: int) -> ClarityIssue:
        """Returns a copy scaled to ``occurrences`` with a recomputed impact score."""
        return replace(
            self,
            occurrences=occurrences,
            impact_score=float(self.severity.weight * occurrences),
        )


@dataclass(frozen=True, slots=True)
class ClarityResult:
    """Weighted clarity scores for one scenario/class plus its ranked issues."""

    overall_score: float
    method_name_score: float
    class_name_score: float
    parameter_name_score: float
    structural_score: float
    cohesion_score: float
    issues: list[ClarityIssue] = field(default_factory=list)
