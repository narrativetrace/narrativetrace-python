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

from pathlib import Path

from scripts.skills_render import _check_all, _fix_all, _rendered_agents_md, _rendered_skill_files
from scripts.translation_check import REPO_ROOT


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

    def test_fix_is_a_no_op_once_already_in_sync(self, tmp_path: Path) -> None:
        """`--fix` re-running after a clean `--check` writes byte-identical content -- it must
        never introduce drift of its own.

        Proven in a `tmp_path` tree seeded with what the catalogue renders, never by writing the
        real one: this test also runs inside the mutmut sandbox, where the mutated catalogue
        renderer would write a mutant's output over tracked `SKILL.md`/`AGENTS.md` files
        (2026-09-17 nightly finding F2's second writer)."""
        for path, content in _rendered_skill_files(tmp_path).items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text(_rendered_agents_md(tmp_path), encoding="utf-8")
        assert _check_all(tmp_path) == []
        before = {
            path: path.read_text(encoding="utf-8") for path in _rendered_skill_files(tmp_path)
        }
        _fix_all(tmp_path)
        after = {path: path.read_text(encoding="utf-8") for path in _rendered_skill_files(tmp_path)}
        assert before == after

    def test_fix_writes_only_under_the_root_it_is_given(self, tmp_path: Path) -> None:
        """The cause behind the finding: `--fix` writes into a root the caller names, so a test
        can exercise it without touching this repository's own tracked files."""
        before = {path: path.read_bytes() for path in _rendered_skill_files()}
        before[REPO_ROOT / "AGENTS.md"] = (REPO_ROOT / "AGENTS.md").read_bytes()
        written = _fix_all(tmp_path)
        assert written
        assert all(tmp_path in path.parents for path in written)
        assert {path: path.read_bytes() for path in before} == before
