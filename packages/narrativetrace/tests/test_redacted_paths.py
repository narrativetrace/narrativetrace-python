# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the template-path redaction walk (the template-resolution family)."""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.markers import not_traced_field
from narrativetrace.redacted_paths import redacts
from narrativetrace.redaction import RedactionPolicy


@dataclass
class Card:
    number: str
    cvv: str = not_traced_field(default="")


@dataclass
class Order:
    id: str
    card: Card | None


@dataclass
class Payment:
    __nt_not_traced__ = ("card",)

    id: str
    card: Card | None


@dataclass
class Badge:
    """``clearance`` is on no deny-list pattern — only the annotation can redact it."""

    id: str
    clearance: str = not_traced_field(default="")


class Login:
    """Nothing is annotated here; the name-based policy is the only rule that applies."""

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password


class TestRedacts:
    def test_a_redacted_leaf_redacts(self) -> None:
        assert redacts(Card("4111", "123"), "cvv", RedactionPolicy.DEFAULT)

    def test_the_annotation_redacts_a_property_no_deny_list_pattern_recognizes(self) -> None:
        assert redacts(Badge("b-1", "TOP-SECRET"), "clearance", RedactionPolicy.DEFAULT)

    def test_the_deny_list_redacts_an_unannotated_property_by_name_alone(self) -> None:
        assert redacts(Login("jsmith", "hunter2"), "password", RedactionPolicy.DEFAULT)

    def test_an_unredacted_leaf_does_not_redact(self) -> None:
        assert not redacts(Card("4111", "123"), "number", RedactionPolicy.DEFAULT)

    def test_a_redacted_segment_at_the_end_of_a_nested_path_redacts(self) -> None:
        order = Order("o-1", Card("4111", "123"))

        assert redacts(order, "card.cvv", RedactionPolicy.DEFAULT)

    def test_a_redacted_segment_in_the_middle_of_a_path_redacts_everything_below_it(self) -> None:
        payment = Payment("p-1", Card("4111", "123"))

        assert redacts(payment, "card.number", RedactionPolicy.DEFAULT)

    def test_an_unredacted_nested_path_does_not_redact(self) -> None:
        order = Order("o-1", Card("4111", "123"))

        assert not redacts(order, "card.number", RedactionPolicy.DEFAULT)

    def test_a_segment_naming_no_member_stops_the_walk_and_redacts_nothing(self) -> None:
        """A typo like `custmer.cvv` must survive literally and still raise the unresolved-
        placeholder warning — nothing can leak, since a path that names nothing resolves to
        nothing."""
        assert not redacts(Order("o-1", None), "password", RedactionPolicy.DEFAULT)

    def test_a_none_intermediate_value_stops_the_walk_and_redacts_nothing(self) -> None:
        assert not redacts(Order("o-1", None), "card.cvv", RedactionPolicy.DEFAULT)

    def test_none_root_redacts_nothing(self) -> None:
        assert not redacts(None, "cvv", RedactionPolicy.DEFAULT)

    def test_a_raising_accessor_stops_the_walk_and_redacts_nothing(self) -> None:
        class Broken:
            @property
            def card(self) -> Card:
                raise RuntimeError("no")

        assert not redacts(Broken(), "card.cvv", RedactionPolicy.DEFAULT)

    def test_a_zero_arg_method_is_invoked_to_continue_the_walk(self) -> None:
        class Wrapper:
            def card(self) -> Card:
                return Card("4111", "123")

        assert redacts(Wrapper(), "card.cvv", RedactionPolicy.DEFAULT)

    def test_a_disabled_policy_still_honours_the_annotation(self) -> None:
        assert redacts(Card("4111", "123"), "cvv", RedactionPolicy.DISABLED)

    def test_a_disabled_policy_does_not_redact_by_name_alone(self) -> None:
        assert not redacts(Login("jsmith", "hunter2"), "password", RedactionPolicy.DISABLED)


class TestEmptyPathSegment:
    """A security fuzz suite finding, redaction-walk side: Java's ``RedactedPaths.member`` calls
    ``findAccessor`` directly, bypassing the normal resolver's broad catch, so an empty path
    segment (a trailing/leading/doubled dot) raised there even after the resolver itself was
    already typo-tolerant. Verified this runtime has no equivalent gap: ``_resolve_segment``'s
    ``getattr(owner, "")`` fails through the existing ``except Exception`` like any other missing
    member, so every shape below already stops the walk and redacts nothing. Pins the behaviour,
    no production change."""

    def test_an_empty_segment_stops_the_walk_and_redacts_nothing(self) -> None:
        assert not redacts(Card("4111", "123"), "", RedactionPolicy.DEFAULT)

    def test_a_trailing_dot_after_a_real_segment_stops_the_walk_and_redacts_nothing(self) -> None:
        order = Order("o-1", Card("4111", "123"))
        assert not redacts(order, "card.", RedactionPolicy.DEFAULT)

    def test_a_doubled_dot_after_a_real_segment_stops_the_walk_and_redacts_nothing(self) -> None:
        order = Order("o-1", Card("4111", "123"))
        assert not redacts(order, "card..cvv", RedactionPolicy.DEFAULT)

    def test_a_path_that_is_only_a_separator_stops_the_walk_and_redacts_nothing(self) -> None:
        assert not redacts(Card("4111", "123"), ".", RedactionPolicy.DEFAULT)
