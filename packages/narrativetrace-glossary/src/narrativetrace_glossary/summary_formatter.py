# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Console summary line for one harvest run.

``VocabularySummaryFormatter``. One line so a suite footer or a CLI run can report what a
harvest decided without a caller re-deriving it: how many terms joined the glossary, and how many
times code still used a phrasing the glossary has deprecated.
"""

from __future__ import annotations

from collections.abc import Sequence

from narrativetrace_glossary.violations import VocabularyViolation


def format_vocabulary_summary(
    new_term_count: int, violations: Sequence[VocabularyViolation]
) -> str:
    """Renders ``"Vocabulary: N new terms harvested, M deprecated synonyms in use"``.

    ``M`` sums every violation's ``occurrences`` — how many times a deprecated phrasing was
    actually seen in code, not how many distinct phrasings were found.
    """
    if new_term_count < 0:
        raise ValueError(f"new_term_count must not be negative: {new_term_count}")
    deprecated_uses = sum(violation.occurrences for violation in violations)
    return (
        f"Vocabulary: {new_term_count} new terms harvested, "
        f"{deprecated_uses} deprecated synonyms in use"
    )


def format_violation_details(violations: Sequence[VocabularyViolation]) -> str:
    """Renders one line per violation with its rename suggestion, sorted for stable output.

    Empty when there are no violations, so a caller can print it unconditionally after the summary
    line without an extra blank line when nothing was found.
    """
    if not violations:
        return ""
    lines = (
        f"  - {violation.context}/{violation.alias} "
        f"(x{violation.occurrences}, {violation.site}): "
        f"use '{violation.canonical_term}' — rename '{violation.identifier}' to "
        f"'{violation.suggested_rename}'"
        for violation in violations
    )
    return "\n".join(lines)
