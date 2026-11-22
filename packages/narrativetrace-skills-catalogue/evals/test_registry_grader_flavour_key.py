# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``grade_the_registry.sh`` tells the Claude flavour's page from the open-standard page by one
frontmatter line. The Claude pages carry no ``allowed-tools`` line, so the line it keys on is
``when_to_use``, which every skill's Claude page carries and no open-standard page does."""

from __future__ import annotations

from pathlib import Path

_GRADER = Path(__file__).resolve().parent / "add-narrative-tracing" / "grade_the_registry.sh"


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


_ROOT = _repo_root()


def test_the_grader_no_longer_keys_on_an_allowed_tools_line() -> None:
    code = [
        line
        for line in _GRADER.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    assert not [line for line in code if "allowed-tools" in line]
    assert [line for line in code if "^when_to_use:" in line]


def test_every_claude_page_carries_when_to_use_and_no_open_standard_page_does() -> None:
    for page in (_ROOT / ".claude" / "skills").glob("*/SKILL.md"):
        assert "\nwhen_to_use:" in page.read_text(encoding="utf-8"), page
    for page in (_ROOT / ".agents" / "skills").glob("*/SKILL.md"):
        assert "\nwhen_to_use:" not in page.read_text(encoding="utf-8"), page
