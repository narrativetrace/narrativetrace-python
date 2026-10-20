# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The committed ``plugin.json`` against the vendor's plugin schema shape. CI never fetches the
schema (the directory portal's own validation on the first upload is the by-hand check), so this
is the offline stand-in: every top-level key is one the schema allows, the two required keys are
present, ``name`` matches the schema's pattern, the asset paths are relative to the package root,
and the skills-only rules hold (no ``version`` in the committed file, no ``hooks``/``apps``)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from narrativetrace_skills.catalogue_index import OPENAI_DIRECTORY
from narrativetrace_skills.render.openai_plugin import SCHEMA_URL, render_openai_plugin_json

_PLUGIN_JSON = Path(__file__).resolve().parent.parent / "openai-plugin" / "plugin.json"

# The schema's ten top-level keys (agent-plugins.org/schemas/1.0.0/plugin.schema.json).
_SCHEMA_TOP_LEVEL_KEYS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}

# Copied from the schema's `name` pattern (agent-plugins.org/schemas/1.0.0/plugin.schema.json):
# lower-case alphanumerics, `.` and `-`, never starting or ending with a separator and never
# carrying `--` or `..`.
_NAME_PATTERN = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return json.loads(_PLUGIN_JSON.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


class TestTheCommittedManifestFitsTheSchemasShape:
    def test_is_the_committed_render_of_the_listing(self) -> None:
        assert _PLUGIN_JSON.read_text(encoding="utf-8") == render_openai_plugin_json(
            OPENAI_DIRECTORY
        )

    def test_every_top_level_key_is_one_the_schema_allows(self, manifest: dict[str, Any]) -> None:
        assert set(manifest) <= _SCHEMA_TOP_LEVEL_KEYS

    def test_the_two_required_keys_are_present(self, manifest: dict[str, Any]) -> None:
        assert {"$schema", "name"} <= set(manifest)

    def test_the_schema_url_is_the_vendors(self, manifest: dict[str, Any]) -> None:
        assert manifest["$schema"] == SCHEMA_URL
        assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"

    def test_the_name_matches_the_schemas_pattern(self, manifest: dict[str, Any]) -> None:
        assert _NAME_PATTERN.match(manifest["name"])

    @pytest.mark.parametrize(
        "name", ["", "-x", "x-", ".x", "x.", "a--b", "a..b", "Upper", "under_score", "spa ce"]
    )
    def test_the_pattern_copy_rejects_near_misses(self, name: str) -> None:
        assert _NAME_PATTERN.match(name) is None

    @pytest.mark.parametrize("name", ["a", "narrativetrace-python", "a.b-c", "x1"])
    def test_the_pattern_copy_accepts_conforming_names(self, name: str) -> None:
        assert _NAME_PATTERN.match(name)

    def test_the_committed_file_carries_no_version_key(self, manifest: dict[str, Any]) -> None:
        assert "version" not in manifest

    def test_carries_no_hooks_or_apps_key_at_any_depth(self) -> None:
        text = _PLUGIN_JSON.read_text(encoding="utf-8")
        assert '"hooks"' not in text
        assert '"apps"' not in text

    def test_the_two_asset_paths_are_relative_to_the_package_root(
        self, manifest: dict[str, Any]
    ) -> None:
        interface = manifest["extensions"]["com.openai"]["interface"]
        assert interface["logo"] == "./assets/logo.png"
        assert interface["composerIcon"] == "./assets/composer-icon.png"

    def test_the_listing_fields_respect_the_directorys_ceiling(
        self, manifest: dict[str, Any]
    ) -> None:
        interface = manifest["extensions"]["com.openai"]["interface"]
        assert len(interface["displayName"]) <= 30
        assert len(interface["shortDescription"]) <= 30
