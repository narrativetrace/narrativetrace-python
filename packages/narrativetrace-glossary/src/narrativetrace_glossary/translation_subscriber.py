# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders a live pipeline event stream into one translated locale as it happens.

``TranslationSubscriber``. INTENT: the same :meth:`~narrativetrace_glossary.
translation_view.TraceTranslationView.render_entry` a batch, per-trace file uses, driven one event
at a time — this is Phase 7's pipeline seam, letting a translated view exist without waiting for a
trace to finish. Register it as an observer, not the trace's only path: dual-path stays the
default (`../narrative-trace-java` core-pipeline convention) — wire ``on_event`` onto a
:class:`~narrativetrace.pipeline.buffered_consumer.BufferedEventConsumer` via ``consumer.subscribe``
(the best-effort path, matching where the Java golden puts it) or onto a
:class:`~narrativetrace.pipeline.dual_path.DualPathPipeline`'s ``synchronous_listener`` — either
way, one more listener beside the trace's own durable path, never a replacement for it.

Per-trace state lives in a :class:`~narrativetrace.pipeline.perishable.PerishableMap`, bounded by
capacity and TTL so an abandoned or never-completing trace cannot grow this subscriber's memory
without limit. The "glossary gaps" footer is emitted exactly once per trace either way: on the
root span's exit (normal completion) or on eviction (a trace that never finished) — never both,
never silently dropped.

Concurrency markers (fork/join/async-dispatch) carry no trace identity yet
(:func:`~narrativetrace.canonical.entry_from_event`'s group-event mapping sets no ``trace_id``) and
are skipped rather than rendered.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from narrativetrace._boundary import PROPAGATED_EXCEPTIONS
from narrativetrace.canonical import MonotonicAnchor, entry_from_event
from narrativetrace.events import TraceEvent
from narrativetrace.pipeline.perishable import PerishableMap
from narrativetrace_glossary.models import Glossary
from narrativetrace_glossary.translation_view import RenderState, TraceTranslationView

DEFAULT_CAPACITY = 1024
DEFAULT_TTL_SECONDS = 300.0
_EXIT = "method_exit"

_Sink = Callable[[str, str], None]


@dataclass(slots=True)
class _TraceState:
    """A per-trace render sequence, paired with the trace id an eviction callback needs.

    :class:`~narrativetrace.pipeline.perishable.PerishableMap`'s eviction callback receives only
    the value, never the key — carrying ``trace_id`` here is what lets an evicted trace still emit
    its gaps footer to the right file/logger.
    """

    trace_id: str
    render_state: RenderState


def _logger_sink(locale: str) -> _Sink:
    logger = logging.getLogger(f"narrativetrace.i18n.{locale}")

    def sink(_trace_id: str, text: str) -> None:
        logger.info(text)

    return sink


class TranslationSubscriber:
    """Renders a pipeline's event stream into one locale, one trace at a time."""

    def __init__(
        self,
        glossary: Glossary,
        locale: str,
        sink: _Sink | None = None,
        *,
        capacity: int = DEFAULT_CAPACITY,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        namespace_of: Callable[[str], str | None] | None = None,
    ) -> None:
        """Args:
        glossary: the committed glossary to translate against.
        locale: the target locale every event on this subscriber renders into.
        sink: ``(trace_id, text) -> None``, called for every non-empty rendered chunk (a line, or
            the gaps footer). Defaults to an SLF4J-equivalent logger named
            ``narrativetrace.i18n.<locale>`` at INFO — pass
            :meth:`~narrativetrace_glossary.translation_file_sink.TranslationFileSink.write` for
            one file per trace.
        capacity: maximum number of traces with open (not-yet-completed) render state at once.
        ttl_seconds: how long an incomplete trace's state survives before eviction.
        namespace_of: forwarded to :class:`~narrativetrace_glossary.translation_view.
            TraceTranslationView` for context resolution on entries captured before schema 1.2.
        """
        if not locale.strip():
            raise ValueError("locale must not be blank")
        self._view = TraceTranslationView(glossary, namespace_of)
        self._locale = locale
        self._sink = sink if sink is not None else _logger_sink(locale)
        self._anchor = MonotonicAnchor.now()
        self._states: PerishableMap[str, _TraceState] = PerishableMap(
            capacity, ttl_seconds, self._on_evict
        )

    def on_event(self, event: TraceEvent) -> None:
        """Renders one pipeline event, best-effort — a hostile sink must not break the pipeline."""
        try:
            self._handle(event)
        except PROPAGATED_EXCEPTIONS:
            raise
        except BaseException:  # observability failure must never become a pipeline failure
            pass

    def _handle(self, event: TraceEvent) -> None:
        try:
            entry = entry_from_event(event, anchor=self._anchor)
        except TypeError:
            return  # an event type this mapper does not (yet) know — skip, never crash
        if entry.trace_id is None:
            return  # concurrency markers: no trace identity to render against
        state = self._states.get(entry.trace_id)
        if state is None:
            state = _TraceState(entry.trace_id, self._view.new_render_state(self._locale))
            self._states.put(entry.trace_id, state)
        text = self._view.render_entry(entry, state.render_state)
        if text:
            self._emit(state.trace_id, text)
        if entry.nt_event_type == _EXIT and entry.parent_span_id is None:
            self._complete(state)

    def _complete(self, state: _TraceState) -> None:
        self._emit_footer(state)
        self._states.remove(state.trace_id)

    def _on_evict(self, state: _TraceState) -> None:
        self._emit_footer(state)

    def _emit_footer(self, state: _TraceState) -> None:
        footer = self._view.render_gaps_footer(state.render_state)
        if footer:
            self._emit(state.trace_id, footer)

    def _emit(self, trace_id: str, text: str) -> None:
        try:
            self._sink(trace_id, text)
        except PROPAGATED_EXCEPTIONS:
            raise
        except BaseException:  # a hostile sink must not break the pipeline it only observes
            pass
