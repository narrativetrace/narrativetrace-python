# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A: the shared ``hostile-corpus/feedback.json`` replayed against the value-free gate, one row
at a time. Mirrors Java's ``FeedbackGateCorpusReplayTest``.

INTENT: ``feedback.json`` is the cross-runtime MASTER for this gate — every runtime copies it
verbatim and reimplements only its reader — so what it means is asserted here rather than agreed in
prose. A row is a decision: "this text must never reach a public issue, for this named reason", or
"this text must be filable, or an agent will learn to work around the gate".

**The ACCEPTED half lands first, and keeps landing.** It is the half a port gets wrong: an install
coordinate, a doctor finding id, a hyphenated sentence and a real structural-artifact path at 3.958
bits per character all have to pass, and a gate that refuses any of them is one an agent routes
around — which leaves every report unchecked instead of one. So this file's accepted replay is a
standing constraint from the first rule onward: every rule added after it has to keep all 23 rows
filable.

**@llmNote** A rejected row asserts the named rule is AMONG the refusing rules, not that it is the
only one. Several rules firing on one line is the normal case — a pasted rendered trace breaks the
call rule and the duration rule together — and demanding exactness would make the corpus a record of
this implementation's internals rather than of the product's promise.
"""

from __future__ import annotations

import pytest
from hostile_corpus import FeedbackCase, feedbacks

from narrativetrace_tooling.feedback import ALL_RULES, rules_refusing


def _accepted() -> tuple[FeedbackCase, ...]:
    return tuple(case for case in feedbacks() if not case.must_be_rejected)


def _rejected() -> tuple[FeedbackCase, ...]:
    return tuple(case for case in feedbacks() if case.must_be_rejected)


class TestTheAcceptedHalfStaysFilable:
    @pytest.mark.parametrize("case", _accepted(), ids=str)
    def test_no_rule_refuses_a_row_the_corpus_declares_filable(self, case: FeedbackCase) -> None:
        refusing = [rule.id for rule in rules_refusing(case.value)]

        assert refusing == [], f"{case.id} ({case.description}) must be filable"

    def test_the_accepted_half_is_not_empty(self) -> None:
        """Without this, every assertion above would be vacuously true the moment the reader
        stopped resolving ``expect`` — the same "loaded, not exercised" hole the corpus's own
        self-check module was written about."""
        assert len(_accepted()) > 20


class TestTheRejectedHalfIsRefusedByTheRuleItNames:
    @pytest.mark.parametrize("case", _rejected(), ids=str)
    def test_the_named_rule_is_among_the_rules_that_refuse_the_row(
        self, case: FeedbackCase
    ) -> None:
        refusing = [rule.id for rule in rules_refusing(case.value)]

        assert case.rule in refusing, (
            f"{case.id} ({case.description}) must be refused by {case.rule}, "
            f"and was refused by {refusing or 'nothing'}"
        )

    @pytest.mark.parametrize("case", _rejected(), ids=str)
    def test_the_rule_a_row_names_is_a_rule_that_exists(self, case: FeedbackCase) -> None:
        """A row naming ``vf.typo`` would otherwise fail as "not refused by vf.typo", which reads
        as a hole in the gate rather than as a hole in the row."""
        assert case.rule in {rule.id for rule in ALL_RULES}

    def test_every_rule_carries_at_least_one_row(self) -> None:
        """A rule nobody replays is a rule nobody has tested — and ten rules with nine rows
        between them is what a port ends up with when it stops at the obvious ones."""
        replayed = {case.rule for case in _rejected()}

        assert {rule.id for rule in ALL_RULES} == replayed


class TestTheThreeRowsThatDocumentADecidedLimit:
    """Three rows pin a decision rather than a capability, and each says so in its own
    description. Asserted here by NAME so that flipping one is a decision somebody has to make on
    purpose, with this test in front of them, rather than a green build after a tidy-up."""

    def _row(self, case_id: str) -> FeedbackCase:
        return next(case for case in feedbacks() if case.id == case_id)

    def test_the_hex_half_of_the_entropy_rule_is_carried_by_length(self) -> None:
        """Sixteen symbols cap Shannon entropy at 4.0 bits per character, so the ceiling can never
        fire on hex. Deleting the length clause to match the design's literal text reopens the
        hole this row exists for."""
        row = self._row("entropy-hex-run-32")

        assert row.must_be_rejected
        assert "vf.entropy" in [rule.id for rule in rules_refusing(row.value)]

    def test_an_unqualified_call_fragment_stays_filable(self) -> None:
        """``vf.rendered-call`` requires ``Type.method(param: value)``, which is what the rendered
        artifact always writes. Widening it would cover a hand-typed fragment and flip this row."""
        row = self._row("accepted-unqualified-rendered-call")

        assert not row.must_be_rejected
        assert rules_refusing(row.value) == ()

    def test_a_hyphenated_phrase_past_the_run_length_stays_filable(self) -> None:
        """It measures 4.33 bits per character, so admitting the hyphen to the encoded-run alphabet
        would refuse it. The alphabet excludes the hyphen for exactly this row."""
        row = self._row("accepted-hyphenated-prose")

        assert not row.must_be_rejected
        assert rules_refusing(row.value) == ()


class TestTheReplayReallyReadsTheCorpusFile:
    """The declared input of this module is one file —
    ``tests/resources/hostile-corpus/feedback.json`` — and this is the PROBE of that declaration
    (cross-port item 8). pytest has no up-to-date check to go stale, so the port's own shape of
    the same hole is a replay that would pass whatever the file said. Perturbing one row's text in
    memory must flip that row's verdict; if it does not, the replay is reading something else.
    """

    def test_perturbing_an_accepted_rows_text_flips_its_verdict(self) -> None:
        row = next(case for case in _accepted() if case.id == "accepted-doctor-finding-id")

        assert rules_refusing(row.value) == ()
        assert rules_refusing(row.value + ": ghp_0123456789abcdefghij") != ()

    def test_perturbing_a_rejected_rows_text_flips_its_verdict(self) -> None:
        row = next(case for case in _rejected() if case.id == "email-in-free-text")

        assert "vf.email" in [rule.id for rule in rules_refusing(row.value)]
        assert rules_refusing(row.value.replace("ada@example.com", "somebody")) == ()
