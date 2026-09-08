# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins the AST scanner and the CLI gate (formats, output files, exit codes)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from narrativetrace_clarity.cli import _build_parser, main
from narrativetrace_clarity.scanner import scan_paths, scan_source
from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary

_SAMPLE = """
class OrderService:
    def place_order(self, customer_id, order_id):
        ...
    def _private(self):
        ...
    def __init__(self):
        ...


class Mgr:
    def do(self, x):
        ...
"""


class TestScanner:
    def test_scans_classes_and_public_methods(self) -> None:
        results = scan_source(_SAMPLE)
        assert set(results) == {"OrderService", "Mgr"}

    def test_private_and_dunder_methods_skipped(self) -> None:
        # OrderService has one public method (place_order); _private/__init__ are skipped.
        results = scan_source("class C:\n    def _hidden(self):\n        ...\n")
        # No public methods → the class produces no nodes → no result.
        assert results == {}

    def test_self_excluded_from_parameters(self) -> None:
        results = scan_source(_SAMPLE)
        # place_order params are customer_id/order_id (self dropped) → good param score.
        assert results["OrderService"].parameter_name_score > 0.8

    def test_generic_class_scores_low(self) -> None:
        results = scan_source(_SAMPLE)
        assert results["Mgr"].overall_score < results["OrderService"].overall_score

    def test_unparseable_file_is_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "broken.py").write_text("def (:\n")
        (tmp_path / "ok.py").write_text(
            "class OrderService:\n    def place_order(self):\n        ...\n"
        )
        results = scan_paths([tmp_path])
        assert "OrderService" in results


class TestCli:
    def test_unknown_format_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = tmp_path / "m.py"
        src.write_text(_SAMPLE)
        assert main([str(src), "--format", "xml"]) == 2
        assert "Unknown format" in capsys.readouterr().err

    def test_writes_both_outputs(self, tmp_path: Path) -> None:
        src = tmp_path / "m.py"
        src.write_text(_SAMPLE)
        out = tmp_path / "out"
        assert main([str(src), "--output-dir", str(out)]) == 0
        report = (out / "clarity-report.md").read_text()
        data = json.loads((out / "clarity-results.json").read_text())
        assert report.startswith("# Clarity Suite Report")
        assert data["version"] == "1.0"
        assert {s["name"] for s in data["scenarios"]} == {"OrderService", "Mgr"}

    def test_json_only_format(self, tmp_path: Path) -> None:
        src = tmp_path / "m.py"
        src.write_text(_SAMPLE)
        out = tmp_path / "out"
        assert main([str(src), "--format", "json", "--output-dir", str(out)]) == 0
        assert (out / "clarity-results.json").exists()
        assert not (out / "clarity-report.md").exists()

    def test_no_classes_found_exits_0(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = tmp_path / "empty.py"
        src.write_text("x = 1\n")
        assert main([str(src)]) == 0
        assert "No classes found" in capsys.readouterr().out

    def test_min_score_gate_fails(self, tmp_path: Path) -> None:
        src = tmp_path / "m.py"
        src.write_text("class Mgr:\n    def do(self, x):\n        ...\n")
        assert main([str(src), "--output-dir", str(tmp_path / "o"), "--min-score", "0.9"]) == 1

    def test_min_score_gate_passes_with_warn_only(self, tmp_path: Path) -> None:
        src = tmp_path / "m.py"
        src.write_text("class Mgr:\n    def do(self, x):\n        ...\n")
        exit_code = main(
            [str(src), "--output-dir", str(tmp_path / "o"), "--min-score", "0.9", "--warn-only"]
        )
        assert exit_code == 0

    def test_max_high_issues_gate(self, tmp_path: Path) -> None:
        src = tmp_path / "m.py"
        src.write_text("class Mgr:\n    def do(self, x):\n        ...\n")
        # "Mgr.do" with param "x" produces HIGH issues; allowing 0 → fail.
        assert main([str(src), "--output-dir", str(tmp_path / "o"), "--max-high-issues", "0"]) == 1

    def test_without_a_vocabulary_reader_glossary_dir_is_accepted_but_ignored(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "m.py"
        src.write_text(_SAMPLE)
        exit_code = main(
            [str(src), "--output-dir", str(tmp_path / "o"), "--glossary-dir", str(tmp_path)]
        )
        assert exit_code == 0

    def test_a_vocabulary_reader_receives_the_resolved_glossary_dir(self, tmp_path: Path) -> None:
        src = tmp_path / "m.py"
        src.write_text(_SAMPLE)
        seen: list[str] = []

        def reader(glossary_dir: str) -> DomainVocabulary:
            seen.append(glossary_dir)
            return EMPTY

        exit_code = main(
            [str(src), "--output-dir", str(tmp_path / "o"), "--glossary-dir", "/some/dir"],
            vocabulary_reader=reader,
        )

        assert exit_code == 0
        assert seen == ["/some/dir"]

    def test_a_failing_vocabulary_reader_degrades_to_the_built_in_dictionaries(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = tmp_path / "m.py"
        src.write_text(_SAMPLE)

        def reader(glossary_dir: str) -> DomainVocabulary:
            raise ValueError("malformed glossary")

        exit_code = main([str(src), "--output-dir", str(tmp_path / "o")], vocabulary_reader=reader)

        assert exit_code == 0
        assert "could not be read" in capsys.readouterr().err

    def test_default_glossary_dir_is_the_current_directory(self) -> None:
        args = _build_parser().parse_args(["x.py"])
        assert args.glossary_dir == "."
