# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import pytest
import run
from model_ids import MODEL_ALIASES, is_full_id, resolve_model


class TestResolveModel:
    @pytest.mark.parametrize(
        ("alias", "full_id"),
        [
            ("haiku", "claude-haiku-5-5"),
            ("sonnet", "claude-sonnet-5-5"),
            ("opus", "claude-opus-5-5"),
        ],
    )
    def test_an_alias_becomes_its_full_id(self, alias: str, full_id: str) -> None:
        assert resolve_model(alias) == full_id

    @pytest.mark.parametrize("full_id", ["claude-haiku-5-5", "gemini-3.8-flash-low", "auto"])
    def test_a_full_id_passes_through_unchanged(self, full_id: str) -> None:
        assert resolve_model(full_id) == full_id

    @pytest.mark.parametrize("unknown", ["fast", "unknown", "", "Haiku", "claude-haiku"])
    def test_an_unknown_alias_is_refused_naming_the_accepted_ids(self, unknown: str) -> None:
        with pytest.raises(
            ValueError, match=r"claude-haiku-5-5.*claude-sonnet-5-5.*claude-opus-5-5"
        ):
            resolve_model(unknown)

    def test_the_table_maps_only_to_full_ids(self) -> None:
        assert all(is_full_id(full_id) for full_id in MODEL_ALIASES.values())


class TestTheRunnerRecordsTheId:
    def test_model_haiku_is_parsed_as_the_full_id(self) -> None:
        args = run._parse_args(
            ["--skill", "s", "--case", "c", "--platform", "claude", "--model", "haiku"]
        )

        assert args.model == "claude-haiku-5-5"

    def test_an_unknown_alias_is_refused_before_anything_runs(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            run._parse_args(
                ["--skill", "s", "--case", "c", "--platform", "claude", "--model", "fast"]
            )

        assert "claude-haiku-5-5" in capsys.readouterr().err
