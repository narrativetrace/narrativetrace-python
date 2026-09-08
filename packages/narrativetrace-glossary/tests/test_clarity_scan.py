# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Glossary-aware clarity scan: vocabulary-check defaults (prerequisite 5)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from narrativetrace_glossary import write_glossary_json
from narrativetrace_glossary.clarity_scan import main
from narrativetrace_glossary.models import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    TermKind,
    TermStatus,
)

_SOURCE = """
class ClaveManager:
    def do(self, clave):
        ...
"""


def _write_glossary(glossary_dir: Path) -> None:
    glossary = Glossary(
        {"security": BoundedContext("security", ["acme"])},
        [
            GlossaryTerm(
                "clave",
                "security",
                TermKind.WORD,
                TermStatus.CURATED,
                first_seen=date(2026, 8, 11),
            )
        ],
    )
    (glossary_dir / "glossary.json").write_text(write_glossary_json(glossary), encoding="utf-8")


def test_scores_with_the_committed_glossarys_vocabulary(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text(_SOURCE, encoding="utf-8")
    _write_glossary(tmp_path)

    exit_code = main(
        [str(src), "--output-dir", str(tmp_path / "out"), "--glossary-dir", str(tmp_path)]
    )

    assert exit_code == 0


def test_degrades_silently_with_no_committed_glossary(tmp_path: Path) -> None:
    src = tmp_path / "m.py"
    src.write_text(_SOURCE, encoding="utf-8")

    exit_code = main(
        [str(src), "--output-dir", str(tmp_path / "out"), "--glossary-dir", str(tmp_path)]
    )

    assert exit_code == 0
