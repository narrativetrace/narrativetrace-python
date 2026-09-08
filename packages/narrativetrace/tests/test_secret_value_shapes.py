# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for structural secret-value-shape detection (adversarial-audit mirror, F3)."""

from __future__ import annotations

import pytest

from narrativetrace.secret_value_shapes import (
    is_jwt_like,
    is_pan_like,
    is_secret_shaped,
    is_set_cookie_like,
)

_REAL_JWT = (
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
)
_VISA_TEST_PAN = "4111111111111111"
_VISA_TEST_PAN_FAILS_LUHN = "4111111111111112"


class TestJwtShape:
    def test_a_real_looking_jwt_is_detected(self) -> None:
        assert is_jwt_like(_REAL_JWT)

    def test_three_dotted_segments_without_the_eyj_header_are_not_a_jwt(self) -> None:
        assert not is_jwt_like("a.b.c")

    def test_a_dotted_hostname_is_not_a_jwt(self) -> None:
        assert not is_jwt_like("www.example.com")

    def test_two_segments_are_not_a_jwt(self) -> None:
        assert not is_jwt_like("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0")

    def test_an_empty_segment_is_not_a_jwt(self) -> None:
        assert not is_jwt_like("eyJhbGciOiJIUzI1NiJ9..dozjgNryP4J3jVmNHl0w5N")

    def test_a_non_base64url_character_disqualifies_a_segment(self) -> None:
        assert not is_jwt_like("eyJhbGciOiJIUzI1NiJ9.not valid!.dozjgNryP4J3jVmNHl0w5N")


class TestPanShape:
    def test_a_luhn_valid_test_pan_is_detected(self) -> None:
        assert is_pan_like(_VISA_TEST_PAN)

    def test_separators_are_allowed(self) -> None:
        assert is_pan_like("4111 1111 1111 1111")
        assert is_pan_like("4111-1111-1111-1111")

    def test_a_luhn_invalid_number_of_the_same_length_stays_visible(self) -> None:
        assert not is_pan_like(_VISA_TEST_PAN_FAILS_LUHN)

    def test_too_short_a_digit_run_is_not_a_pan(self) -> None:
        assert not is_pan_like("4111111111")

    def test_too_long_a_digit_run_is_not_a_pan(self) -> None:
        assert not is_pan_like("41111111111111111111")

    def test_a_leading_or_trailing_separator_is_not_a_pan(self) -> None:
        assert not is_pan_like("-4111111111111111")
        assert not is_pan_like("4111111111111111-")

    def test_a_non_digit_non_separator_character_is_not_a_pan(self) -> None:
        assert not is_pan_like("4111-1111-1111-111a")

    def test_an_ordinary_order_number_stays_visible(self) -> None:
        assert not is_pan_like("ORD-2026-000123")


class TestSetCookieShape:
    def test_a_set_cookie_header_with_path_is_detected(self) -> None:
        assert is_set_cookie_like("sessionid=abc123; Path=/; HttpOnly")

    def test_a_set_cookie_header_with_secure_and_samesite_is_detected(self) -> None:
        assert is_set_cookie_like("token=xyz; Secure; SameSite=Strict")

    def test_a_plain_key_value_pair_stays_visible(self) -> None:
        assert not is_set_cookie_like("name=value")

    def test_semicolon_joined_ordinary_pairs_stay_visible(self) -> None:
        assert not is_set_cookie_like("name=Ada; age=36")

    def test_a_pair_with_no_value_is_not_a_cookie(self) -> None:
        assert not is_set_cookie_like("name=; Path=/")

    def test_a_pair_with_no_name_is_not_a_cookie(self) -> None:
        assert not is_set_cookie_like("=value; Path=/")


class TestIsSecretShaped:
    @pytest.mark.parametrize(
        "value",
        [_REAL_JWT, _VISA_TEST_PAN, "sessionid=abc123; Path=/; HttpOnly", "52998224725"],
    )
    def test_each_shape_is_covered(self, value: str) -> None:
        assert is_secret_shaped(value)

    @pytest.mark.parametrize("value", ["", "hello world", "ORD-2026-000123", "name=Ada; age=36"])
    def test_ordinary_values_are_not_secret_shaped(self, value: str) -> None:
        assert not is_secret_shaped(value)
