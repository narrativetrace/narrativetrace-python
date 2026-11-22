# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The Claude plugin folder's own files, pinned against the committed tree: ``plugin.json`` (the
manifest the directory reads), ``icon.png`` (a copy of the OpenAI package's logo) and the claim
that the manifest and the root marketplace entry say the same thing about the plugin. No Claude
page, in the repository or in either carrier, carries an ``allowed-tools`` line."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from narrativetrace_skills.catalogue_index import CLAUDE_DIRECTORY, MARKETPLACE, SKILLS
from narrativetrace_skills.render.claude_plugin_json import render_claude_plugin_json
from narrativetrace_skills.render.png_dimensions import png_dimensions


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


_ROOT = _repo_root()
_PLUGIN_DIR = _ROOT / MARKETPLACE.plugin_source / ".claude-plugin"
_MANIFEST = _PLUGIN_DIR / "plugin.json"
_ICON = _PLUGIN_DIR / "icon.png"
_OPENAI_LOGO = (
    _ROOT / "packages" / "narrativetrace-skills-catalogue" / "openai-plugin" / "assets" / "logo.png"
)
_MARKETPLACE = _ROOT / ".claude-plugin" / "marketplace.json"

# Keys that would add components to a plugin whose manifest is the source of its content.
_COMPONENT_KEYS = ("commands", "agents", "skills", "hooks", "mcpServers", "outputStyles", "strict")

_CLAUDE_PAGE_ROOTS = (
    ".claude/skills",
    "packages/narrativetrace-skills/skills/claude",
    "packages/narrativetrace/src/narrativetrace/_skills/claude",
)


class TestThePluginManifest:
    def test_the_committed_file_equals_a_fresh_render(self) -> None:
        assert _MANIFEST.is_file(), "run `python scripts/skills_render.py --fix` and commit it"
        assert _MANIFEST.read_text(encoding="utf-8") == render_claude_plugin_json(CLAUDE_DIRECTORY)

    def test_it_lives_in_the_folder_the_marketplace_entry_names_as_its_source(self) -> None:
        assert MARKETPLACE.plugin_source == "./.claude"
        assert _MANIFEST == (_ROOT / ".claude" / ".claude-plugin" / "plugin.json")

    def test_it_names_the_plugin_as_the_marketplace_entry_does(self) -> None:
        manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        entry = json.loads(_MARKETPLACE.read_text(encoding="utf-8"))["plugins"][0]
        assert manifest["name"] == entry["name"] == MARKETPLACE.name

    def test_the_manifest_and_the_marketplace_entry_agree_on_every_shared_field(self) -> None:
        manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        entry = json.loads(_MARKETPLACE.read_text(encoding="utf-8"))["plugins"][0]
        for field in ("name", "description", "license", "homepage", "keywords"):
            assert manifest[field] == entry[field], field

    def test_the_marketplace_entry_adds_no_components_and_keeps_strict_at_its_default(self) -> None:
        entry = json.loads(_MARKETPLACE.read_text(encoding="utf-8"))["plugins"][0]
        for key in _COMPONENT_KEYS:
            assert key not in entry, key

    def test_the_directory_listing_fields_live_only_in_the_manifest(self) -> None:
        manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
        entry = json.loads(_MARKETPLACE.read_text(encoding="utf-8"))["plugins"][0]
        assert manifest["icon"] == "./.claude-plugin/icon.png"
        assert (_ROOT / ".claude" / manifest["icon"]).is_file()
        assert "icon" not in entry

    def test_it_carries_no_version_key(self) -> None:
        assert "version" not in json.loads(_MANIFEST.read_text(encoding="utf-8"))


class TestThePluginIcon:
    def test_the_committed_icon_is_byte_identical_to_the_openai_logo(self) -> None:
        assert _ICON.is_file(), "run `python scripts/skills_render.py --fix` and commit it"
        assert _ICON.read_bytes() == _OPENAI_LOGO.read_bytes()

    def test_the_icon_meets_the_directorys_floor(self) -> None:
        # Square PNG, 512 to 2048 pixels, under 2 MB.
        data = _ICON.read_bytes()
        width, height = png_dimensions(data)
        assert width == height
        assert 512 <= width <= 2048
        assert len(data) < 2 * 1024 * 1024


@pytest.mark.parametrize("root", _CLAUDE_PAGE_ROOTS)
class TestNoClaudePageCarriesAnAllowedToolsLine:
    def test_the_tree_has_a_page_per_skill_and_none_has_the_key(self, root: str) -> None:
        names = sorted(path.name for path in (_ROOT / root).iterdir() if path.is_dir())
        assert names == sorted(skill.canonical_name for skill in SKILLS)
        for name in names:
            page = (_ROOT / root / name / "SKILL.md").read_text(encoding="utf-8")
            assert "allowed-tools" not in page, f"{root}/{name}"
