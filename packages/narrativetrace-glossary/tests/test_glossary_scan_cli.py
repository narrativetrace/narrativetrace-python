# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``glossary-scan`` CLI: static harvest, merge, write back, report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from narrativetrace_glossary.glossary_scan_cli import _build_parser, main
from narrativetrace_glossary.suite_harvest import GLOSSARY_JSON_FILE, GLOSSARY_MARKDOWN_FILE
from narrativetrace_glossary.usage_report import USAGE_REPORT_FILE

_SOURCE = """
class OverdraftService:
    def open_account(self, customer_id):
        return None
"""


def test_first_run_creates_the_glossary_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "overdraft_service.py").write_text(_SOURCE, encoding="utf-8")
    glossary_dir = tmp_path / "repo"
    glossary_dir.mkdir()

    exit_code = main(
        [
            str(src),
            "--glossary-dir",
            str(glossary_dir),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    assert exit_code == 0
    assert (glossary_dir / GLOSSARY_JSON_FILE).is_file()
    assert (glossary_dir / GLOSSARY_MARKDOWN_FILE).is_file()
    assert (tmp_path / "out" / USAGE_REPORT_FILE).is_file()
    out = capsys.readouterr().out
    assert "new terms harvested" in out
    assert "Glossary:" in out
    assert "Usage report:" in out


def test_a_second_scan_is_a_no_op_merge(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "overdraft_service.py").write_text(_SOURCE, encoding="utf-8")
    glossary_dir = tmp_path / "repo"
    glossary_dir.mkdir()
    args = [str(src), "--glossary-dir", str(glossary_dir), "--output-dir", str(tmp_path / "out")]
    main(args)
    capsys.readouterr()

    exit_code = main(args)

    assert exit_code == 0
    assert "0 new terms harvested" in capsys.readouterr().out


def test_default_glossary_and_output_dirs() -> None:
    parsed = _build_parser().parse_args(["x.py"])

    assert parsed.glossary_dir == "."
    assert parsed.output_dir == "build/narrativetrace"


def test_usage_report_is_valid_json(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "overdraft_service.py").write_text(_SOURCE, encoding="utf-8")
    glossary_dir = tmp_path / "repo"
    glossary_dir.mkdir()

    main([str(src), "--glossary-dir", str(glossary_dir), "--output-dir", str(tmp_path / "out")])

    document = json.loads((tmp_path / "out" / USAGE_REPORT_FILE).read_text(encoding="utf-8"))
    assert document["newTerms"]
