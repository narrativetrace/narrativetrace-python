# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The structural delta between two ``.nt`` artifacts.

``StructuralDelta`` / ``ScenarioDelta``. The comparison engine for the test-loop feedback
surfaces — the post-run console delta line, the failure delta against the last-green artifact, and
approval-mode verification. Sameness is equality of the artifact's lines with span ids set aside:
the renderer (:class:`~narrativetrace.render.structural.StructuralTraceRenderer`) is
deterministic, so the same lines mean the same behaviour, and any difference is real change worth
surfacing. A baseline written before span ids existed, or checked out with CRLF line endings,
still compares.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from narrativetrace.output import line_diff
from narrativetrace.render import span_id


@dataclass(frozen=True, slots=True)
class StructuralDelta:
    """Compares a baseline artifact (last green or approved) against the current one."""

    baseline: str
    current: str

    @property
    def unchanged(self) -> bool:
        """True iff the two artifacts have the same lines once span ids are set aside — the
        scenario's structure did not change."""
        return without_ids(self.baseline) == without_ids(self.current)

    def only_omits(self) -> bool:
        """True when the current document differs from the baseline only by omission — every one
        of its lines appears in the baseline, in order, span ids set aside. The question to ask of
        a run known to be incomplete: an omission shifts the ids of later siblings, which is not a
        change."""
        return line_diff.is_subsequence(without_ids(self.baseline), without_ids(self.current))

    def summary(self) -> str:
        """Compact per-signature call-count changes, e.g. ``+4 calls
        CurrencyConverter.toBaseCurrency``; empty when :attr:`unchanged`."""
        if self.unchanged:
            return ""
        changes = self._count_changes()
        if not changes:
            return "structure changed"
        return ", ".join(_format_change(signature, count) for signature, count in changes.items())

    def diff(self) -> str:
        """Full-document line diff in the conventional format: ``-`` removed, ``+`` added, one
        leading space on unchanged context lines; empty when :attr:`unchanged`. Lines match with
        span ids set aside, and each side prints its own: a context line whose id an earlier
        insertion or removal shifted cites the baseline's, ``#1.3 - A.b()  (was #1.2)``."""
        if self.unchanged:
            return ""
        return line_diff.unified(self.baseline, self.current, span_id.without_id, _context_line)

    def _count_changes(self) -> dict[str, int]:
        """Signature → net count, in first-seen order (``current`` before ``baseline``) so an
        added signature is listed before a purely-removed one — mirrors a Java ``LinkedHashMap``
        merged in that same order."""
        counts: dict[str, int] = {}
        for signature in _call_signatures(self.current):
            counts[signature] = counts.get(signature, 0) + 1
        for signature in _call_signatures(self.baseline):
            counts[signature] = counts.get(signature, 0) - 1
        return {signature: count for signature, count in counts.items() if count != 0}


def without_ids(document: str) -> str:
    """The document's lines with every span id removed, joined by LF — the form sameness is
    decided on. Ids are derived from position and carry no behaviour of their own; line
    terminators (LF, CR, CRLF) and a final newline are encoding, not structure, and the line diff
    never sees them either."""
    return "\n".join(span_id.without_id(line) for line in line_diff.lines(document))


def _context_line(was: str, now: str) -> str:
    """An unchanged line as the current document prints it, citing the baseline's id when it
    shifted. A baseline written before span ids existed has none to cite."""
    was_id = span_id.of(was)
    return now if was_id is None or was_id == span_id.of(now) else f"{now}  (was {was_id})"


def _call_signatures(document: str) -> list[str]:
    """Call lines are ``- Class.method(params)`` at any indent, after any span id; fork markers
    and blanks are not calls."""
    shapes = (span_id.without_id(line).lstrip() for line in line_diff.lines(document))
    return [_signature_of(shape) for shape in shapes if shape.startswith("- ")]


def _signature_of(call_line: str) -> str:
    open_paren = call_line.find("(")
    return call_line[2:] if open_paren < 0 else call_line[2:open_paren]


def _format_change(signature: str, count: int) -> str:
    magnitude = abs(count)
    noun = " call " if magnitude == 1 else " calls "
    sign = "+" if count > 0 else "-"
    return f"{sign}{magnitude}{noun}{signature}"


class Kind(Enum):
    """How a scenario's structure relates to its last-green (or approved) artifact."""

    NEW = "new"
    UNCHANGED = "unchanged"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class ScenarioDelta:
    """One scenario's structural status against its last-green ``.nt`` artifact.

    The unit the trace writer reports upward after each test — the suite footer aggregates these
    into the post-run delta line, and the failure surface prints the diff of the failing scenario.

    Args:
        scenario: the humanized scenario name (the ``scenario:`` header value).
        kind: NEW (no baseline yet), UNCHANGED (same lines, ids set aside), or CHANGED.
        summary: compact change summary (``+4 calls X.y``); empty unless CHANGED.
        diff: readable line diff against the baseline; empty unless CHANGED.
    """

    scenario: str
    kind: Kind
    summary: str = ""
    diff: str = ""

    @staticmethod
    def of(scenario: str, baseline: str | None, current: str) -> ScenarioDelta:
        """Classifies the current artifact against the baseline; ``baseline is None`` means no
        last-green artifact exists yet — the scenario is NEW."""
        if baseline is None:
            return ScenarioDelta(scenario, Kind.NEW)
        structural = StructuralDelta(baseline, current)
        if structural.unchanged:
            return ScenarioDelta(scenario, Kind.UNCHANGED)
        return ScenarioDelta(scenario, Kind.CHANGED, structural.summary(), structural.diff())
