# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``scripts/publish_agents_md_section.py``: the publish-pipeline step that composes the public
snapshot's ``AGENTS.md`` from just its managed section, since ``.publishignore`` strips the whole
(private) file (see that module's own docstring for the what-to-commit.md gap this closes)."""

from __future__ import annotations

from pathlib import Path

import pytest
from narrativetrace_skills import render_agents_md_snippet
from narrativetrace_skills.catalogue_index import PRO_LISTINGS, SKILLS
from scripts.publish_agents_md_section import compose_public_agents_md


class TestComposePublicAgentsMd:
    def test_writes_only_the_managed_section(self, tmp_path: Path) -> None:
        section = render_agents_md_snippet(SKILLS, PRO_LISTINGS)
        source = tmp_path / "AGENTS.md"
        source.write_text(
            f"# Private briefing\n\nInternal-only prose.\n\n{section}\n\nMore internal prose.\n",
            encoding="utf-8",
        )
        stage = tmp_path / "stage"
        stage.mkdir()

        compose_public_agents_md(source, stage)

        written = (stage / "AGENTS.md").read_text(encoding="utf-8")
        assert written == f"{section}\n"
        assert "Private briefing" not in written
        assert "Internal-only prose" not in written
        assert "More internal prose" not in written

    def test_matches_this_repository_own_committed_agents_md(self, tmp_path: Path) -> None:
        """The real regression: run against THIS repo's own ``AGENTS.md``, the way the publish
        pipeline does, and prove the result is exactly what ``skills_render.py``'s own drift
        check expects a staged (section-only) ``AGENTS.md`` to read as."""
        repo_root = Path(__file__).resolve()
        while not (repo_root / "AGENTS.md").is_file():
            repo_root = repo_root.parent
        stage = tmp_path / "stage"
        stage.mkdir()

        compose_public_agents_md(repo_root / "AGENTS.md", stage)

        expected_section = render_agents_md_snippet(SKILLS, PRO_LISTINGS)
        assert (stage / "AGENTS.md").read_text(encoding="utf-8") == f"{expected_section}\n"

    def test_raises_naming_the_file_when_no_section_is_present(self, tmp_path: Path) -> None:
        source = tmp_path / "AGENTS.md"
        source.write_text("no markers here\n", encoding="utf-8")
        stage = tmp_path / "stage"
        stage.mkdir()

        with pytest.raises(ValueError, match=r"AGENTS\.md"):
            compose_public_agents_md(source, stage)
