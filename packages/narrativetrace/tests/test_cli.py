# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the ``narrativetrace-approve`` console entry point (:mod:`narrativetrace.cli`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from narrativetrace.cli import main


class TestApproveCli:
    def test_no_received_traces_prints_a_plain_message_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = main(["--approved-dir", str(tmp_path)])
        assert exit_code == 0
        assert "No received traces to approve." in capsys.readouterr().out

    def test_promotes_received_traces_and_reports_each_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        class_dir = tmp_path / "T"
        class_dir.mkdir()
        (class_dir / "m.received.nt").write_text("scenario: s\n\n- A.b()\n", encoding="utf-8")

        exit_code = main(["--approved-dir", str(tmp_path)])

        assert exit_code == 0
        assert (class_dir / "m.approved.nt").is_file()
        assert not (class_dir / "m.received.nt").exists()
        assert "Approved:" in capsys.readouterr().out

    def test_defaults_to_the_configured_approved_dir_when_no_flag_is_given(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.chdir(tmp_path)
        exit_code = main([])
        assert exit_code == 0
        assert "No received traces to approve." in capsys.readouterr().out
