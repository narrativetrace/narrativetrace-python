# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The shape of the marketplace listing this repository publishes, asserted on the typed source
-- no vendor dependency here (that lives in ``scripts/vendor_validation.py``'s heavy-tier gate).
The vendor requires ``name``, ``owner`` and ``plugins`` at the top level and ``name`` plus
``source`` in every entry; rejects a relative source that does not start with ``./`` or that
contains ``..``; and treats an entry with no ``plugin.json`` as the manifest itself, which is why
the entry name has to be the plugin's own name.
"""

from __future__ import annotations

import re
from pathlib import Path

from narrativetrace_skills.catalogue_index import MARKETPLACE, SKILLS
from narrativetrace_skills.render.marketplace import render_marketplace_json


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


_REPO_ROOT = _repo_root()


class TestCatalogueMarketplace:
    def test_the_marketplace_and_its_one_plugin_share_the_runtime_slug_name(self) -> None:
        assert MARKETPLACE.name == "narrativetrace-python"

    def test_the_rendered_file_carries_every_key_the_vendor_requires(self) -> None:
        rendered = render_marketplace_json(MARKETPLACE)
        assert '"name": "narrativetrace-python"' in rendered
        assert '"owner": {' in rendered
        assert '"plugins": [' in rendered
        assert '"source": "./.claude"' in rendered

    def test_the_rendered_file_names_the_one_plugin_exactly_once_besides_the_marketplace_itself(
        self,
    ) -> None:
        rendered = render_marketplace_json(MARKETPLACE)
        # The marketplace name AND the plugin entry's name, and no third listing.
        assert len(rendered.split('"name": "narrativetrace-python"')) == 3

    def test_the_rendered_file_carries_no_version_key_or_literal(self) -> None:
        rendered = render_marketplace_json(MARKETPLACE)
        assert '"version"' not in rendered
        assert re.search(r"\d+\.\d+\.\d+", rendered) is None

    def test_the_plugin_source_is_a_relative_path_the_vendor_accepts(self) -> None:
        assert MARKETPLACE.plugin_source.startswith("./")
        assert ".." not in MARKETPLACE.plugin_source
        assert "\\" not in MARKETPLACE.plugin_source

    def test_the_plugin_source_directory_holds_every_skill_page_the_catalogue_declares(
        self,
    ) -> None:
        plugin_root = (_REPO_ROOT / MARKETPLACE.plugin_source).resolve()
        for skill in SKILLS:
            page = plugin_root / "skills" / skill.canonical_name / "SKILL.md"
            assert page.is_file(), f"{skill.canonical_name}'s page must live under the plugin"

    def test_the_listing_declares_the_open_licence_the_pages_ship_under(self) -> None:
        assert MARKETPLACE.license == "Apache-2.0"

    def test_the_listing_carries_search_keywords_and_a_homepage(self) -> None:
        assert "narrativetrace" in MARKETPLACE.keywords
        assert "python" in MARKETPLACE.keywords
        assert MARKETPLACE.homepage.startswith("https://")
