# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Workspace-derived package list for `poe verify-publication` (`scripts/verify_publication_
packages.py`).

`derive_workspace_packages`'s real invocation against this repository's own workspace is
exercised for real by `poe verify-publication --dry-run` (and the live run against pypi.org);
these tests drive the derivation against synthetic `tmp_path` workspaces so a ninth/tenth member,
a missing manifest, or a "Private :: Do Not Upload" classifier are each covered without needing
to edit this repository's real `packages/` tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.verify_publication_packages import derive_workspace_packages, latest_git_tag_version


def _write_root(repo_root: Path, members: str = '["packages/*"]') -> None:
    (repo_root / "pyproject.toml").write_text(
        f"[tool.uv.workspace]\nmembers = {members}\n", encoding="utf-8"
    )


def _write_package(
    repo_root: Path, directory: str, name: str, version: str, classifiers: list[str] | None = None
) -> None:
    pkg_dir = repo_root / directory
    pkg_dir.mkdir(parents=True, exist_ok=True)
    classifiers_toml = ", ".join(f'"{c}"' for c in (classifiers or []))
    (pkg_dir / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "{version}"\nclassifiers = [{classifiers_toml}]\n',
        encoding="utf-8",
    )


class TestDeriveWorkspacePackages:
    def test_finds_every_member_directorys_own_manifest(self, tmp_path: Path) -> None:
        _write_root(tmp_path)
        _write_package(tmp_path, "packages/alpha", "alpha", "1.0.0")
        _write_package(tmp_path, "packages/beta", "beta", "2.0.0")

        packages = derive_workspace_packages(tmp_path)

        assert [p.name for p in packages] == ["alpha", "beta"]

    def test_sorts_by_name_not_discovery_order(self, tmp_path: Path) -> None:
        _write_root(tmp_path)
        _write_package(tmp_path, "packages/zeta", "zeta", "1.0.0")
        _write_package(tmp_path, "packages/alpha", "alpha", "1.0.0")

        packages = derive_workspace_packages(tmp_path)

        assert [p.name for p in packages] == ["alpha", "zeta"]

    def test_a_package_with_no_special_classifier_is_publishable(self, tmp_path: Path) -> None:
        _write_root(tmp_path)
        _write_package(
            tmp_path, "packages/alpha", "alpha", "1.0.0", classifiers=["Typing :: Typed"]
        )

        (package,) = derive_workspace_packages(tmp_path)

        assert package.publish is True

    def test_the_private_do_not_upload_classifier_marks_a_package_unpublishable(
        self, tmp_path: Path
    ) -> None:
        _write_root(tmp_path)
        _write_package(
            tmp_path,
            "packages/security-tests",
            "security-tests",
            "1.0.0",
            classifiers=["Private :: Do Not Upload", "Typing :: Typed"],
        )

        (package,) = derive_workspace_packages(tmp_path)

        assert package.publish is False

    def test_skips_a_workspace_directory_with_no_pyprojecttoml(self, tmp_path: Path) -> None:
        _write_root(tmp_path)
        _write_package(tmp_path, "packages/alpha", "alpha", "1.0.0")
        (tmp_path / "packages" / "placeholder").mkdir(parents=True)

        packages = derive_workspace_packages(tmp_path)

        assert [p.name for p in packages] == ["alpha"]

    def test_a_missing_name_or_version_raises_rather_than_silently_dropping_the_package(
        self, tmp_path: Path
    ) -> None:
        _write_root(tmp_path)
        pkg_dir = tmp_path / "packages" / "broken"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "pyproject.toml").write_text('[project]\nname = "broken"\n', encoding="utf-8")

        with pytest.raises(ValueError, match=r"missing \[project\]\.name or \[project\]\.version"):
            derive_workspace_packages(tmp_path)

    def test_a_literal_non_glob_member_path_is_read_directly(self, tmp_path: Path) -> None:
        _write_root(tmp_path, members='["standalone"]')
        _write_package(tmp_path, "standalone", "standalone", "1.0.0")

        packages = derive_workspace_packages(tmp_path)

        assert [p.name for p in packages] == ["standalone"]

    def test_no_workspace_members_key_raises(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "root"\n', encoding="utf-8")

        with pytest.raises(ValueError, match=r"\[tool.uv.workspace\].members"):
            derive_workspace_packages(tmp_path)


class TestLatestGitTagVersion:
    def test_strips_the_v_prefix_from_the_first_matching_tag(self) -> None:
        assert latest_git_tag_version(["v0.2.0", "v0.1.0"]) == "0.2.0"

    def test_returns_none_given_no_tags(self) -> None:
        assert latest_git_tag_version([]) is None

    def test_ignores_a_tag_that_does_not_match_the_v_version_shape(self) -> None:
        assert latest_git_tag_version(["release-candidate", "v1.2.3"]) == "1.2.3"

    def test_returns_none_when_nothing_matches(self) -> None:
        assert latest_git_tag_version(["not-a-version-tag"]) is None
