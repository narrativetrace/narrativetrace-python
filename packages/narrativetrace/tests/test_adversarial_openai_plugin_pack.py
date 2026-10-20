# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial cases over ``scripts/openai_plugin_pack.py``'s check: shapes of manifest and archive
the main tests do not reach."""

from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

import pytest
from narrativetrace_skills import SKILLS, openai_package_entries
from scripts import openai_plugin_pack as pack

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png(width: int, height: int) -> bytes:
    return _SIGNATURE + struct.pack(">I4sII", 13, b"IHDR", width, height)


def _archive(tmp_path: Path, manifest: object, extra: dict[str, bytes] | None = None) -> Path:
    files = {
        "assets/logo.png": _png(64, 64),
        "assets/composer-icon.png": _png(64, 64),
        **(extra or {}),
    }
    target = tmp_path / "package.zip"
    with zipfile.ZipFile(target, "w") as built:
        built.writestr("plugin.json", json.dumps(manifest))
        for name, content in files.items():
            built.writestr(name, content)
    return target


def _check(archive: Path) -> list[str]:
    expected = ["assets/composer-icon.png", "assets/logo.png", "plugin.json"]
    return pack.violations(archive, expected, "1.2.3")


class TestAManifestThatIsNotTheExpectedShape:
    @pytest.mark.parametrize("manifest", [[], "text", 7, None])
    def test_a_manifest_that_is_not_a_json_object_is_one_violation_not_a_crash(
        self, tmp_path: Path, manifest: object
    ) -> None:
        assert "plugin.json is not a JSON object" in _check(_archive(tmp_path, manifest))

    @pytest.mark.parametrize("version", [123, None, ["1.2.3"], True])
    def test_a_version_that_is_not_the_expected_string_does_not_equal_it(
        self, tmp_path: Path, version: object
    ) -> None:
        problems = _check(_archive(tmp_path, {"version": version}))
        assert f"plugin.json version '{version}' does not equal 1.2.3" in problems

    def test_a_path_used_as_a_key_rather_than_a_value_is_not_a_manifest_path(
        self, tmp_path: Path
    ) -> None:
        problems = _check(_archive(tmp_path, {"version": "1.2.3", "./nowhere.png": "x"}))
        assert problems == []

    def test_a_non_png_path_must_resolve_but_is_not_measured_as_an_icon(
        self, tmp_path: Path
    ) -> None:
        archive = _archive(tmp_path, {"version": "1.2.3", "readme": "./README.md"})
        assert _check(archive) == ["manifest path './README.md' resolves to no packaged entry"]

    def test_an_icon_outside_the_assets_directory_is_measured_all_the_same(
        self, tmp_path: Path
    ) -> None:
        archive = _archive(
            tmp_path, {"version": "1.2.3", "logo": "./icons/x.png"}, {"icons/x.png": _png(10, 10)}
        )
        problems = pack.violations(
            archive,
            ["assets/composer-icon.png", "assets/logo.png", "icons/x.png", "plugin.json"],
            "1.2.3",
        )
        assert problems == ["icons/x.png is smaller than 48px (10px)"]


class TestAnIconThatIsDegenerate:
    def test_a_zero_by_zero_icon_is_below_the_floor(self, tmp_path: Path) -> None:
        archive = _archive(
            tmp_path,
            {"version": "1.2.3", "logo": "./assets/logo.png"},
            {"assets/logo.png": _png(0, 0)},
        )
        assert "assets/logo.png is smaller than 48px (0px)" in _check(archive)

    def test_a_truncated_header_is_reported_not_raised(self, tmp_path: Path) -> None:
        archive = _archive(
            tmp_path,
            {"version": "1.2.3", "logo": "./assets/logo.png"},
            {"assets/logo.png": _png(64, 64)[:20]},
        )
        assert "assets/logo.png is not a PNG: too short to hold a signature and IHDR" in _check(
            archive
        )


class TestAnArchiveThatIsNotAZip:
    def test_a_file_that_is_not_a_zip_raises_rather_than_passing(self, tmp_path: Path) -> None:
        bogus = tmp_path / "bogus.zip"
        bogus.write_bytes(b"not a zip")
        with pytest.raises(zipfile.BadZipFile):
            pack.violations(bogus, [], "1.2.3")


class TestTheReleaseVersionSource:
    def test_reads_the_version_of_the_root_it_is_given(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nversion = "7.8.9"\n', encoding="utf-8")
        assert pack.release_version(tmp_path) == "7.8.9"

    def test_a_pyproject_with_no_version_raises_instead_of_inventing_one(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        with pytest.raises(KeyError):
            pack.release_version(tmp_path)


class TestTheDerivedLayoutAgainstTheRealCatalogue:
    def test_every_skill_name_appears_exactly_once(self) -> None:
        entries = openai_package_entries(SKILLS)
        assert len(entries) == len(set(entries))
        assert sum(1 for entry in entries if entry.startswith("skills/")) == len(SKILLS)
