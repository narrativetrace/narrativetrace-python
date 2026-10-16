# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The Context7 gate (`scripts/context7_check.py`): the shipped `context7.json` is valid, derived
from the tags, and every code fence Context7 will index carries a language tag."""

from __future__ import annotations

import json
import subprocess  # nosec B404 - fixed git argv building a throwaway repo
from pathlib import Path
from typing import Any

import pytest
from scripts.context7_check import (
    check,
    check_fences,
    check_previous_versions,
    check_schema,
    indexed_files,
    load_config,
    untagged_fences,
)
from scripts.translation_check import REPO_ROOT

_BASE: dict[str, Any] = {
    "folders": ["documentation"],
    "excludeFolders": ["documentation/es"],
    "excludeFiles": ["LEAME.md"],
}


def _write(root: Path, relative: str, text: str = "# T\n") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _relative(root: Path, config: dict[str, Any]) -> list[str]:
    return [p.relative_to(root).as_posix() for p in indexed_files(root, config)]


class TestUntaggedFences:
    def test_a_bare_backtick_fence_is_reported_at_its_opening_line(self) -> None:
        assert untagged_fences("text\n\n```\ncode\n```\n") == [3]

    def test_a_tagged_fence_is_clean(self) -> None:
        assert untagged_fences("```python\nx = 1\n```\n") == []

    def test_a_bare_tilde_fence_is_reported(self) -> None:
        assert untagged_fences("~~~\ncode\n~~~\n") == [1]

    def test_a_closing_fence_is_not_mistaken_for_an_opener(self) -> None:
        assert untagged_fences("```text\na\n```\n\n```text\nb\n```\n") == []

    def test_a_shorter_fence_inside_a_longer_one_is_content(self) -> None:
        text = "````markdown\n```\ninner\n```\n````\n"
        assert untagged_fences(text) == []

    def test_a_tilde_line_inside_a_backtick_block_does_not_close_it(self) -> None:
        assert untagged_fences("```text\n~~~\n```\n```\nx\n```\n") == [4]

    def test_an_indented_list_fence_is_checked_too(self) -> None:
        assert untagged_fences("- item\n\n   ```\n   x\n   ```\n") == [3]

    def test_a_closing_fence_with_an_info_string_does_not_close(self) -> None:
        assert untagged_fences("```text\n```python\n```\nprose\n") == []


class TestIndexedFiles:
    def test_root_markdown_is_included_even_when_folders_is_set(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.md")
        _write(tmp_path, "src/notes.md")
        assert _relative(tmp_path, _BASE) == ["README.md"]

    def test_folders_narrow_the_rest(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/a.md")
        _write(tmp_path, "examples/b.md")
        assert _relative(tmp_path, _BASE) == ["documentation/a.md"]

    def test_an_excluded_folder_is_skipped_but_a_prefix_sibling_is_not(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "documentation/es/a.md")
        _write(tmp_path, "documentation/espresso/b.md")
        assert _relative(tmp_path, _BASE) == ["documentation/espresso/b.md"]

    def test_excluded_file_names_are_skipped_at_any_depth(self, tmp_path: Path) -> None:
        _write(tmp_path, "LEAME.md")
        _write(tmp_path, "documentation/LEAME.md")
        assert _relative(tmp_path, _BASE) == []

    def test_only_documentation_file_types_are_indexed(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/a.txt")
        _write(tmp_path, "documentation/b.yaml")
        _write(tmp_path, "documentation/c.py")
        assert _relative(tmp_path, _BASE) == ["documentation/a.txt"]

    def test_paths_the_public_snapshot_strips_are_not_indexed(self, tmp_path: Path) -> None:
        _write(tmp_path, ".publishignore", "# c\n*-plan.md\ndrafts\nNOTES-private.md\n")
        _write(tmp_path, "documentation/next-run-plan.md")
        _write(tmp_path, "documentation/real.md")
        _write(tmp_path, "NOTES-private.md")
        assert _relative(tmp_path, _BASE) == ["documentation/real.md"]


class TestFenceCheck:
    def test_an_untagged_fence_names_file_and_line(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/a.md", "x\n```\ny\n```\n")
        (problem,) = check_fences(tmp_path, _BASE)
        assert problem.startswith("documentation/a.md:2:")

    def test_an_untagged_fence_in_an_excluded_mirror_is_ignored(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/es/a.md", "```\ny\n```\n")
        assert check_fences(tmp_path, _BASE) == []


def _git_repo_with_tags(root: Path, tags: list[str]) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)  # nosec B603, B607
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(  # nosec B603 - fixed argv
        [*git, "commit", "-q", "--allow-empty", "-m", "c"], cwd=root, check=True
    )
    for tag in tags:
        subprocess.run([*git, "tag", "-a", tag, "-m", tag], cwd=root, check=True)  # nosec B603


def _write_version(root: Path, version: str) -> None:
    (root / "pyproject.toml").write_text(f'[project]\nname = "x"\nversion = "{version}"\n')


class TestPreviousVersions:
    def test_the_builds_own_version_is_listed_before_its_tag_exists(self, tmp_path: Path) -> None:
        # B-82: the release tag is minted on a tree that must already list it.
        _git_repo_with_tags(tmp_path, ["v0.1.0", "v0.2.0"])
        _write_version(tmp_path, "0.3.0")
        config = {"previousVersions": [{"tag": "v0.3.0"}, {"tag": "v0.2.0"}, {"tag": "v0.1.0"}]}
        assert check_previous_versions(tmp_path, config) == []

    def test_a_file_that_omits_the_builds_own_version_is_reported(self, tmp_path: Path) -> None:
        _git_repo_with_tags(tmp_path, ["v0.1.0", "v0.2.0"])
        _write_version(tmp_path, "0.3.0")
        config = {"previousVersions": [{"tag": "v0.2.0"}, {"tag": "v0.1.0"}]}
        (problem,) = check_previous_versions(tmp_path, config)
        assert "v0.3.0" in problem

    def test_the_release_tags_own_checkout_is_clean_when_the_file_lists_it(
        self, tmp_path: Path
    ) -> None:
        _git_repo_with_tags(tmp_path, ["v0.1.0", "v0.2.0"])
        _write_version(tmp_path, "0.2.0")
        config = {"previousVersions": [{"tag": "v0.2.0"}, {"tag": "v0.1.0"}]}
        assert check_previous_versions(tmp_path, config) == []

    def test_a_tagged_checkout_without_the_version_source_is_a_misconfigured_gate_not_a_skip(
        self, tmp_path: Path
    ) -> None:
        _git_repo_with_tags(tmp_path, ["v0.1.0"])
        with pytest.raises(ValueError, match="version"):
            check_previous_versions(tmp_path, {"previousVersions": [{"tag": "v0.1.0"}]})

    def test_the_list_equal_to_the_tags_newest_first_is_clean(self, tmp_path: Path) -> None:
        _git_repo_with_tags(tmp_path, ["v0.9.0", "v0.10.0"])
        _write_version(tmp_path, "0.10.0")
        config = {"previousVersions": [{"tag": "v0.10.0"}, {"tag": "v0.9.0"}]}
        assert check_previous_versions(tmp_path, config) == []

    def test_a_release_that_forgot_the_file_fails(self, tmp_path: Path) -> None:
        _git_repo_with_tags(tmp_path, ["v1.0.0", "v1.1.0"])
        _write_version(tmp_path, "1.1.0")
        (problem,) = check_previous_versions(tmp_path, {"previousVersions": [{"tag": "v1.0.0"}]})
        assert "v1.1.0" in problem

    def test_a_missing_key_with_no_tags_is_clean(self, tmp_path: Path) -> None:
        _git_repo_with_tags(tmp_path, [])
        assert check_previous_versions(tmp_path, {}) == []

    def test_a_non_release_tag_is_not_a_version(self, tmp_path: Path) -> None:
        _git_repo_with_tags(tmp_path, ["v1.0.0", "nightly"])
        _write_version(tmp_path, "1.0.0")
        assert check_previous_versions(tmp_path, {"previousVersions": [{"tag": "v1.0.0"}]}) == []

    def test_a_tree_that_is_not_a_git_checkout_has_no_tags_to_compare(self, tmp_path: Path) -> None:
        # The public snapshot is verified as a plain tree, staged without a .git directory; the
        # rule has nothing to derive from there and must not fail the gate (found by the 0.4.0
        # `--tag` verify, 2026-10-15).
        config = {"previousVersions": [{"tag": "v1.0.0"}]}
        assert check_previous_versions(tmp_path, config) == []


class TestSchema:
    @staticmethod
    def _root(tmp_path: Path) -> Path:
        _write(
            tmp_path,
            "config/context7/context7.schema.json",
            (REPO_ROOT / "config/context7/context7.schema.json").read_text(encoding="utf-8"),
        )
        return tmp_path

    def test_an_unknown_key_is_rejected(self, tmp_path: Path) -> None:
        problems = check_schema(self._root(tmp_path), {"branchVersions": []})
        assert problems and "branchVersions" in problems[0]

    def test_an_overlong_rule_is_rejected_naming_its_path(self, tmp_path: Path) -> None:
        (problem,) = check_schema(self._root(tmp_path), {"rules": ["x" * 256]})
        assert problem.startswith("context7.json: rules/0:")

    def test_a_one_word_description_is_rejected(self, tmp_path: Path) -> None:
        assert check_schema(self._root(tmp_path), {"description": "short"})

    def test_a_folder_path_in_excludefiles_is_rejected(self, tmp_path: Path) -> None:
        assert check_schema(self._root(tmp_path), {"excludeFiles": ["documentation/x.md"]})


def test_a_tree_without_the_config_is_reported(tmp_path: Path) -> None:
    assert check(tmp_path) == ["context7.json: missing at the repository root"]


class TestShippedConfig:
    def test_the_repository_is_index_ready(self) -> None:
        assert check(REPO_ROOT) == []

    def test_every_translated_mirror_folder_is_excluded(self) -> None:
        manifest = json.loads((REPO_ROOT / "documentation/i18n/manifest.json").read_text("utf-8"))
        excluded = load_config(REPO_ROOT)["excludeFolders"]
        for language in manifest["languages"]:
            assert language["directory"] in excluded
        assert "documentation/i18n" in excluded

    @pytest.mark.parametrize("key", ["url", "public_key"])
    def test_ownership_verification_is_left_to_the_owner(self, key: str) -> None:
        assert key not in load_config(REPO_ROOT)

    def test_every_localised_root_readme_is_excluded_by_name(self) -> None:
        manifest = json.loads((REPO_ROOT / "documentation/i18n/manifest.json").read_text("utf-8"))
        excluded = load_config(REPO_ROOT)["excludeFiles"]
        for language in manifest["languages"]:
            assert language["rootReadme"] in excluded
