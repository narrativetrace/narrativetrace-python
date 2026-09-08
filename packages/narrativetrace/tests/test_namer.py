# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Cross-runtime determinism tests for TraceNamer (fixtures from the Java test suite)."""

from __future__ import annotations

import re

from narrativetrace.ids import TraceId
from narrativetrace.namer import _ADJECTIVES, _NOUNS, _VERBS, trace_name


class TestWordLists:
    def test_sizes_are_byte_identical_to_java(self) -> None:
        assert len(_ADJECTIVES) == 256
        assert len(_NOUNS) == 512
        assert len(_VERBS) == 256

    def test_all_words_are_three_to_six_chars(self) -> None:
        for words in (_ADJECTIVES, _NOUNS, _VERBS):
            assert all(3 <= len(w) <= 6 for w in words)


class TestCrossRuntimeDeterminism:
    def test_all_zeros_is_first_word_of_each_list(self) -> None:
        assert trace_name("0" * 32) == "red fox runs"

    def test_all_fs_is_last_word_of_each_list(self) -> None:
        assert trace_name("f" * 32) == "nutty rig fans"

    def test_only_first_7_hex_chars_matter(self) -> None:
        assert trace_name("abcdef0000000000000000000000aaaa") == trace_name(
            "abcdef0000000000000000000000bbbb"
        )

    def test_different_prefixes_differ(self) -> None:
        a = trace_name("1234567000000000000000000000aaaa")
        b = trace_name("7654321000000000000000000000aaaa")
        assert a != b

    def test_deterministic(self) -> None:
        hex_value = "a3f7c1b290de4f8801234567deadbeef"
        assert trace_name(hex_value) == trace_name(hex_value)

    def test_shape_is_three_lowercase_words(self) -> None:
        assert re.fullmatch(r"[a-z]+ [a-z]+ [a-z]+", trace_name("5a8b3c2d1e0f9876543210abcdef0123"))


class TestTraceIdIntegration:
    def test_human_name_delegates_to_namer(self) -> None:
        tid = TraceId("0" * 32)
        assert tid.human_name() == "red fox runs"

    def test_names_are_well_distributed(self) -> None:
        names = {TraceId.generate().human_name() for _ in range(1000)}
        assert len(names) > 990  # ~33.5M combinations → 1000 samples nearly all distinct
