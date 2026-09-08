# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the layered configuration resolver."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from narrativetrace.config import ConfigResolver, DuplicateConfigurationError


def _pyproject(directory: Path, body: str) -> None:
    (directory / "pyproject.toml").write_text(body, encoding="utf-8")


def _standalone(directory: Path, body: str) -> None:
    (directory / "narrativetrace.toml").write_text(body, encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_ambient_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with no NARRATIVETRACE_* variables leaking in from the outer run."""
    for name in list(os.environ):
        if name.startswith("NARRATIVETRACE_"):
            monkeypatch.delenv(name, raising=False)


class TestPyprojectChannel:
    def test_reads_the_tool_table(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[tool.narrativetrace]\nlevel = "SUMMARY"\n')
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == "SUMMARY"

    def test_pyproject_without_the_table_is_not_a_config_source(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[project]\nname = "app"\n')
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == "DETAIL"

    def test_unrelated_tool_table_is_ignored(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, "[tool.ruff]\nline-length = 100\n")
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == "DETAIL"


class TestStandaloneChannel:
    def test_reads_the_document_root(self, tmp_path: Path) -> None:
        _standalone(tmp_path, 'level = "ERRORS"\n')
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == "ERRORS"

    def test_coexists_with_a_pyproject_that_declares_no_table(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[project]\nname = "app"\n')
        _standalone(tmp_path, 'level = "ERRORS"\n')
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == "ERRORS"


class TestDuplicateFailFast:
    def test_two_sources_in_one_directory_is_a_hard_error(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[tool.narrativetrace]\nlevel = "SUMMARY"\n')
        _standalone(tmp_path, 'level = "ERRORS"\n')
        with pytest.raises(DuplicateConfigurationError) as excinfo:
            ConfigResolver(tmp_path)
        assert "narrativetrace.toml" in str(excinfo.value)
        assert "pyproject.toml" in str(excinfo.value)

    def test_a_malformed_standalone_still_counts_as_a_declared_source(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[tool.narrativetrace]\nlevel = "SUMMARY"\n')
        _standalone(tmp_path, "this is not toml\n")
        with pytest.raises(DuplicateConfigurationError):
            ConfigResolver(tmp_path)

    def test_the_same_two_files_in_different_directories_are_not_a_duplicate(
        self, tmp_path: Path
    ) -> None:
        _pyproject(tmp_path, '[tool.narrativetrace]\nlevel = "SUMMARY"\n')
        child = tmp_path / "child"
        child.mkdir()
        _standalone(child, 'level = "ERRORS"\n')
        assert ConfigResolver(child).resolve("level", "DETAIL") == "ERRORS"


class TestUpwardWalk:
    def test_finds_configuration_in_an_ancestor(self, tmp_path: Path) -> None:
        _standalone(tmp_path, 'level = "ERRORS"\n')
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert ConfigResolver(nested).resolve("level", "DETAIL") == "ERRORS"

    def test_the_nearest_directory_wins(self, tmp_path: Path) -> None:
        _standalone(tmp_path, 'level = "ERRORS"\n')
        child = tmp_path / "child"
        child.mkdir()
        _standalone(child, 'level = "SUMMARY"\n')
        assert ConfigResolver(child).resolve("level", "DETAIL") == "SUMMARY"

    def test_a_declared_but_empty_file_stops_the_walk(self, tmp_path: Path) -> None:
        _standalone(tmp_path, 'level = "ERRORS"\n')
        child = tmp_path / "child"
        child.mkdir()
        _standalone(child, "")
        assert ConfigResolver(child).resolve("level", "DETAIL") == "DETAIL"

    def test_no_configuration_anywhere_yields_the_default(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert ConfigResolver(nested).resolve("level", "DETAIL") == "DETAIL"


class TestEnvironmentPrecedence:
    def test_environment_beats_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _standalone(tmp_path, 'level = "ERRORS"\n')
        monkeypatch.setenv("NARRATIVETRACE_LEVEL", "SUMMARY")
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == "SUMMARY"

    def test_multiword_key_maps_to_a_screaming_snake_variable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", "/from/env")
        assert ConfigResolver(tmp_path).resolve("output_dir", "traces") == "/from/env"

    def test_an_empty_environment_value_still_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _standalone(tmp_path, 'level = "ERRORS"\n')
        monkeypatch.setenv("NARRATIVETRACE_LEVEL", "")
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == ""


class TestValueCanonicalization:
    def test_booleans_render_as_properties_style_lowercase(self, tmp_path: Path) -> None:
        _standalone(tmp_path, "output = true\ngraph = false\n")
        resolver = ConfigResolver(tmp_path)
        assert resolver.resolve("output") == "true"
        assert resolver.resolve("graph") == "false"

    def test_numbers_render_as_text(self, tmp_path: Path) -> None:
        _standalone(tmp_path, "depth = 5\n")
        assert ConfigResolver(tmp_path).resolve("depth") == "5"


class TestDegradation:
    def test_a_malformed_standalone_file_degrades_to_defaults(self, tmp_path: Path) -> None:
        _standalone(tmp_path, "not = = toml\n")
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == "DETAIL"

    def test_a_malformed_pyproject_is_not_a_config_source(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, "not = = toml\n")
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == "DETAIL"

    def test_a_non_table_tool_entry_is_ignored(self, tmp_path: Path) -> None:
        _pyproject(tmp_path, '[tool]\nnarrativetrace = "yes"\n')
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == "DETAIL"

    def test_a_directory_named_like_the_config_file_is_not_read(self, tmp_path: Path) -> None:
        (tmp_path / "narrativetrace.toml").mkdir()
        assert ConfigResolver(tmp_path).resolve("level", "DETAIL") == "DETAIL"


class TestGuards:
    def test_an_empty_key_is_rejected(self, tmp_path: Path) -> None:
        # Anchored: an unanchored match is a substring search, so a mutant that pads the message
        # would still satisfy it.
        with pytest.raises(ValueError, match=r"\Akey must not be empty\Z"):
            ConfigResolver(tmp_path).resolve("")

    def test_a_missing_key_falls_through_to_the_default(self, tmp_path: Path) -> None:
        _standalone(tmp_path, 'level = "ERRORS"\n')
        assert ConfigResolver(tmp_path).resolve("format", "markdown") == "markdown"

    def test_a_missing_key_without_a_default_is_none(self, tmp_path: Path) -> None:
        assert ConfigResolver(tmp_path).resolve("format") is None

    def test_file_values_exposes_the_discovered_table(self, tmp_path: Path) -> None:
        _standalone(tmp_path, 'level = "ERRORS"\n')
        assert ConfigResolver(tmp_path).file_values == {"level": "ERRORS"}
