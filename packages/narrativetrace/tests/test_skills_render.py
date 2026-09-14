# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/skills_render.py`: `.claude/skills/{narrativetrace-doctor,add-narrative-tracing}/
SKILL.md`, `.agents/skills/{narrativetrace-doctor,add-narrative-tracing}/SKILL.md` and this
repository's own `AGENTS.md` managed section are BUILD OUTPUT of the typed `narrativetrace_skills`
catalogue — this drift check is what `poe check`'s own `skills-check` task runs, exercised here
too so a plain `uv run poe coverage` run also measures and gates it (`scripts/skills_render.py`
itself is a CLI entry point, not imported by anything else that would otherwise cover it)."""

from __future__ import annotations

from scripts.skills_render import _check_all, _fix_all, _rendered_agents_md, _rendered_skill_files


class TestRenderedArtifactsMatchTheTypedCatalogue:
    def test_no_drift_against_the_committed_files(self) -> None:
        """Fails naming the drifted path(s) — run `python scripts/skills_render.py --fix`."""
        assert _check_all() == []

    def test_rendered_skill_files_cover_both_shipped_skills(self) -> None:
        paths = {path.name for path in _rendered_skill_files()}
        assert paths == {"SKILL.md"}

    def test_rendered_skill_files_cover_both_platforms_for_both_skills(self) -> None:
        # Two shipped skills, two platforms (Claude Code + Codex) rendering the same body under
        # different frontmatter -- four files, not two.
        rendered = _rendered_skill_files()
        assert len(rendered) == 4
        assert sum(1 for path in rendered if ".claude" in path.parts) == 2
        assert sum(1 for path in rendered if ".agents" in path.parts) == 2

    def test_rendered_agents_md_carries_the_markers(self) -> None:
        rendered = _rendered_agents_md()
        assert "<!-- narrativetrace:skills:start -->" in rendered
        assert "<!-- narrativetrace:skills:end -->" in rendered

    def test_fix_is_a_no_op_once_already_in_sync(self) -> None:
        """`--fix` re-running after a clean `--check` writes byte-identical content -- it must
        never introduce drift of its own."""
        before = {path: path.read_text(encoding="utf-8") for path in _rendered_skill_files()}
        _fix_all()
        after = {path: path.read_text(encoding="utf-8") for path in _rendered_skill_files()}
        assert before == after
