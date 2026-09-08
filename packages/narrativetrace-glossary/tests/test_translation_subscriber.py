# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Live pipeline rendering: TranslationSubscriber on_event."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

import pytest
from narrativetrace_glossary.models import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    TermKind,
    TermStatus,
)
from narrativetrace_glossary.translation_subscriber import DEFAULT_CAPACITY, TranslationSubscriber

from narrativetrace.events import EnterEvent, ExitEvent, ForkCreatedEvent
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.outcomes import Returned, Threw, TraceOutcome
from narrativetrace.pipeline.buffered_consumer import BufferedEventConsumer
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext

_FIRST_SEEN = date(2026, 8, 11)


def _term(term: str, translations: dict[str, str], kind: TermKind = TermKind.WORD) -> GlossaryTerm:
    return GlossaryTerm(
        term, "billing", kind, TermStatus.CURATED, translations=translations, first_seen=_FIRST_SEEN
    )


def _glossary(*extra: GlossaryTerm) -> Glossary:
    return Glossary({"billing": BoundedContext("billing", ["acme.billing"])}, list(extra))


def _enter(
    trace_id: TraceId,
    span_id: SpanId,
    parent: SpanId | None,
    class_name: str,
    method: str,
    parameters: list[ParameterCapture] | None = None,
) -> EnterEvent:
    span = SpanContext(trace_id, span_id, parent, span_name=f"{class_name}.{method}")
    signature = MethodSignature(class_name, method, parameters or [], package_name="acme.billing")
    return EnterEvent(span, 0, signature)


def _exit(
    trace_id: TraceId,
    span_id: SpanId,
    parent: SpanId | None,
    class_name: str,
    method: str,
    outcome: TraceOutcome | None = None,
) -> ExitEvent:
    span = SpanContext(trace_id, span_id, parent, span_name=f"{class_name}.{method}")
    return ExitEvent(span, 10, outcome if outcome is not None else Returned(None))


def _recording_sink() -> tuple[list[tuple[str, str]], Callable[[str, str], None]]:
    calls: list[tuple[str, str]] = []

    def sink(trace_id: str, text: str) -> None:
        calls.append((trace_id, text))

    return calls, sink


def test_renders_a_root_span_and_emits_on_completion() -> None:
    glossary = _glossary(_term("open", {"es": "abre"}))
    calls, sink = _recording_sink()
    subscriber = TranslationSubscriber(glossary, "es", sink)
    trace_id = TraceId.generate()
    span_id = SpanId.generate()

    subscriber.on_event(_enter(trace_id, span_id, None, "OverdraftService", "open"))
    subscriber.on_event(_exit(trace_id, span_id, None, "OverdraftService", "open"))

    joined = "".join(text for _, text in calls)
    assert "OverdraftService.abre (open)" in joined
    assert "-> " in joined


def test_gaps_footer_emitted_on_root_completion() -> None:
    calls, sink = _recording_sink()
    subscriber = TranslationSubscriber(_glossary(), "es", sink)
    trace_id = TraceId.generate()
    span_id = SpanId.generate()

    subscriber.on_event(_enter(trace_id, span_id, None, "X", "unknownMethod"))
    subscriber.on_event(_exit(trace_id, span_id, None, "X", "unknownMethod"))

    joined = "".join(text for _, text in calls)
    assert "Vacíos del glosario" in joined
    assert "unknown method" in joined


def test_two_traces_are_isolated_from_each_other() -> None:
    calls, sink = _recording_sink()
    subscriber = TranslationSubscriber(_glossary(_term("open", {"es": "abre"})), "es", sink)
    trace_a, trace_b = TraceId.generate(), TraceId.generate()
    span_a, span_b = SpanId.generate(), SpanId.generate()

    subscriber.on_event(_enter(trace_a, span_a, None, "A", "open"))
    subscriber.on_event(_enter(trace_b, span_b, None, "B", "open"))
    subscriber.on_event(_exit(trace_a, span_a, None, "A", "open"))
    subscriber.on_event(_exit(trace_b, span_b, None, "B", "open"))

    trace_ids_seen = {trace_id for trace_id, _ in calls}
    assert trace_ids_seen == {str(trace_a), str(trace_b)}


def test_concurrency_events_carry_no_trace_identity_and_are_skipped() -> None:
    calls, sink = _recording_sink()
    subscriber = TranslationSubscriber(_glossary(), "es", sink)

    subscriber.on_event(ForkCreatedEvent("group-1", 0))

    assert calls == []


class InsufficientFundsException(RuntimeError):
    """Exception name normalizes to "insufficient fund" (suffix stripped)."""


def test_a_root_exception_renders_and_completes_the_trace() -> None:
    calls, sink = _recording_sink()
    subscriber = TranslationSubscriber(
        _glossary(_term("insufficient fund", {"es": "fondos insuficientes"}, TermKind.NOUN_PHRASE)),
        "es",
        sink,
    )
    trace_id = TraceId.generate()
    span_id = SpanId.generate()

    subscriber.on_event(_enter(trace_id, span_id, None, "PaymentService", "charge"))
    subscriber.on_event(
        _exit(
            trace_id,
            span_id,
            None,
            "PaymentService",
            "charge",
            outcome=Threw(InsufficientFundsException("boom")),
        )
    )

    joined = "".join(text for _, text in calls)
    assert "!! fondos insuficientes" in joined


def test_capacity_eviction_still_emits_the_gaps_footer() -> None:
    calls, sink = _recording_sink()
    subscriber = TranslationSubscriber(_glossary(), "es", sink, capacity=1)
    first_trace, second_trace = TraceId.generate(), TraceId.generate()

    # First trace never completes (no exit) — still open when the second trace's put evicts it.
    subscriber.on_event(_enter(first_trace, SpanId.generate(), None, "X", "unknownOne"))
    subscriber.on_event(_enter(second_trace, SpanId.generate(), None, "Y", "unknownTwo"))

    first_trace_output = "".join(text for trace_id, text in calls if trace_id == str(first_trace))
    assert "Vacíos del glosario" in first_trace_output


def test_default_capacity_constant() -> None:
    assert DEFAULT_CAPACITY == 1024


def test_default_sink_is_a_named_logger(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("INFO", logger="narrativetrace.i18n.es")
    subscriber = TranslationSubscriber(_glossary(_term("open", {"es": "abre"})), "es")
    trace_id = TraceId.generate()
    span_id = SpanId.generate()

    subscriber.on_event(_enter(trace_id, span_id, None, "X", "open"))
    subscriber.on_event(_exit(trace_id, span_id, None, "X", "open"))

    assert any("X.abre (open)" in record.message for record in caplog.records)


def test_a_hostile_sink_does_not_break_the_subscriber() -> None:
    def hostile(_trace_id: str, _text: str) -> None:
        raise RuntimeError("boom")

    subscriber = TranslationSubscriber(_glossary(), "es", hostile)
    trace_id = TraceId.generate()
    span_id = SpanId.generate()

    subscriber.on_event(_enter(trace_id, span_id, None, "X", "open"))  # must not raise
    subscriber.on_event(_exit(trace_id, span_id, None, "X", "open"))  # must not raise


def test_rejects_a_blank_locale() -> None:
    with pytest.raises(ValueError, match=r"\Alocale must not be blank\Z"):
        TranslationSubscriber(_glossary(), "")


def test_end_to_end_through_a_buffered_event_consumer() -> None:
    """The real Phase-7 pipeline seam: subscribe onto BufferedEventConsumer, no bypass."""
    calls, sink = _recording_sink()
    subscriber = TranslationSubscriber(_glossary(_term("open", {"es": "abre"})), "es", sink)
    consumer = BufferedEventConsumer(start_consumer=False)
    consumer.subscribe(subscriber.on_event)
    trace_id = TraceId.generate()
    span_id = SpanId.generate()

    consumer.accept(_enter(trace_id, span_id, None, "X", "open"))
    consumer.accept(_exit(trace_id, span_id, None, "X", "open"))
    consumer.flush()

    joined = "".join(text for _, text in calls)
    assert "X.abre (open)" in joined
    consumer.close()
