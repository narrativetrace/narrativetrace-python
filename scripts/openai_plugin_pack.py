# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Builds and checks the OpenAI plugin directory's release ZIP.

The package is a root ``plugin.json`` (rendered WITH the release version), the drift-pinned
``.agents/skills`` pages under ``skills/``, and the two listing icons under ``assets/``. It is
built from an annotated ``v*`` tag by hand, never per commit and never by a release workflow, and
the ZIP is a build output that is never committed. Every upload to the directory is its own
review, so nothing here uploads anything.

The entry list is DERIVED from the catalogue (``openai_package_entries``) and ASSERTED against the
built archive (release rule 5: a file set is derived from the build, never a glob), together with
the version (semantic ``X.Y.Z``, the root ``pyproject.toml``'s own), every ``./`` path the manifest
names, each icon's shape and size, and the entries a skills-only plugin must not carry.

``--build DIR`` writes ``DIR/narrativetrace-python-openai-plugin-<version>.zip`` (reproducible:
sorted entries, fixed timestamps); ``--check`` builds into a temporary directory and verifies the
result, which is what ``poe openai-plugin-check`` runs inside ``poe check``.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

from narrativetrace_skills import (
    OPENAI_DIRECTORY,
    SKILLS,
    openai_package_entries,
    render_openai_plugin_json,
)
from narrativetrace_skills.render.png_dimensions import png_dimensions

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.skills_render import _codex_skill_md_path, _openai_plugin_dir
from scripts.translation_check import REPO_ROOT

SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_MIN_ICON_PX = 48
_MAX_ICON_BYTES = 5 * 1024 * 1024
_FIXED_TIME = (1980, 1, 1, 0, 0, 0)  # the ZIP format's earliest representable timestamp
_ASSET_NAMES = ("logo.png", "composer-icon.png")
_USAGE = "Usage: python scripts/openai_plugin_pack.py --build DIR | --check"


def release_version(root: Path = REPO_ROOT) -> str:
    """The build's own version: the root ``pyproject.toml``'s ``project.version``."""
    with (root / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def package_files(root: Path, version: str) -> dict[str, bytes]:
    """Every ZIP entry's bytes, keyed by entry path: the manifest rendered with ``version``, the
    committed ``.agents/skills`` pages, the committed icons."""
    files = {"plugin.json": render_openai_plugin_json(OPENAI_DIRECTORY, version).encode()}
    for skill in SKILLS:
        page = _codex_skill_md_path(skill.canonical_name, root)
        files[f"skills/{skill.canonical_name}/SKILL.md"] = page.read_bytes()
    for name in _ASSET_NAMES:
        files[f"assets/{name}"] = (_openai_plugin_dir(root) / "assets" / name).read_bytes()
    return files


def build_zip(root: Path, version: str, out_dir: Path) -> Path:
    """Writes the release ZIP into ``out_dir`` and asserts it against the derived layout. A
    version that is not semantic ``X.Y.Z`` raises ``ValueError`` before anything is written."""
    if not SEMVER.fullmatch(version):
        raise ValueError(_not_semantic(version))
    files = package_files(root, version)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{OPENAI_DIRECTORY.base.name}-openai-plugin-{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, _FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, files[name])
    problems = violations(target, openai_package_entries(SKILLS), version)
    if problems:
        raise RuntimeError(f"{target} failed its own checks:\n" + "\n".join(problems))
    return target


def violations(zip_path: Path, expected_entries: list[str], expected_version: str) -> list[str]:
    """Every way the archive at ``zip_path`` departs from the package contract; empty when it
    holds."""
    problems: list[str] = []
    with zipfile.ZipFile(zip_path) as archive:
        names = sorted(n for n in archive.namelist() if not n.endswith("/"))
        _check_entry_set(sorted(expected_entries), names, problems)
        problems.extend(f"forbidden entry present: {n}" for n in names if _is_forbidden(n))
        manifest = _read_manifest(archive, problems)
        if manifest is not None:
            _check_version(manifest, expected_version, problems)
            paths = _relative_paths(manifest)
            _check_paths(paths, set(names), problems)
            _check_icons(archive, paths, problems)
    return problems


def _not_semantic(version: str) -> str:
    return f"version '{version}' is not semantic (X.Y.Z, no -SNAPSHOT)"


def _check_entry_set(expected: list[str], actual: list[str], problems: list[str]) -> None:
    if expected != actual:
        problems.append(f"entries do not match the layout — expected {expected} but found {actual}")


def _is_forbidden(name: str) -> bool:
    return (
        name.startswith("hooks/")
        or name == "mcp.json"
        or name.endswith(".app.json")
        or name.endswith(".class")
    )


def _read_manifest(archive: zipfile.ZipFile, problems: list[str]) -> dict[str, object] | None:
    if "plugin.json" not in archive.namelist():
        problems.append("plugin.json is missing from the zip")
        return None
    try:
        manifest = json.loads(archive.read("plugin.json"))
    except ValueError:
        problems.append("plugin.json is not valid JSON")
        return None
    if not isinstance(manifest, dict):
        problems.append("plugin.json is not a JSON object")
        return None
    return manifest


def _check_version(manifest: dict[str, object], expected: str, problems: list[str]) -> None:
    if not SEMVER.fullmatch(expected):
        problems.append(_not_semantic(expected))
    if "version" not in manifest:
        problems.append('plugin.json carries no "version" key')
    elif manifest["version"] != expected:
        problems.append(f"plugin.json version '{manifest['version']}' does not equal {expected}")


def _relative_paths(node: object) -> list[str]:
    """Every string value in the manifest that starts with ``./``, in document order."""
    if isinstance(node, str):
        return [node.removeprefix("./")] if node.startswith("./") else []
    children = node.values() if isinstance(node, dict) else node if isinstance(node, list) else []
    return [path for child in children for path in _relative_paths(child)]


def _check_paths(paths: list[str], names: set[str], problems: list[str]) -> None:
    problems.extend(
        f"manifest path './{path}' resolves to no packaged entry"
        for path in paths
        if path not in names
    )


def _check_icons(archive: zipfile.ZipFile, paths: list[str], problems: list[str]) -> None:
    present = set(archive.namelist())
    for path in paths:
        if path.endswith(".png") and path in present:
            _check_icon(path, archive.read(path), problems)


def _check_icon(path: str, data: bytes, problems: list[str]) -> None:
    if len(data) > _MAX_ICON_BYTES:
        problems.append(f"{path} is larger than 5 MiB")
        return
    try:
        width, height = png_dimensions(data)
    except ValueError as error:
        problems.append(f"{path} is {error}")
        return
    if width != height:
        problems.append(f"{path} is not square ({width}x{height})")
    elif width < _MIN_ICON_PX:
        problems.append(f"{path} is smaller than {_MIN_ICON_PX}px ({width}px)")


def _check(root: Path) -> int:
    version = release_version(root)
    with tempfile.TemporaryDirectory() as scratch:
        archive = build_zip(root, version, Path(scratch))
        with zipfile.ZipFile(archive) as built:
            entries = built.namelist()
    print(f"openai_plugin_pack: ok — {len(entries)} entries match the catalogue layout")
    return 0


def _build(root: Path, out_dir: Path) -> int:
    archive = build_zip(root, release_version(root), out_dir)
    print(f"wrote {archive}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--check"]:
        return _check(REPO_ROOT)
    if len(args) == 2 and args[0] == "--build":
        return _build(REPO_ROOT, Path(args[1]))
    print(_USAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
