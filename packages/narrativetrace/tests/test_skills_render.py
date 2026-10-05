# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/skills_render.py`: `.claude/skills/{narrativetrace-doctor,add-narrative-tracing}/
SKILL.md`, `.agents/skills/{narrativetrace-doctor,add-narrative-tracing}/SKILL.md`, this
repository's own `AGENTS.md` managed section, the published `narrativetrace-skills` distribution's
`skills/**` payload and its byte-identical copy bundled as `narrativetrace`'s own package data
(`narrativetrace/_skills/**`) are BUILD OUTPUT of the typed `narrativetrace_skills` catalogue —
this drift check is what `poe check`'s own `skills-check` task runs, exercised here too so a plain
`uv run poe coverage` run also measures and gates it (`scripts/skills_render.py` itself is a CLI
entry point, not imported by anything else that would otherwise cover it)."""

from __future__ import annotations

from pathlib import Path

from scripts.skills_render import (
    _carrier_skills_dir,
    _check_all,
    _core_bundled_skills_dir,
    _fix_all,
    _rendered_agents_md,
    _rendered_carrier_files,
    _rendered_skill_files,
    _stray_carrier_files,
)
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
        _fix_all(tmp_path)
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


class TestCarrierTreesMatchTheTypedCatalogue:
    """The published `narrativetrace-skills` payload and `narrativetrace`'s own bundled copy --
    Phase 3 milestone 1, D1/D2."""

    def test_rendering_twice_is_identical(self) -> None:
        assert _rendered_carrier_files() == _rendered_carrier_files()

    def test_the_carrier_and_the_bundled_copy_are_byte_identical(self) -> None:
        carrier = {
            path.relative_to(_carrier_skills_dir()): content
            for path, content in _rendered_carrier_files().items()
            if _carrier_skills_dir() in path.parents
        }
        bundled = {
            path.relative_to(_core_bundled_skills_dir()): content
            for path, content in _rendered_carrier_files().items()
            if _core_bundled_skills_dir() in path.parents
        }
        assert carrier == bundled
        assert carrier

    def test_no_drift_against_the_committed_carrier_files(self) -> None:
        assert _check_all() == []

    def test_a_removed_skills_leftover_page_is_flagged_as_a_stray(self, tmp_path: Path) -> None:
        _fix_all(tmp_path)
        stray = _carrier_skills_dir(tmp_path) / "claude" / "retired-skill" / "SKILL.md"
        stray.parent.mkdir(parents=True)
        stray.write_text("stale", encoding="utf-8")
        assert stray in _stray_carrier_files(tmp_path)
        assert stray in _check_all(tmp_path)

    def test_fix_removes_a_stray_carrier_file(self, tmp_path: Path) -> None:
        _fix_all(tmp_path)
        stray = _core_bundled_skills_dir(tmp_path) / "agents" / "retired-skill" / "SKILL.md"
        stray.parent.mkdir(parents=True)
        stray.write_text("stale", encoding="utf-8")
        _fix_all(tmp_path)
        assert not stray.exists()
        assert _check_all(tmp_path) == []
