# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-174: every emitter that writes an exception message reads it through the shared filter
(``narrativetrace.exception_message``), so a credential-shaped message is the marker."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

import pytest

from narrativetrace import exception_message
from narrativetrace.canonical import MonotonicAnchor, entry_from_event
from narrativetrace.events import ExitEvent
from narrativetrace.export import export
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.logging_bridge import LoggingTraceConsumer
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.redaction import REDACTED_MARKER
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree
from narrativetrace.tree_canonical import entries_from_tree

# Public test PAN, not a real credential; the shape policy recognises these bytes.
_PAN = "4111111111111111"


def _span() -> SpanContext:
    return SpanContext(trace_id=TraceId("0" * 32), span_id=SpanId("a" * 16))


class TestLoggingBridge:
    def test_the_exception_line_carries_the_marker_never_the_message(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="narrativetrace")
        LoggingTraceConsumer().accept(ExitEvent(_span(), 10, Threw(ValueError(_PAN))))
        assert caplog.records[-1].getMessage() == f"!! ValueError: {REDACTED_MARKER}"


class TestCanonicalEvent:
    def test_the_exit_entry_carries_the_marker_in_message_and_exception_message(self) -> None:
        anchor = MonotonicAnchor(epoch_millis=1_775_000_000_000, monotonic_nanos=5_000_000_000)
        event = ExitEvent(_span(), anchor.monotonic_nanos, Threw(ValueError(_PAN)))
        entry = entry_from_event(event, anchor=anchor)
        assert entry.exception_message == REDACTED_MARKER
        assert entry.message == f"!! ValueError: {REDACTED_MARKER}"


def _threw_tree(failure: BaseException) -> TraceTree:
    node = TraceNode(
        MethodSignature("Svc", "run", []),
        [],
        Threw(failure),
        duration_nanos=5,
        start_time_nanos=1_775_000_000_000_000_000,
    )
    return TraceTree([node])


class TestTreeCanonical:
    def test_the_exit_entry_carries_the_marker_in_message_and_exception_message(self) -> None:
        exit_entry = entries_from_tree(_threw_tree(ValueError(_PAN)))[1]
        assert exit_entry.exception_message == REDACTED_MARKER
        assert exit_entry.message == f"!! ValueError: {REDACTED_MARKER}"


def _threw_leaf_and_nested(failure: BaseException) -> tuple[TraceTree, TraceTree]:
    """A throwing leaf root (inline site) and a throwing child under a parent (closing site)."""
    leaf = TraceNode(MethodSignature("Svc", "run", []), [], Threw(failure))
    child = TraceNode(MethodSignature("Svc", "child", []), [], Threw(failure))
    parent = TraceNode(MethodSignature("Svc", "parent", []), [child], Returned("x"))
    return TraceTree([leaf]), TraceTree([parent])


class TestIndentedRenderer:
    def test_both_outcome_sites_carry_the_marker_never_the_message(self) -> None:
        for tree in _threw_leaf_and_nested(ValueError(_PAN)):
            out = IndentedTextRenderer().render(tree)
            assert _PAN not in out
            assert f"!! ValueError: {REDACTED_MARKER}" in out


class TestProseRenderer:
    def test_both_outcome_sites_carry_the_marker_never_the_message(self) -> None:
        for tree in _threw_leaf_and_nested(ValueError(_PAN)):
            out = ProseRenderer().render(tree)
            assert _PAN not in out
            assert f"ValueError: {REDACTED_MARKER}" in out


class TestMarkdownRenderer:
    def test_both_outcome_sites_carry_the_marker_never_the_message(self) -> None:
        for tree in _threw_leaf_and_nested(ValueError(_PAN)):
            out = MarkdownRenderer().render(tree)
            assert _PAN not in out
            assert f"`ValueError`: {REDACTED_MARKER}" in out


class TestJsonExporter:
    def test_the_error_message_is_the_marker_never_the_message(self) -> None:
        node = TraceNode(
            MethodSignature("Svc", "run", []), [], Threw(ValueError(_PAN)), span_context=_span()
        )
        text = export(TraceTree([node]))
        assert _PAN not in text
        assert json.loads(text)["events"][1]["errorMessage"] == REDACTED_MARKER


# Sixteen SUPERSCRIPT TWO: `str.isdigit()` says digit, `int()` refuses. The shared reading runs
# the value-shape scan unguarded, so what the scan raises is what the emitter raises.
_NON_DECIMAL_DIGIT_MESSAGE = "²" * 16


class TestNonDecimalDigitMessage:
    """ADV-2026-10-29-1 -- an emitter degrades on a hostile exception message and never raises:
    an observability failure must not become an application failure."""

    def test_adv_2026_10_29_1_the_shared_reading_answers_the_message(self) -> None:
        assert exception_message.of(ValueError(_NON_DECIMAL_DIGIT_MESSAGE)) == (
            _NON_DECIMAL_DIGIT_MESSAGE
        )

    @pytest.mark.parametrize(
        "render",
        [IndentedTextRenderer().render, ProseRenderer().render, MarkdownRenderer().render],
    )
    def test_adv_2026_10_29_1_every_renderer_writes_the_message(
        self, render: Callable[[TraceTree], str]
    ) -> None:
        for tree in _threw_leaf_and_nested(ValueError(_NON_DECIMAL_DIGIT_MESSAGE)):
            assert _NON_DECIMAL_DIGIT_MESSAGE in render(tree)

    def test_adv_2026_10_29_1_the_json_exporter_writes_the_message(self) -> None:
        node = TraceNode(
            MethodSignature("Svc", "run", []),
            [],
            Threw(ValueError(_NON_DECIMAL_DIGIT_MESSAGE)),
            span_context=_span(),
        )
        exported = json.loads(export(TraceTree([node])))
        assert exported["events"][1]["errorMessage"] == _NON_DECIMAL_DIGIT_MESSAGE

    def test_adv_2026_10_29_1_the_logging_bridge_logs_the_message(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="narrativetrace")
        LoggingTraceConsumer().accept(
            ExitEvent(_span(), 10, Threw(ValueError(_NON_DECIMAL_DIGIT_MESSAGE)))
        )
        assert caplog.records[-1].getMessage() == (f"!! ValueError: {_NON_DECIMAL_DIGIT_MESSAGE}")
