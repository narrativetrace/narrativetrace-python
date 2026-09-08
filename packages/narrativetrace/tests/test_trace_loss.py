# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What a caller can learn about a trace being incomplete, through the public API.

Mirrors Java ``TraceLossReportingTest`` plus the ``TraceLoss`` value contract. A short trace must
never be indistinguishable from a quiet one.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from narrativetrace.context import NOOP_CONTEXT, ContextVarNarrativeContext
from narrativetrace.ids import SpanId
from narrativetrace.loss import TraceLoss
from narrativetrace.pipeline.event_store import EventStore
from narrativetrace.signature import MethodSignature

_JOIN_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def ctx() -> Iterator[ContextVarNarrativeContext]:
    context = ContextVarNarrativeContext()
    yield context
    context.reset()


def _sig(class_name: str, method_name: str) -> MethodSignature:
    return MethodSignature(class_name, method_name, [])


class TestTraceLossValue:
    def test_nothing_lost_is_a_shared_none(self) -> None:
        assert TraceLoss.none() == TraceLoss(0, 0, 0)
        assert not TraceLoss.none().any()

    def test_dropped_events_alone_count_as_loss(self) -> None:
        assert TraceLoss(1, 0, 0).any()

    def test_refused_scopes_alone_count_as_loss(self) -> None:
        assert TraceLoss(0, 1, 3).any()

    def test_refused_spans_without_a_refused_scope_are_not_loss_on_their_own(self) -> None:
        """A span count is the size of a refusal, never a refusal itself — scopes are the event."""
        assert not TraceLoss(0, 0, 7).any()

    def test_negative_counts_are_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"\ALoss counts must not be negative\Z"):
            TraceLoss(-1, 0, 0)

    def test_losses_sum_for_a_suite_total(self) -> None:
        assert TraceLoss(1, 2, 3).plus(TraceLoss(10, 20, 30)) == TraceLoss(11, 22, 33)

    def test_the_difference_between_two_readings_attributes_loss_to_a_scenario(self) -> None:
        assert TraceLoss(10, 5, 50).since(TraceLoss(4, 1, 20)) == TraceLoss(6, 4, 30)

    def test_a_difference_against_a_later_reading_floors_at_zero(self) -> None:
        """Counters only grow; a reversed pair is a caller error, not a negative loss."""
        assert TraceLoss(1, 1, 1).since(TraceLoss(9, 9, 9)) == TraceLoss.none()


class TestContextReporting:
    def test_an_ordinary_run_reports_no_loss(self, ctx: ContextVarNarrativeContext) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        ctx.exit_method_with_return("ok")
        snapshot = ctx.snapshot()

        def worker() -> None:
            with snapshot.activate():
                ctx.enter_method(_sig("Notifier", "notifyAsync"))
                ctx.exit_method_with_return("true")

        thread = threading.Thread(target=worker, name="loss-worker")
        thread.start()
        thread.join(_JOIN_TIMEOUT_SECONDS)

        assert ctx.trace_loss() == TraceLoss.none()
        assert len(ctx.capture_trace().roots) == 2

    def test_a_context_that_records_nothing_reports_no_loss(self) -> None:
        assert NOOP_CONTEXT.trace_loss() == TraceLoss.none()

    def test_loss_read_twice_around_a_quiet_scenario_attributes_nothing_to_it(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        before = ctx.trace_loss()
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        ctx.exit_method_with_return("ok")

        assert ctx.trace_loss().since(before) == TraceLoss.none()

    def test_a_refused_scope_reaches_the_context_reading(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        ctx.enter_method(_sig("OrderService", "placeOrder"))
        stack = ctx._get_stack()
        stack.max_adopted_spans = 0

        stack.adopt({SpanId.generate(), SpanId.generate()})

        assert ctx.trace_loss() == TraceLoss(0, 1, 2)

    def test_dropped_events_come_from_a_store_that_counts_them(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        """A plain event store sheds nothing; a buffered one reports its backpressure drops."""
        assert ctx.trace_loss().dropped_events == 0
        assert ContextVarNarrativeContext(store=_SheddingStore()).trace_loss() == TraceLoss(7, 0, 0)


class _SheddingStore(EventStore):
    """A store that also reports drops, the way the buffered consumer does."""

    def dropped_count(self) -> int:
        return 7
