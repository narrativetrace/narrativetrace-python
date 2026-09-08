# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for TracingLevel parsing/ordering and NarrativeTraceConfig."""

from pathlib import Path

import pytest

from narrativetrace.config import ConfigResolver
from narrativetrace.levels import NarrativeTraceConfig, TracingLevel


class TestOrdering:
    def test_levels_are_ordered_by_verbosity(self) -> None:
        order = [
            TracingLevel.OFF,
            TracingLevel.ERRORS,
            TracingLevel.SUMMARY,
            TracingLevel.NARRATIVE,
            TracingLevel.DETAIL,
        ]
        assert [level_value.rank for level_value in order] == [0, 1, 2, 3, 4]

    def test_is_enabled_is_ordinal_comparison(self) -> None:
        assert TracingLevel.DETAIL.is_enabled(TracingLevel.ERRORS)
        assert TracingLevel.ERRORS.is_enabled(TracingLevel.ERRORS)
        assert not TracingLevel.ERRORS.is_enabled(TracingLevel.DETAIL)
        assert not TracingLevel.OFF.is_enabled(TracingLevel.ERRORS)


class TestFromName:
    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("detail", TracingLevel.DETAIL),
            ("DETAIL", TracingLevel.DETAIL),
            ("  Summary  ", TracingLevel.SUMMARY),
            ("errors", TracingLevel.ERRORS),
        ],
    )
    def test_parses_case_and_whitespace_insensitively(
        self, name: str, expected: TracingLevel
    ) -> None:
        assert TracingLevel.from_name(name, TracingLevel.OFF) is expected

    @pytest.mark.parametrize("garbage", [None, "", "   ", "nonsense", "verbose"])
    def test_degrades_garbage_to_fallback_without_raising(self, garbage: str | None) -> None:
        assert TracingLevel.from_name(garbage, TracingLevel.NARRATIVE) is TracingLevel.NARRATIVE


class TestConfig:
    def test_default_level_is_detail(self) -> None:
        assert NarrativeTraceConfig().level is TracingLevel.DETAIL

    def test_level_is_mutable_at_runtime(self) -> None:
        config = NarrativeTraceConfig(TracingLevel.OFF)
        config.level = TracingLevel.SUMMARY
        assert config.level is TracingLevel.SUMMARY

    def test_resolve_reads_the_environment_channel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NARRATIVETRACE_LEVEL", "summary")
        assert NarrativeTraceConfig.resolve().level is TracingLevel.SUMMARY

    def test_resolve_falls_back_to_detail_on_garbage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NARRATIVETRACE_LEVEL", "bogus")
        assert NarrativeTraceConfig.resolve().level is TracingLevel.DETAIL

    def test_resolve_uses_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NARRATIVETRACE_LEVEL", raising=False)
        assert NarrativeTraceConfig.resolve().level is TracingLevel.DETAIL

    def test_resolve_reads_the_file_channel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NARRATIVETRACE_LEVEL", raising=False)
        (tmp_path / "narrativetrace.toml").write_text('level = "ERRORS"\n', encoding="utf-8")
        config = NarrativeTraceConfig.resolve(resolver=ConfigResolver(tmp_path))
        assert config.level is TracingLevel.ERRORS

    def test_resolve_lets_the_environment_beat_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "narrativetrace.toml").write_text('level = "ERRORS"\n', encoding="utf-8")
        monkeypatch.setenv("NARRATIVETRACE_LEVEL", "SUMMARY")
        config = NarrativeTraceConfig.resolve(resolver=ConfigResolver(tmp_path))
        assert config.level is TracingLevel.SUMMARY
