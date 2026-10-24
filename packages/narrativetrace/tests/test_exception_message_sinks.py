# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""B-174: every emitter that writes an exception message reads it through the shared filter
(``narrativetrace.exception_message``), so a credential-shaped message is the marker."""

from __future__ import annotations

import json
import logging

import pytest

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
