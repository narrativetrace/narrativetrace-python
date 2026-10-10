# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A: "reuse the runtime's deny-list and value shapes, never copy them" — kept by an ASSERTION
rather than by a dependency, because there cannot be one. Mirrors Java's
``FeedbackGateCoversTheRedactionDefaultTest``.

INTENT: ``narrativetrace-tooling`` declares zero dependencies and its own architecture gate
(``tests/test_architecture.py``) fails on any import of ``narrativetrace`` — the edge would be a
cycle, since the ``narrativetrace`` distribution depends on THAT one. So the value-free gate
restates the vocabulary and the shapes as data, and THIS package, the only one that may see both,
holds them together: every name and every value the renderer redacts by default must also be refused
by the
gate. A term dropped from one side and not the other fails here, inside ``poe check``, instead of in
a public issue.

**@llmNote** The implication is asserted in ONE direction, and the asymmetry is the design. The
renderer refuses an entropy heuristic and verifies every national-id checksum because a false
positive there silently blanks a user's data; the gate uses entropy and matches id SHAPES because a
false positive here is a refusal that names its rule. So the gate is a strict superset, and
:meth:`TestTheAsymmetryIsOnPurpose.test_the_gate_refuses_what_the_renderer_leaves_visible` pins that
it really is strict — otherwise a future simplification could quietly make the two equal and lose
the entropy half.
"""

from __future__ import annotations

import pytest
from hostile_corpus import RedactionCase, redactions

from narrativetrace.redaction import REDACTED_MARKER, RedactionPolicy
from narrativetrace_tooling.feedback import rules_refusing
from narrativetrace_tooling.feedback.matchers import REDACTION_MARKER
from narrativetrace_tooling.feedback.rules import MARKER, NAMED_SECRET, VALUE_SHAPE

NEUTRAL_VALUE = "ada"
"""A value no rule of the gate reacts to on its own — so a refusal below is about the NAME."""


def _denied_names() -> tuple[RedactionCase, ...]:
    return tuple(case for case in redactions() if case.expects_redaction and case.name is not None)


def _secret_shaped_values() -> tuple[RedactionCase, ...]:
    return tuple(case for case in redactions() if case.expects_redaction and case.value is not None)


class TestTheCanaryThisSuiteBindsIsItselfFilable:
    def test_a_neutral_value_passes_every_rule(self) -> None:
        """Without this, every name row below would pass for the wrong reason: a canary the gate
        refuses on its own makes "the gate refused ``name: canary``" say nothing about the name."""
        assert rules_refusing(NEUTRAL_VALUE) == ()


class TestEveryNameTheRendererRedactsIsAlsoRefusedByTheGate:
    @pytest.mark.parametrize("case", _denied_names(), ids=str)
    def test_the_runtime_redacts_this_name(self, case: RedactionCase) -> None:
        """Half one: the corpus row is current. A row the runtime no longer redacts is a stale row,
        and asserting the gate against it would be asserting against nothing."""
        assert RedactionPolicy.DEFAULT.should_redact(case.name), (
            f"{case.id}: the runtime must redact {case.name!r}, or the corpus row is stale"
        )

    @pytest.mark.parametrize("case", _denied_names(), ids=str)
    def test_and_so_does_the_gate_when_a_value_sits_beside_it(self, case: RedactionCase) -> None:
        refusing = rules_refusing(f"{case.name}: {NEUTRAL_VALUE}")

        assert NAMED_SECRET in refusing, (
            f"{case.id}: the gate must refuse {case.name!r} carrying a value"
        )

    def test_the_name_half_of_the_corpus_is_not_empty(self) -> None:
        assert len(_denied_names()) > 20


class TestEveryValueShapeTheRendererRedactsIsAlsoRefusedByTheGate:
    @pytest.mark.parametrize("case", _secret_shaped_values(), ids=str)
    def test_the_runtime_redacts_this_value_shape(self, case: RedactionCase) -> None:
        assert RedactionPolicy.DEFAULT.should_redact_value(case.value or ""), (
            f"{case.id}: the runtime must redact this value shape, or the corpus row is stale"
        )

    @pytest.mark.parametrize("case", _secret_shaped_values(), ids=str)
    def test_and_so_does_the_gate(self, case: RedactionCase) -> None:
        refusing = rules_refusing(case.value or "")

        assert refusing != (), f"{case.id}: the gate must refuse {case.value!r}"

    def test_the_value_half_of_the_corpus_is_not_empty(self) -> None:
        assert len(_secret_shaped_values()) > 20


class TestTheRedactionMarkerIsOneStringOnBothSides:
    def test_the_gates_restated_marker_is_the_runtimes_own_literal(self) -> None:
        """The gate writes the marker out rather than importing it (zero-dependency contract), so
        this is the assertion that keeps the two from drifting."""
        assert REDACTION_MARKER == REDACTED_MARKER

    def test_the_gate_refuses_text_carrying_the_runtimes_marker(self) -> None:
        assert MARKER in rules_refusing(f"place_order returned {REDACTED_MARKER}")


class TestTheAsymmetryIsOnPurpose:
    def test_the_gate_refuses_what_the_renderer_leaves_visible(self) -> None:
        """A CPF whose check digits are wrong. Both decisions are right for their own surface — the
        renderer would be blanking a user's data on a guess, the gate would be publishing an
        identity number — and this test is what stops the next person from "fixing" the
        disagreement into agreement and losing the entropy half with it. Corpus row
        ``value-shape-checksum-failing-lookalike``."""
        bad_check_digits = "52998224726"

        assert not RedactionPolicy.DEFAULT.should_redact_value(bad_check_digits), (
            "the renderer leaves a checksum-failing lookalike visible, by ruling"
        )
        assert VALUE_SHAPE in rules_refusing(bad_check_digits), (
            "the gate refuses it anyway: an unfilable report costs a sentence, a public id does not"
        )

    def test_the_converse_is_deliberately_not_asserted_anywhere_in_this_module(self) -> None:
        """The one-way reading, stated as a test rather than only as prose: there is a string the
        gate refuses and the renderer does not, so "every value the GATE refuses is also redacted
        by the renderer" is false — and a future test asserting it would be asserting the gate down
        to the renderer's own tradeoff."""
        a_long_opaque_run = "Zm9vYmFyYmF6cXV1eHdhbGRvZnJlZG1pbmU9"

        assert rules_refusing(a_long_opaque_run) != ()
        assert not RedactionPolicy.DEFAULT.should_redact_value(a_long_opaque_run)
