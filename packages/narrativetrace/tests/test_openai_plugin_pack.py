# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``scripts/openai_plugin_pack.py``: the OpenAI plugin directory's release ZIP. Its entry list is
DERIVED from the catalogue and ASSERTED against the built archive (release rule 5); the ZIP is a
build output, never committed. These tests exercise every check against hand-built archives, then
the real build against the real tree."""

from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

import pytest
from narrativetrace_skills import OPENAI_DIRECTORY, SKILLS, openai_package_entries
from scripts import openai_plugin_pack as pack
from scripts.skills_render import _codex_skill_md_path, _openai_plugin_dir
from scripts.translation_check import REPO_ROOT

_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png(width: int, height: int) -> bytes:
    return _SIGNATURE + struct.pack(">I4sII", 13, b"IHDR", width, height)


def _manifest(version: str | None = "1.2.3", logo: str = "./assets/logo.png") -> bytes:
    payload: dict[str, object] = {"name": "narrativetrace-x"}
    if version is not None:
        payload["version"] = version
    payload["extensions"] = {
        "com.openai": {"interface": {"logo": logo, "composerIcon": "./assets/composer-icon.png"}}
    }
    return json.dumps(payload).encode()


def _valid(version: str = "1.2.3") -> dict[str, bytes]:
    return {
        "plugin.json": _manifest(version),
        "skills/narrativetrace-doctor/SKILL.md": b"page",
        "assets/logo.png": _png(64, 64),
        "assets/composer-icon.png": _png(64, 64),
    }


def _zip(tmp_path: Path, entries: dict[str, bytes], *, directories: bool = False) -> Path:
    target = tmp_path / "package.zip"
    with zipfile.ZipFile(target, "w") as archive:
        if directories:
            archive.writestr("skills/", b"")
            archive.writestr("assets/", b"")
        for name, content in entries.items():
            archive.writestr(name, content)
    return target


def _violations(tmp_path: Path, entries: dict[str, bytes], version: str = "1.2.3") -> list[str]:
    return pack.violations(_zip(tmp_path, entries), sorted(_valid()), version)


class TestAValidPackage:
    def test_has_no_violations(self, tmp_path: Path) -> None:
        assert _violations(tmp_path, _valid()) == []

    def test_directory_entries_are_a_zip_format_artifact_not_unexpected_content(
        self, tmp_path: Path
    ) -> None:
        archive = _zip(tmp_path, _valid(), directories=True)
        assert pack.violations(archive, sorted(_valid()), "1.2.3") == []

    def test_an_icon_of_exactly_48_pixels_is_accepted(self, tmp_path: Path) -> None:
        entries = {**_valid(), "assets/logo.png": _png(48, 48)}
        assert _violations(tmp_path, entries) == []

    def test_an_icon_of_exactly_five_mebibytes_is_accepted(self, tmp_path: Path) -> None:
        entries = {**_valid(), "assets/logo.png": _png(64, 64).ljust(5 * 1024 * 1024, b"\0")}
        assert _violations(tmp_path, entries) == []


class TestTheEntrySetEqualsTheLayout:
    def test_a_missing_expected_entry_is_flagged(self, tmp_path: Path) -> None:
        entries = _valid()
        del entries["skills/narrativetrace-doctor/SKILL.md"]
        assert any(
            v.startswith("entries do not match the layout") for v in _violations(tmp_path, entries)
        )

    def test_an_extra_entry_is_flagged(self, tmp_path: Path) -> None:
        entries = {**_valid(), "skills/stray/SKILL.md": b"x"}
        assert any(
            v.startswith("entries do not match the layout") for v in _violations(tmp_path, entries)
        )

    def test_a_duplicated_entry_is_flagged(self, tmp_path: Path) -> None:
        target = tmp_path / "dup.zip"
        with zipfile.ZipFile(target, "w") as archive:
            for name, content in _valid().items():
                archive.writestr(name, content)
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr("assets/logo.png", _png(64, 64))
        problems = pack.violations(target, sorted(_valid()), "1.2.3")
        assert any(v.startswith("entries do not match the layout") for v in problems)


class TestForbiddenEntries:
    @pytest.mark.parametrize(
        "name", ["hooks/pre-install.js", "mcp.json", "widget.app.json", "Hooks.class"]
    )
    def test_each_is_flagged_by_name(self, tmp_path: Path, name: str) -> None:
        problems = _violations(tmp_path, {**_valid(), name: b"x"})
        assert f"forbidden entry present: {name}" in problems

    @pytest.mark.parametrize(
        "name", ["hooksworthy/file.js", "notmcp.json", "widgetapp.json", "NotesClass.txt"]
    )
    def test_a_near_miss_sibling_sharing_the_prefix_or_suffix_is_not(
        self, tmp_path: Path, name: str
    ) -> None:
        problems = _violations(tmp_path, {**_valid(), name: b"x"})
        assert not [v for v in problems if v.startswith("forbidden")]


class TestTheVersion:
    @pytest.mark.parametrize(
        "version", ["1.2.3-SNAPSHOT", "1.2", "1.2.3.4", "v1.2.3", "1.2.3\n", ""]
    )
    def test_a_non_semver_expected_version_is_flagged(self, tmp_path: Path, version: str) -> None:
        problems = _violations(tmp_path, {**_valid(), "plugin.json": _manifest(version)}, version)
        assert any("is not semantic" in v for v in problems)

    def test_a_manifest_version_that_is_not_the_expected_one_is_flagged(
        self, tmp_path: Path
    ) -> None:
        problems = _violations(tmp_path, {**_valid(), "plugin.json": _manifest("9.9.9")})
        assert "plugin.json version '9.9.9' does not equal 1.2.3" in problems

    def test_a_manifest_with_no_version_key_is_flagged(self, tmp_path: Path) -> None:
        problems = _violations(tmp_path, {**_valid(), "plugin.json": _manifest(None)})
        assert 'plugin.json carries no "version" key' in problems


class TestTheManifest:
    def test_a_package_with_no_manifest_is_flagged_not_crashed_on(self, tmp_path: Path) -> None:
        entries = _valid()
        del entries["plugin.json"]
        assert "plugin.json is missing from the zip" in _violations(tmp_path, entries)

    def test_a_manifest_that_is_not_json_is_flagged(self, tmp_path: Path) -> None:
        problems = _violations(tmp_path, {**_valid(), "plugin.json": b"{not json"})
        assert "plugin.json is not valid JSON" in problems

    def test_a_manifest_path_that_resolves_to_no_entry_is_flagged(self, tmp_path: Path) -> None:
        entries = {**_valid(), "plugin.json": _manifest(logo="./assets/missing.png")}
        problems = _violations(tmp_path, entries)
        assert "manifest path './assets/missing.png' resolves to no packaged entry" in problems

    def test_prose_that_mentions_a_path_mid_sentence_is_not_a_manifest_path(
        self, tmp_path: Path
    ) -> None:
        payload = json.loads(_manifest())
        payload["description"] = "see ./assets/missing.png for the logo"
        entries = {**_valid(), "plugin.json": json.dumps(payload).encode()}
        assert _violations(tmp_path, entries) == []

    def test_a_path_nested_in_a_list_is_still_checked(self, tmp_path: Path) -> None:
        payload = json.loads(_manifest())
        payload["screenshots"] = ["./assets/shot.png"]
        entries = {**_valid(), "plugin.json": json.dumps(payload).encode()}
        assert "manifest path './assets/shot.png' resolves to no packaged entry" in _violations(
            tmp_path, entries
        )


class TestTheIcons:
    def test_an_icon_over_five_mebibytes_is_flagged(self, tmp_path: Path) -> None:
        entries = {**_valid(), "assets/logo.png": _png(64, 64).ljust(5 * 1024 * 1024 + 1, b"\0")}
        assert "assets/logo.png is larger than 5 MiB" in _violations(tmp_path, entries)

    def test_a_non_square_icon_is_flagged(self, tmp_path: Path) -> None:
        entries = {**_valid(), "assets/logo.png": _png(64, 32)}
        assert "assets/logo.png is not square (64x32)" in _violations(tmp_path, entries)

    def test_an_icon_of_47_pixels_is_flagged(self, tmp_path: Path) -> None:
        entries = {**_valid(), "assets/logo.png": _png(47, 47)}
        assert "assets/logo.png is smaller than 48px (47px)" in _violations(tmp_path, entries)

    def test_an_icon_that_is_not_a_png_is_flagged(self, tmp_path: Path) -> None:
        entries = {**_valid(), "assets/logo.png": b"not a png at all, but long enough......"}
        assert "assets/logo.png is not a PNG: bad signature" in _violations(tmp_path, entries)


class TestTheRealBuild:
    def test_the_release_version_is_the_root_pyprojects_and_semantic(self) -> None:
        version = pack.release_version()
        assert version in (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert pack.SEMVER.fullmatch(version)

    def test_the_built_archive_holds_exactly_the_catalogue_derived_entries(
        self, tmp_path: Path
    ) -> None:
        archive = pack.build_zip(REPO_ROOT, "1.2.3", tmp_path)
        assert archive == tmp_path / f"{OPENAI_DIRECTORY.base.name}-openai-plugin-1.2.3.zip"
        with zipfile.ZipFile(archive) as built:
            assert built.namelist() == openai_package_entries(SKILLS)

    def test_the_skill_pages_are_the_drift_pinned_agents_flavour_byte_for_byte(
        self, tmp_path: Path
    ) -> None:
        archive = pack.build_zip(REPO_ROOT, "1.2.3", tmp_path)
        with zipfile.ZipFile(archive) as built:
            for skill in SKILLS:
                page = _codex_skill_md_path(skill.canonical_name).read_bytes()
                assert built.read(f"skills/{skill.canonical_name}/SKILL.md") == page

    def test_the_manifest_inside_carries_the_version_and_the_assets_are_the_committed_ones(
        self, tmp_path: Path
    ) -> None:
        archive = pack.build_zip(REPO_ROOT, "1.2.3", tmp_path)
        with zipfile.ZipFile(archive) as built:
            assert json.loads(built.read("plugin.json"))["version"] == "1.2.3"
            for asset in ("logo.png", "composer-icon.png"):
                committed = (_openai_plugin_dir() / "assets" / asset).read_bytes()
                assert built.read(f"assets/{asset}") == committed

    def test_building_twice_is_byte_identical(self, tmp_path: Path) -> None:
        first = pack.build_zip(REPO_ROOT, "1.2.3", tmp_path / "a").read_bytes()
        second = pack.build_zip(REPO_ROOT, "1.2.3", tmp_path / "b").read_bytes()
        assert first == second

    def test_every_entry_carries_the_fixed_timestamp(self, tmp_path: Path) -> None:
        archive = pack.build_zip(REPO_ROOT, "1.2.3", tmp_path)
        with zipfile.ZipFile(archive) as built:
            assert {info.date_time for info in built.infolist()} == {(1980, 1, 1, 0, 0, 0)}

    @pytest.mark.parametrize("version", ["1.2.3-SNAPSHOT", "1.2", "", " ", "1.2.3\n"])
    def test_a_non_semver_version_is_refused_before_anything_is_written(
        self, tmp_path: Path, version: str
    ) -> None:
        with pytest.raises(ValueError, match="is not semantic"):
            pack.build_zip(REPO_ROOT, version, tmp_path / "out")
        assert not (tmp_path / "out").exists()

    def test_a_tree_missing_a_skill_page_fails_naming_the_path(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match=r"SKILL\.md"):
            pack.package_files(tmp_path, "1.2.3")


class TestTheCommandLine:
    def test_check_builds_in_a_temporary_directory_and_passes_on_this_tree(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert pack.main(["--check"]) == 0
        out = capsys.readouterr().out
        assert "openai_plugin_pack: ok" in out
        assert not list(Path.cwd().glob("*openai-plugin*.zip"))

    def test_build_writes_the_archive_into_the_named_directory(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        assert pack.main(["--build", str(tmp_path)]) == 0
        version = pack.release_version()
        assert (tmp_path / f"narrativetrace-python-openai-plugin-{version}.zip").is_file()
        assert "wrote" in capsys.readouterr().out

    @pytest.mark.parametrize("argv", [[], ["--build"], ["--other"], ["--check", "x"]])
    def test_any_other_invocation_prints_usage_and_fails(
        self, capsys: pytest.CaptureFixture[str], argv: list[str]
    ) -> None:
        assert pack.main(argv) == 1
        assert "Usage:" in capsys.readouterr().err
