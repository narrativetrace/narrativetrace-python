# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A test-suite execution's own identity: a W3C-shaped id and its three-word phrase.

``RunIdentity`` — a trace has a name because a trace id is unreadable; a whole SUITE RUN needs
the same thing for a different reason. Before this type, nothing named "this execution" at all,
so a suite footer, a ``manifest.json``, or a log aggregator query could say "18 scenarios" but
never "which 18-scenario run" when two ran back to back. One :class:`RunIdentity` is generated
once per pytest session (2026-09-13 ruling, item 2) and threaded explicitly to every place that
names the run — never re-derived, never a process-wide singleton a caller cannot vary, which is
exactly what makes "two runs, byte-identical artifacts, different run name" provable.

This is deliberately not a :class:`~narrativetrace.ids.TraceId`: a run is not a trace, has no
spans, and must never be confused with one in an exporter or a schema. It reuses
:meth:`~narrativetrace.ids.TraceId.generate` only because a run id needs the same shape (32
lowercase hex) and the same generator's entropy — borrowing the primitive, not the concept.
:func:`~narrativetrace.namer.trace_name` is reused outright: the whole point of ruling item 2 is
that a run's phrase and a trace's phrase come from the same three tables, so a reader who has
learned to read one learns to read both.

Cross-cutting invariant (ruling item 3): a ``RunIdentity`` must never reach the structural
``.nt`` text, an approved/received trace, an artifact filename, or a manifest per-scenario key —
every call site that computes one of those takes no ``RunIdentity`` at all, so the omission is
structural, not a discipline someone has to remember.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.ids import TraceId


@dataclass(frozen=True, slots=True)
class RunIdentity:
    """One test-suite execution's identity.

    Args:
        id: the run's own W3C-shaped id — 32 lowercase hex characters, unrelated to any trace id.
        name: the three-word phrase :func:`~narrativetrace.namer.trace_name` derives from ``id``.
    """

    id: str
    name: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.name:
            raise ValueError("name must not be empty")

    @staticmethod
    def generate() -> RunIdentity:
        """Generates a fresh run identity: a new random id and the phrase derived from it.

        Call this exactly once per test-suite execution — see this module's own docstring — and
        pass the single result everywhere a run needs to be named. Calling it twice names two
        different runs, which is correct when there genuinely are two (see the byte-identity
        proof), and wrong when a caller wanted the same run twice.
        """
        trace_id = TraceId.generate()
        return RunIdentity(trace_id.value, trace_id.human_name())
