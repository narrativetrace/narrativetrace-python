# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/skills_render.py`: each shipped skill's (`narrativetrace-doctor`,
`add-narrative-tracing`, `narrativetrace-feedback`, `add-narrativetrace-clarity`)
`.claude/skills/<name>/SKILL.md` and `.agents/skills/<name>/SKILL.md`, this
repository's own `AGENTS.md` managed section, `.claude-plugin/marketplace.json` (the Claude Code
plugin-marketplace listing, Phase 4 milestone 1), the published `narrativetrace-skills`
distribution's `skills/**` payload and its byte-identical copy bundled as `narrativetrace`'s own
package data (`narrativetrace/_skills/**`) are BUILD OUTPUT of the typed `narrativetrace_skills`
catalogue — this drift check is what `poe check`'s own `skills-check` task runs, exercised here
too so a plain `uv run poe coverage` run also measures and gates it (`scripts/skills_render.py`
itself is a CLI entry point, not imported by anything else that would otherwise cover it)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from scripts.skills_render import (
    _carrier_skills_dir,
    _check_all,
    _core_bundled_skills_dir,
    _cursor_marketplace_json_path,
    _cursor_plugin_json_path,
    _cursor_rule_path,
    _fix_all,
    _marketplace_json_path,
    _openai_plugin_json_path,
    _rendered_agents_md,
    _rendered_carrier_files,
    _rendered_cursor_rule,
    _rendered_marketplace_json,
    _rendered_openai_plugin_json,
    _rendered_skill_files,
    _stray_carrier_files,
)
from scripts.translation_check import REPO_ROOT


class TestRenderedArtifactsMatchTheTypedCatalogue:
    def test_no_drift_against_the_committed_files(self) -> None:
        """Fails naming the drifted path(s) — run `python scripts/skills_render.py --fix`."""
        assert _check_all() == []

    def test_rendered_skill_files_cover_every_shipped_skill(self) -> None:
        paths = {path.name for path in _rendered_skill_files()}
        assert paths == {"SKILL.md"}

    def test_rendered_skill_files_cover_both_platforms_for_every_skill(self) -> None:
        # Seven shipped skills, two platforms (Claude Code + Codex) rendering the same body under
        # different frontmatter -- fourteen files, not seven.
        rendered = _rendered_skill_files()
        assert len(rendered) == 14
        assert sum(1 for path in rendered if ".claude" in path.parts) == 7
        assert sum(1 for path in rendered if ".agents" in path.parts) == 7

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


class TestMarketplaceFileMatchesTheTypedCatalogue:
    """`.claude-plugin/marketplace.json` -- the Claude Code plugin-marketplace listing rendered
    from `narrativetrace_skills.MARKETPLACE` (Phase 4 milestone 1)."""

    def test_no_drift_against_the_committed_file(self) -> None:
        assert _check_all() == []

    def test_lives_at_the_repo_root_claude_plugin_directory(self) -> None:
        assert _marketplace_json_path() == REPO_ROOT / ".claude-plugin" / "marketplace.json"

    def test_is_included_in_fix_all_and_check_all(self, tmp_path: Path) -> None:
        written = _fix_all(tmp_path)
        marketplace_path = _marketplace_json_path(tmp_path)
        assert marketplace_path in written
        assert marketplace_path.read_text(encoding="utf-8") == _rendered_marketplace_json()
        assert _check_all(tmp_path) == []

    def test_check_all_flags_a_hand_edited_marketplace_file(self, tmp_path: Path) -> None:
        _fix_all(tmp_path)
        _marketplace_json_path(tmp_path).write_text("tampered", encoding="utf-8")
        assert _marketplace_json_path(tmp_path) in _check_all(tmp_path)


class TestOpenAiPluginJsonMatchesTheTypedCatalogue:
    """`packages/narrativetrace-skills-catalogue/openai-plugin/plugin.json` -- the OpenAI plugin
    directory's versionless manifest rendered from `narrativetrace_skills.OPENAI_DIRECTORY`
    (Phase 4 milestone 8)."""

    def test_the_committed_file_equals_a_fresh_render(self) -> None:
        assert _openai_plugin_json_path().read_text(encoding="utf-8") == (
            _rendered_openai_plugin_json()
        )

    def test_lives_inside_the_catalogue_package_not_at_the_repo_root(self) -> None:
        assert _openai_plugin_json_path() == (
            REPO_ROOT
            / "packages"
            / "narrativetrace-skills-catalogue"
            / "openai-plugin"
            / "plugin.json"
        )
        assert not (REPO_ROOT / "plugin.json").exists()

    def test_is_included_in_fix_all_and_check_all(self, tmp_path: Path) -> None:
        written = _fix_all(tmp_path)
        path = _openai_plugin_json_path(tmp_path)
        assert path in written
        assert path.read_text(encoding="utf-8") == _rendered_openai_plugin_json()
        assert _check_all(tmp_path) == []

    def test_check_all_flags_a_hand_edited_file(self, tmp_path: Path) -> None:
        _fix_all(tmp_path)
        _openai_plugin_json_path(tmp_path).write_text("tampered", encoding="utf-8")
        assert _openai_plugin_json_path(tmp_path) in _check_all(tmp_path)

    def test_check_all_flags_a_missing_file(self, tmp_path: Path) -> None:
        _fix_all(tmp_path)
        _openai_plugin_json_path(tmp_path).unlink()
        assert _openai_plugin_json_path(tmp_path) in _check_all(tmp_path)


class TestCursorFilesMatchTheTypedCatalogueAndThePlatformTable:
    """`.cursor-plugin/plugin.json`, `.cursor-plugin/marketplace.json` (rendered from the same
    `MARKETPLACE` as the Claude file) and `.cursor/rules/narrativetrace.mdc` (the platform
    table's Cursor pointer, unstamped) — Phase 8, platform pointers."""

    def test_the_files_live_where_cursor_looks_for_them(self) -> None:
        assert _cursor_plugin_json_path() == REPO_ROOT / ".cursor-plugin" / "plugin.json"
        assert _cursor_marketplace_json_path() == REPO_ROOT / ".cursor-plugin" / "marketplace.json"
        assert _cursor_rule_path() == REPO_ROOT / ".cursor" / "rules" / "narrativetrace.mdc"

    def test_the_committed_rule_is_the_unstamped_one_the_installer_adopts(self) -> None:
        rule = _cursor_rule_path().read_text(encoding="utf-8")

        assert rule == _rendered_cursor_rule()
        assert "<!-- narrativetrace:start -->\n" in rule

    def test_the_plugin_manifest_points_at_the_rule_file_this_check_holds(self) -> None:
        plugin = json.loads(_cursor_plugin_json_path().read_text(encoding="utf-8"))

        assert REPO_ROOT.joinpath(plugin["rules"]).resolve() == _cursor_rule_path().resolve()
        assert REPO_ROOT.joinpath(plugin["skills"]).is_dir()

    def test_fix_all_writes_and_check_all_covers_all_three(self, tmp_path: Path) -> None:
        written = _fix_all(tmp_path)

        for path in (
            _cursor_plugin_json_path(tmp_path),
            _cursor_marketplace_json_path(tmp_path),
            _cursor_rule_path(tmp_path),
        ):
            assert path in written
            assert path.is_file()
        assert _check_all(tmp_path) == []

    @pytest.mark.parametrize(
        "path_of",
        [_cursor_plugin_json_path, _cursor_marketplace_json_path, _cursor_rule_path],
    )
    def test_check_all_flags_a_hand_edited_cursor_file(
        self, tmp_path: Path, path_of: Callable[[Path], Path]
    ) -> None:
        _fix_all(tmp_path)
        path_of(tmp_path).write_text("tampered", encoding="utf-8")

        assert path_of(tmp_path) in _check_all(tmp_path)

    @pytest.mark.parametrize(
        "path_of",
        [_cursor_plugin_json_path, _cursor_marketplace_json_path, _cursor_rule_path],
    )
    def test_check_all_flags_a_missing_cursor_file(
        self, tmp_path: Path, path_of: Callable[[Path], Path]
    ) -> None:
        _fix_all(tmp_path)
        path_of(tmp_path).unlink()

        assert path_of(tmp_path) in _check_all(tmp_path)
