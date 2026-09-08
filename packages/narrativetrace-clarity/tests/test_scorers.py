# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins the five scorers to Java's exact golden numbers."""

from __future__ import annotations

import pytest
from narrativetrace_clarity import scorers


class TestMethodNameScorer:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("", 0.0),
            ("process", 0.10),  # GENERIC single
            ("calculate", 0.60),  # DOMAIN single
            ("customize", 0.55),  # UNKNOWN + -ize morphological verb
            ("widget", 0.50),  # UNKNOWN non-verb
            ("en", 0.50),  # verb suffix but too short
        ],
    )
    def test_exact(self, name: str, expected: float) -> None:
        assert scorers.score_method_name(name) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("calculateRefundAmountTotalAndSend", 0.88),
            ("customizeWidget", 0.79),
        ],
    )
    def test_multi_token(self, name: str, expected: float) -> None:
        assert scorers.score_method_name(name) == pytest.approx(expected, abs=0.02)


class TestClassNameScorer:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("", 0.0),
            ("Manager", 0.05),  # GENERIC role suffix single
            ("Service", 0.10),  # DESIGN_PATTERN single
            ("Validator", 0.10),  # FUNCTIONAL single
            ("Comparable", 0.85),  # ADJECTIVE morphology single
            ("Widget", 0.75),  # UNKNOWN noun single
        ],
    )
    def test_exact(self, name: str, expected: float) -> None:
        assert scorers.score_class_name(name) == pytest.approx(expected)

    def test_good_multi_token_is_high(self) -> None:
        assert scorers.score_class_name("OrderService") >= 0.85


class TestParameterNameScorer:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("", 0.0),
            ("fooBar", 0.15),  # meaningless token present
            ("statusCount", 0.865),  # both typed-generic, no domain
            ("customerRegion", 1.0),  # both domain
        ],
    )
    def test_exact(self, name: str, expected: float) -> None:
        assert scorers.score_parameter_name(name) == pytest.approx(expected, abs=0.02)

    def test_single_meaningless_is_zero(self) -> None:
        assert scorers.score_parameter_name("x") == 0.0

    def test_single_domain_token(self) -> None:
        assert scorers.score_parameter_name("customer") == pytest.approx(0.80)

    def test_single_abbreviation_penalized(self) -> None:
        # NOT_GENERIC single token that is an abbreviation → 0.40 (else 0.80)
        assert scorers.score_parameter_name("ctx") == pytest.approx(0.40)


class TestCohesionScorer:
    def test_unknown_suffix_returns_0_7(self) -> None:
        assert scorers.score_cohesion_class("Widget", ["doThing"]) == pytest.approx(0.7)

    def test_broad_role_without_expected_verbs_returns_0_9(self) -> None:
        # "service" is a design-pattern suffix with an EMPTY expected-verb list → broad 0.9.
        assert scorers.score_cohesion_class("OrderService", ["placeOrder"]) == pytest.approx(0.9)

    def test_aligned_methods_ratio(self) -> None:
        # repository expects find/save/... — 1 of 2 methods aligns.
        score = scorers.score_cohesion_class("UserRepository", ["findUser", "doStuff"])
        assert score == pytest.approx(0.5)

    def test_empty_trace_returns_0_7(self) -> None:
        assert scorers.score_cohesion_trace({}) == pytest.approx(0.7)
