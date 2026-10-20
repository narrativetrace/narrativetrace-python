# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The two listing icons the manifest points at, as files under the package root: hand-made
sources, never rendered. They are PLACEHOLDERS (a single flat colour) until a brand asset
replaces them; this test pins the vendor's floor for any replacement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from narrativetrace_skills.render.png_dimensions import png_dimensions

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "openai-plugin"
_MAX_ICON_BYTES = 5 * 1024 * 1024


def _interface() -> dict[str, str]:
    manifest = json.loads((_PACKAGE_ROOT / "plugin.json").read_text(encoding="utf-8"))
    return manifest["extensions"]["com.openai"]["interface"]  # type: ignore[no-any-return]


@pytest.mark.parametrize("key", ["logo", "composerIcon"])
class TestTheListingIcons:
    def test_the_manifest_path_resolves_to_a_file_under_the_package_root(self, key: str) -> None:
        path = _interface()[key]
        assert path.startswith("./assets/")
        assert (_PACKAGE_ROOT / path).is_file()

    def test_the_icon_is_square_and_at_least_48_pixels(self, key: str) -> None:
        width, height = png_dimensions((_PACKAGE_ROOT / _interface()[key]).read_bytes())
        assert width == height
        assert width >= 48

    def test_the_icon_is_within_five_mebibytes(self, key: str) -> None:
        assert (_PACKAGE_ROOT / _interface()[key]).stat().st_size <= _MAX_ICON_BYTES


def test_the_assets_directory_holds_exactly_the_two_icons() -> None:
    names = sorted(path.name for path in (_PACKAGE_ROOT / "assets").iterdir())
    assert names == ["composer-icon.png", "logo.png"]
