# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""NOTICE's sibling half of Q2's gate (Phase 4 design, "the skill pages, the marketplace file and
the skills package are Apache"): the rendered agent-skill pages and the marketplace file ship
under Apache while the repository root's own LICENSE is BUSL, so NOTICE -- the file a reader
consults to learn which licence covers what -- has to name them. Derived from
`scripts.skills_render`'s own path helpers rather than from three string literals: a renamed
render target must fail here, not go quietly unlicensed.
"""

from __future__ import annotations

from narrativetrace_skills import SKILLS
from scripts.skills_render import (
    _claude_skill_md_path,
    _codex_skill_md_path,
    _marketplace_json_path,
)
from scripts.translation_check import REPO_ROOT

NOTICE_TEXT = (REPO_ROOT / "NOTICE").read_text(encoding="utf-8")


class TestNoticeNamesEveryRenderTarget:
    def test_names_the_claude_flavour_page_root(self) -> None:
        first_skill = SKILLS[0].canonical_name
        claude_root = _claude_skill_md_path(first_skill).parent.parent
        assert str(claude_root.relative_to(REPO_ROOT)) in NOTICE_TEXT

    def test_names_the_open_standard_page_root(self) -> None:
        first_skill = SKILLS[0].canonical_name
        agents_root = _codex_skill_md_path(first_skill).parent.parent
        assert str(agents_root.relative_to(REPO_ROOT)) in NOTICE_TEXT

    def test_names_the_marketplace_file(self) -> None:
        marketplace = _marketplace_json_path()
        assert str(marketplace.relative_to(REPO_ROOT)) in NOTICE_TEXT
