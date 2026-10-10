# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial tests for skills_render.py: marketplace wiring edge cases."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.skills_render import (
    _check_all,
    _fix_all,
    _marketplace_json_path,
    _rendered_marketplace_json,
)


class TestMarketplaceJsonPathHandling:
    """Edge cases for .claude-plugin directory handling."""

    def test_marketplace_path_created_when_missing(self, tmp_path: Path) -> None:
        """When .claude-plugin/ doesn't exist, _fix_all should create it."""
        # Verify directory doesn't exist initially
        plugin_dir = tmp_path / ".claude-plugin"
        assert not plugin_dir.exists()

        # Run _fix_all
        written = _fix_all(tmp_path)

        # Check that marketplace.json was written
        marketplace_path = _marketplace_json_path(tmp_path)
        assert marketplace_path.is_file()
        assert marketplace_path in written

    def test_marketplace_json_created_in_existing_directory(self, tmp_path: Path) -> None:
        """When .claude-plugin/ exists with other files, marketplace.json is written alongside."""
        plugin_dir = tmp_path / ".claude-plugin"
        plugin_dir.mkdir()
        unrelated = plugin_dir / "other.txt"
        unrelated.write_text("keep me", encoding="utf-8")

        # Run _fix_all
        _fix_all(tmp_path)

        # Both files should exist
        assert unrelated.is_file()
        assert unrelated.read_text(encoding="utf-8") == "keep me"
        assert _marketplace_json_path(tmp_path).is_file()

    def test_check_all_detects_missing_marketplace(self, tmp_path: Path) -> None:
        """When marketplace.json doesn't exist, _check_all flags it."""
        # Don't write any files
        drifted = _check_all(tmp_path)

        # Marketplace should be in drifted list
        marketplace_path = _marketplace_json_path(tmp_path)
        assert marketplace_path in drifted

    def test_check_all_detects_tampered_marketplace(self, tmp_path: Path) -> None:
        """When marketplace.json content differs, _check_all flags it."""
        _fix_all(tmp_path)
        marketplace_path = _marketplace_json_path(tmp_path)

        # Tamper with it
        marketplace_path.write_text("tampered", encoding="utf-8")

        drifted = _check_all(tmp_path)
        assert marketplace_path in drifted

    def test_fix_all_overwrites_tampered_marketplace(self, tmp_path: Path) -> None:
        """When marketplace.json is tampered, _fix_all restores it."""
        _fix_all(tmp_path)
        marketplace_path = _marketplace_json_path(tmp_path)
        original = marketplace_path.read_text(encoding="utf-8")

        # Tamper
        marketplace_path.write_text("tampered", encoding="utf-8")

        # Fix
        _fix_all(tmp_path)

        # Should be restored
        assert marketplace_path.read_text(encoding="utf-8") == original

    def test_marketplace_json_is_valid_json(self, tmp_path: Path) -> None:
        """The rendered marketplace.json must be valid JSON."""
        rendered = _rendered_marketplace_json()
        # Should not raise
        payload = json.loads(rendered)
        assert "name" in payload
        assert "owner" in payload
        assert "plugins" in payload

    def test_marketplace_json_contains_required_vendor_keys(self, tmp_path: Path) -> None:
        """The rendered marketplace.json must contain all keys the vendor requires."""
        payload = json.loads(_rendered_marketplace_json())
        required_plugin_keys = {"name", "source", "description", "license", "homepage", "keywords"}

        assert {"name", "owner", "plugins"} <= payload.keys()
        assert {"name", "url"} <= payload["owner"].keys()
        assert all(required_plugin_keys <= plugin.keys() for plugin in payload["plugins"])

    def test_fix_all_creates_parent_directories(self, tmp_path: Path) -> None:
        """_fix_all should create all parent directories if needed."""
        nested_root = tmp_path / "a" / "b" / "c"
        # Don't create it; _fix_all should
        assert not nested_root.exists()

        _fix_all(nested_root)

        # Marketplace should exist
        marketplace_path = _marketplace_json_path(nested_root)
        assert marketplace_path.is_file()

    def test_check_all_empty_root_lists_all_drifts(self, tmp_path: Path) -> None:
        """On an empty root, _check_all lists marketplace as drifted."""
        drifted = _check_all(tmp_path)

        # Should include the marketplace path
        marketplace_path = _marketplace_json_path(tmp_path)
        assert any(p == marketplace_path for p in drifted)
