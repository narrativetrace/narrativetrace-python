# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The bounded ledgers behind adoption: what a stack accepts, and what it refuses.

Mirrors Java ``TraceStackLiveChildTest``. These are boundary conditions an end-to-end test would
need ten thousand workers to reach, so they exercise :class:`~narrativetrace.context._TraceStack`
directly through the same test seam Java uses — a lowered ceiling.
"""

from __future__ import annotations

import gc

import pytest

from narrativetrace.context import _TraceStack
from narrativetrace.ids import SpanId


def _stack(max_adopted_spans: int = 5) -> _TraceStack:
    return _TraceStack(max_adopted_spans=max_adopted_spans)


class TestWhatALiveChildContributes:
    def test_a_stack_with_no_live_children_reports_no_spans(self) -> None:
        assert _stack().live_child_span_ids() == set()

    def test_a_live_childs_spans_are_reportable_by_the_origin(self) -> None:
        origin, child = _stack(), _stack()
        span_id = SpanId.generate()
        origin.register_live_child(child)

        child.push_active(span_id)

        assert origin.live_child_span_ids() == {span_id}

    def test_a_live_child_contributes_exactly_what_it_will_hand_over_at_close(self) -> None:
        """One definition, not two — which is what stops a call appearing and then vanishing."""
        origin, child = _stack(), _stack()
        own, from_grandchild = SpanId.generate(), SpanId.generate()
        child.push_active(own)
        child.adopt({from_grandchild})
        origin.register_live_child(child)

        assert origin.live_child_span_ids() == {own, from_grandchild}
        assert child.reportable_span_ids() == origin.live_child_span_ids()

    def test_a_live_grandchild_reaches_the_origin_through_its_parent(self) -> None:
        origin, child, grandchild = _stack(), _stack(), _stack()
        child_span, grandchild_span = SpanId.generate(), SpanId.generate()
        child.push_active(child_span)
        grandchild.push_active(grandchild_span)
        origin.register_live_child(child)
        child.register_live_child(grandchild)

        assert origin.live_child_span_ids() == {child_span, grandchild_span}

    def test_a_chain_of_live_stacks_is_walked_to_its_end(self) -> None:
        stacks = [_stack() for _ in range(6)]
        spans = [SpanId.generate() for _ in stacks]
        for index, stack in enumerate(stacks):
            stack.push_active(spans[index])
            if index:
                stacks[index - 1].register_live_child(stack)

        assert stacks[0].reportable_span_ids() == set(spans)

    def test_a_stack_with_nothing_of_its_own_still_reports_what_its_children_have(self) -> None:
        origin, child = _stack(), _stack()
        child_span = SpanId.generate()
        child.push_active(child_span)
        origin.register_live_child(child)

        assert origin.reportable_span_ids() == {child_span}

    def test_a_span_reachable_through_both_adoption_and_a_live_child_is_reported_once(self) -> None:
        origin, child = _stack(), _stack()
        shared = SpanId.generate()
        child.push_active(shared)
        origin.register_live_child(child)
        # The window scope close opens: adopt() has run, unregister_live_child() has not.
        origin.adopt(child.reportable_span_ids())

        assert origin.reportable_span_ids() == {shared}

    def test_every_live_child_contributes(self) -> None:
        origin, first, second = _stack(), _stack(), _stack()
        first_span, second_span = SpanId.generate(), SpanId.generate()
        first.push_active(first_span)
        second.push_active(second_span)

        origin.register_live_child(first)
        origin.register_live_child(second)

        assert origin.live_child_span_ids() == {first_span, second_span}

    def test_unregistering_ends_the_contribution(self) -> None:
        origin, child = _stack(), _stack()
        child.push_active(SpanId.generate())
        registration = origin.register_live_child(child)

        origin.unregister_live_child(registration)

        assert origin.live_child_span_ids() == set()

    def test_unregistering_on_a_stack_that_never_registered_is_harmless(self) -> None:
        origin, other = _stack(), _stack()
        registration = other.register_live_child(_stack())

        origin.unregister_live_child(registration)

        assert origin.live_child_span_ids() == set()

    def test_a_collected_child_contributes_nothing_and_frees_its_slot(self) -> None:
        origin = _stack(1)
        collected = _stack(1)
        collected.push_active(SpanId.generate())
        origin.register_live_child(collected)

        del collected  # what the garbage collector does to a worker that died mid-scope
        gc.collect()

        assert origin.live_child_span_ids() == set()
        replacement = _stack(1)
        replacement.push_active(SpanId.generate())
        assert origin.register_live_child(replacement) is not None, (
            "the cleared registration must have been pruned, or the ceiling leaks slots"
        )


class TestRegistrationGuards:
    def test_a_null_child_is_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"\AChild stack is required\Z"):
            _stack().register_live_child(None)  # type: ignore[arg-type]

    def test_a_stack_cannot_register_itself(self) -> None:
        origin = _stack()
        with pytest.raises(ValueError, match=r"\AA stack cannot be its own live child\Z"):
            origin.register_live_child(origin)


class TestAdoptionCeiling:
    def test_the_ceiling_of_the_receiving_stack_bounds_what_it_accepts_from_a_whole_chain(
        self,
    ) -> None:
        """All-or-nothing: a prefix would strand a grandchild whose parent stayed out."""
        origin = _stack(2)
        child = _stack()
        child.push_active(SpanId.generate())
        child.adopt({SpanId.generate(), SpanId.generate()})

        origin.adopt(child.reportable_span_ids())

        assert origin.adopted_span_ids() == set()
        assert origin.refused_scopes == 1
        assert origin.refused_spans == 3

    def test_a_batch_that_exactly_fills_the_ceiling_is_accepted(self) -> None:
        origin = _stack(2)
        spans = {SpanId.generate(), SpanId.generate()}

        origin.adopt(spans)

        assert origin.adopted_span_ids() == spans
        assert origin.refused_scopes == 0

    def test_a_refusal_leaves_what_was_already_adopted_intact(self) -> None:
        origin = _stack(2)
        first = {SpanId.generate()}
        origin.adopt(first)

        origin.adopt({SpanId.generate(), SpanId.generate()})

        assert origin.adopted_span_ids() == first
        assert origin.refused_scopes == 1
        assert origin.refused_spans == 2

    def test_an_empty_hand_over_is_neither_adopted_nor_refused(self) -> None:
        origin = _stack(0)

        origin.adopt(set())

        assert origin.refused_scopes == 0
        assert origin.refused_spans == 0

    def test_refusals_accumulate_across_scopes(self) -> None:
        origin = _stack(1)

        origin.adopt({SpanId.generate(), SpanId.generate()})
        origin.adopt({SpanId.generate(), SpanId.generate(), SpanId.generate()})

        assert origin.refused_scopes == 2
        assert origin.refused_spans == 5


class TestRegistrationCeiling:
    def test_the_ceiling_refuses_further_registrations(self) -> None:
        origin = _stack(1)
        kept = _stack(1)
        refused = _stack(1)
        kept.push_active(SpanId.generate())
        refused.push_active(SpanId.generate())

        assert origin.register_live_child(kept) is not None
        assert origin.register_live_child(refused) is None
        assert len(origin.live_child_span_ids()) == 1

    def test_a_refused_registration_is_not_counted_as_a_lost_scope(self) -> None:
        """Nothing is lost by a refusal here: the spans still arrive through adopt() at close."""
        origin = _stack(1)
        origin.register_live_child(_stack(1))

        origin.register_live_child(_stack(1))

        assert origin.refused_scopes == 0
        assert origin.refused_spans == 0

    def test_unregistering_a_refused_registration_is_harmless(self) -> None:
        origin = _stack(1)
        kept = _stack(1)
        kept.push_active(SpanId.generate())
        origin.register_live_child(kept)

        origin.unregister_live_child(None)

        assert len(origin.live_child_span_ids()) == 1
