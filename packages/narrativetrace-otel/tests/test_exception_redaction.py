# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-174: an exception message is redacted by the shared reading on every OTel sink, the exception
event included (mirrors Java's ``ExceptionEventRedactionTest``, B-159)."""

from __future__ import annotations

from narrativetrace_otel import attributes
from opentelemetry.sdk.trace import Event
from otel_harness import Harness

from narrativetrace.outcomes import Threw
from narrativetrace.redaction import REDACTED_MARKER
from narrativetrace.signature import MethodSignature

# Public test PAN, not a real credential; the shape policy recognises these bytes.
_PAN = "4111111111111111"


def _raise_with_cause() -> BaseException:
    try:
        try:
            raise ValueError(_PAN)
        except ValueError as inner:
            raise RuntimeError("outer") from inner
    except RuntimeError as outer:
        return outer


def _raise(exc: BaseException) -> BaseException:
    try:
        raise exc
    except BaseException as caught:
        return caught


def _finish(otel: Harness, failure: BaseException) -> tuple[object, list[Event]]:
    span = otel.tracer.start_span("probe")
    attributes.set_outcome_attributes(Threw(failure), span)
    span.end()
    finished = otel.named("probe")
    return finished.status, list(finished.events)


class TestStatusDescription:
    def test_a_credential_shaped_message_is_the_marker(self, otel: Harness) -> None:
        status, _ = _finish(otel, _raise(ValueError(_PAN)))
        assert getattr(status, "description", None) == REDACTED_MARKER


class TestExceptionEvent:
    def test_the_event_carries_type_redacted_message_and_frames_without_the_message(
        self, otel: Harness
    ) -> None:
        _, events = _finish(otel, _raise(ValueError(_PAN)))
        assert [e.name for e in events] == ["exception"]
        attrs = dict(events[0].attributes or {})
        assert attrs["exception.type"] == "ValueError"
        assert attrs["exception.message"] == REDACTED_MARKER
        stacktrace = str(attrs["exception.stacktrace"])
        assert _PAN not in stacktrace
        assert stacktrace.startswith("ValueError\n\tat ")

    def test_a_causes_message_is_redacted_in_the_stacktrace_too(self, otel: Harness) -> None:
        _, events = _finish(otel, _raise_with_cause())
        stacktrace = str(dict(events[0].attributes or {})["exception.stacktrace"])
        assert _PAN not in stacktrace
        assert "ValueError" in stacktrace
        assert REDACTED_MARKER in stacktrace

    def test_the_event_message_is_the_plain_message_when_nothing_is_secret(
        self, otel: Harness
    ) -> None:
        _, events = _finish(otel, _raise(ValueError("boom")))
        assert dict(events[0].attributes or {})["exception.message"] == "boom"


class TestNarrativeOutcomeAttribute:
    def test_the_error_outcome_carries_the_redacted_message(self) -> None:
        attrs = attributes.build_event_attributes(
            MethodSignature("C", "m"), Threw(ValueError(_PAN))
        )
        assert attrs["narrative.outcome"] == f"error: {REDACTED_MARKER}"
