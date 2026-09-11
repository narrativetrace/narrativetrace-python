# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Publishable-package derivation for `poe verify-publication` (`scripts/verify_publication.py`).

Mirrors `narrative-trace-ts/tools/verify-publication-packages.ts`: the package list is read
straight from the workspace's own manifests — `[tool.uv.workspace].members` in the root
`pyproject.toml`, expanded to real directories, then each directory's own `pyproject.toml` —
never hand-kept here a second time. A ninth workspace member (or a tenth) is picked up the
moment its own `pyproject.toml` exists; nothing needs updating in this file to notice it.

Each package is either **publishable** (expected present on PyPI at the release version) or
**must never publish** (`narrativetrace-security-tests`, tagged with the standard PyPI/twine
"Private :: Do Not Upload" classifier — see its own `pyproject.toml` comment). The split is the
`publish` field below, read from `classifiers`, not a second hand-kept exclusion list: the same
reasoning `verify-publication-registry.py`'s absence check exists for — a project excluded from
`publish.yml`'s build step by a typo'd name would otherwise never be checked for either presence
or absence.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

PRIVATE_DO_NOT_UPLOAD = "Private :: Do Not Upload"


@dataclass(frozen=True)
class WorkspacePackage:
    """One workspace member, as its own `pyproject.toml` declares it.

    `publish` is `True` for every package expected to reach PyPI on a normal release,
    `False` for the one that must never appear there (`narrativetrace-security-tests`).
    """

    name: str
    version: str
    directory: str  # relative to repo_root, e.g. "packages/narrativetrace"
    publish: bool


def _read_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _workspace_member_globs(repo_root: Path) -> list[str]:
    """The `[tool.uv.workspace].members` glob list from the root `pyproject.toml`."""
    root = _read_toml(repo_root / "pyproject.toml")
    tool = root.get("tool")
    workspace = tool.get("uv", {}).get("workspace", {}) if isinstance(tool, dict) else {}
    members = workspace.get("members") if isinstance(workspace, dict) else None
    if not isinstance(members, list) or not members:
        raise ValueError("pyproject.toml has no non-empty [tool.uv.workspace].members")
    return [str(member) for member in members]


def _expand_glob(repo_root: Path, glob: str) -> list[str]:
    """Directories one workspace glob names, relative to `repo_root`.

    Only the trailing-`/*` shape (every immediate subdirectory) and a bare literal directory are
    supported — the two shapes this repository's own workspace member list actually uses.
    """
    if not glob.endswith("/*"):
        return [glob] if (repo_root / glob).is_dir() else []
    base = glob[: -len("/*")]
    base_dir = repo_root / base
    if not base_dir.is_dir():
        return []
    return sorted(f"{base}/{entry.name}" for entry in base_dir.iterdir() if entry.is_dir())


def _read_package(repo_root: Path, directory: str) -> WorkspacePackage | None:
    manifest_path = repo_root / directory / "pyproject.toml"
    if not manifest_path.is_file():
        return None
    project = _read_toml(manifest_path).get("project")
    if not isinstance(project, dict):
        return None
    name = project.get("name")
    version = project.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise ValueError(f"{manifest_path} is missing [project].name or [project].version")
    classifiers = project.get("classifiers", [])
    must_not_publish = isinstance(classifiers, list) and PRIVATE_DO_NOT_UPLOAD in classifiers
    return WorkspacePackage(
        name=name, version=version, directory=directory, publish=not must_not_publish
    )


def derive_workspace_packages(repo_root: Path) -> list[WorkspacePackage]:
    """Every workspace member with its own `pyproject.toml`, derived from the workspace itself.

    Sorted by name for a stable, diffable report — never by discovery order, which depends on
    filesystem iteration order.
    """
    globs = _workspace_member_globs(repo_root)
    directories = [d for glob in globs for d in _expand_glob(repo_root, glob)]
    packages = [_read_package(repo_root, d) for d in directories]
    found = [p for p in packages if p is not None]
    return sorted(found, key=lambda p: p.name)


_VERSION_TAG = re.compile(r"^v(\d[\w.+-]*)$")


def latest_git_tag_version(tags: list[str]) -> str | None:
    """The newest `v<version>` tag's bare version, given `tags` already sorted newest-first.

    Pure — the caller (`verify_publication.py`) runs `git tag --list 'v*' --sort=-version:refname`
    and passes the lines in; kept here only so the parsing (strip the `v`, ignore anything that
    does not match the shape a release tag actually has) is unit-testable without a git process.
    """
    for tag in tags:
        match = _VERSION_TAG.match(tag.strip())
        if match:
            return match.group(1)
    return None
