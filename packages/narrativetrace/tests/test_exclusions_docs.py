# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Both exclusion lists are published verbatim from code: the configuration guide carries a table
per list, and these tests render the tables from the code's own constants and require them to
appear in the guide word for word -- so the lists are never typed twice and never drift."""

from __future__ import annotations

from pathlib import Path

import pytest

from narrativetrace._generated import GENERATED_MEMBERS
from narrativetrace.exclusions import DEFAULT_EXCLUDE, EXCLUDE_REASONS


def _find_repo_root() -> Path:
    """Walks up to the directory holding both the root ``pyproject.toml`` and ``packages/``
    instead of counting parents: under ``mutmut`` this suite re-runs from a copied tree one level
    deeper (``packages/narrativetrace/mutants/tests/``), where a fixed ``parents[3]`` lands on
    ``packages/`` and the guide is not found (nightly 2026-10-22, B-153)."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "packages").is_dir():
            return candidate
    raise RuntimeError(f"no workspace root (pyproject.toml + packages/) above {__file__}")


_DOCS = _find_repo_root() / "documentation"
_GUIDE = _DOCS / "guides/configuration.md"


def _table(header: tuple[str, str], rows: list[tuple[str, str]]) -> str:
    lines = [f"| {header[0]} | {header[1]} |", "|---|---|"]
    lines += [f"| `{first}` | {second} |" for first, second in rows]
    return "\n".join(lines)


def test_the_default_list_and_its_reasons_cover_the_same_prefixes_in_the_same_order() -> None:
    assert tuple(EXCLUDE_REASONS) == DEFAULT_EXCLUDE


def test_the_guide_publishes_list_two_verbatim() -> None:
    table = _table(("Module prefix", "Why it is excluded"), list(EXCLUDE_REASONS.items()))
    assert table in _GUIDE.read_text(encoding="utf-8")


def test_the_guide_publishes_list_one_verbatim() -> None:
    table = _table(("Never traced", "Structural property"), list(GENERATED_MEMBERS))
    assert table in _GUIDE.read_text(encoding="utf-8")


def test_list_one_has_no_vendor_module_names() -> None:
    assert not [m for m, _ in GENERATED_MEMBERS if m.split(".")[0] in DEFAULT_EXCLUDE]


@pytest.mark.parametrize(
    "page", ["guides/configuration.md", "choosing-an-integration.md", "llms.txt", "llms-full.md"]
)
def test_every_page_that_describes_attachment_names_the_exclude_key(page: str) -> None:
    text = (_DOCS / page).read_text(encoding="utf-8")
    assert "NARRATIVETRACE_EXCLUDE" in text


def test_the_install_skill_names_the_exclude_key() -> None:
    skill = _DOCS.parent / "packages/narrativetrace/src/narrativetrace/_skills/agents"
    text = (skill / "add-narrative-tracing/SKILL.md").read_text(encoding="utf-8")
    assert "NARRATIVETRACE_EXCLUDE" in text
