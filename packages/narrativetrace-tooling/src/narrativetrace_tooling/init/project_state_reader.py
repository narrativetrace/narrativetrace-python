# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Builds a :class:`~narrativetrace_tooling.init.project_state.ProjectState` from a real project
directory: read-only, zero network, a bounded listing of each install root.

INTENT: the installer's single reader. Every file the planners reason about is read here, once, so
nothing downstream touches the project until the executor writes.

**@llmNote** Unlike the doctor's snapshot, this reader is NOT best-effort. A file that exists but
cannot be read is a hard failure, because "unreadable" and "absent" lead to opposite plans — absent
means create, and creating over a file we could not read would destroy it.

**@llmNote** The output directory is read as TEXT (``narrativetrace.toml``, then
``[tool.narrativetrace]`` in ``pyproject.toml``), never through the runtime's own resolver: this
library never imports the runtime. It is one detected fact for one line of prose in the managed
section, not the configuration the runtime resolves, and the default is the runtime's own.

**@sideEffects** Reads. Never writes, never creates a directory.
"""

from __future__ import annotations

import os
import stat
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Final

from narrativetrace_tooling.init import marked_block, provenance
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.project_state import (
    DEFAULT_OUTPUT_DIRECTORY,
    PAGE,
    InstalledSkill,
    Presence,
    ProjectState,
)

RULE_FILES: Final = (".cursorrules", ".github/copilot-instructions.md")
"""Vendor rule files whose existing managed block is kept up to date, never created."""

_STANDALONE_CONFIG: Final = "narrativetrace.toml"

_PYPROJECT: Final = "pyproject.toml"

_LOCK_FILE: Final = "uv.lock"

_OUTPUT_DIRECTORY_KEY: Final = "output_dir"

DEFAULT_MAX_SKILL_DIRECTORIES: Final = 200
"""A listing cap, so a pathological tree degrades to a partial read rather than to a hang."""


def read_project_state(
    project_directory: Path, max_skill_directories: int = DEFAULT_MAX_SKILL_DIRECTORIES
) -> ProjectState:
    """Reads a project directory.

    :raises TypeError: when no directory is given
    :raises ValueError: when the path is not a directory, or a file that exists cannot be read
    """
    if not isinstance(project_directory, Path):
        raise TypeError("a project directory must be given")
    if not project_directory.is_dir():
        raise ValueError(f"{project_directory} is not a directory")
    linked_roots = _linked_install_roots(project_directory)
    return ProjectState(
        agents_md=_text_of(project_directory / "AGENTS.md"),
        claude_md=_text_of(project_directory / "CLAUDE.md"),
        claude_directory=(project_directory / ".claude").is_dir(),
        installed_skills=_installed_skills(project_directory, linked_roots, max_skill_directories),
        linked_install_roots=linked_roots,
        marked_rule_files=_marked_rule_files(project_directory),
        output_directory=_output_directory(project_directory),
        uv_project=_is_uv_project(project_directory),
    )


def _linked_install_roots(project_directory: Path) -> dict[SkillFlavour, str]:
    """A flavour whose whole install root is a link, reported once — rule 20. Nothing may be written
    into that flavour at all, because every page of it would land wherever the link goes."""
    linked: dict[SkillFlavour, str] = {}
    for flavour in SkillFlavour:
        target = _link_target(project_directory / flavour.install_root)
        if target is not None:
            linked[flavour] = target
    return linked


def _installed_skills(
    project_directory: Path,
    linked_roots: Mapping[SkillFlavour, str],
    max_skill_directories: int,
) -> tuple[InstalledSkill, ...]:
    return tuple(
        _installed_skill(project_directory, flavour, child)
        for flavour in SkillFlavour
        if flavour not in linked_roots
        for child in _children(project_directory / flavour.install_root, max_skill_directories)
    )


def _children(root: Path, limit: int) -> list[Path]:
    if not _is_directory_not_a_link(root):
        return []
    try:
        entries = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError as error:
        raise ValueError(f"cannot list {root}: {error}") from error
    return entries[:limit]


def _installed_skill(
    project_directory: Path, flavour: SkillFlavour, directory: Path
) -> InstalledSkill:
    """What sits at one skill's path, WITHOUT following a link on the way.

    A link is reported as one, never resolved into "a directory of ours": writing through it would
    land in whatever it points at, and after ``npx skills add`` that is the other flavour's page.
    """
    name = directory.name
    to_directory = _link_target(directory)
    if to_directory is not None:
        return _linked(project_directory, flavour, name, Presence.LINKED_DIRECTORY, to_directory)
    if not _is_directory_not_a_link(directory):
        return InstalledSkill(flavour, name, Presence.NOT_A_DIRECTORY)
    to_page = _link_target(directory / PAGE)
    if to_page is not None:
        return _linked(project_directory, flavour, name, Presence.LINKED_PAGE, to_page)
    return _page_of(flavour, name, directory / PAGE)


def _page_of(flavour: SkillFlavour, name: str, page_file: Path) -> InstalledSkill:
    """A real directory: ours when its page carries the provenance line, somebody else's
    otherwise."""
    page = _text_of(page_file) or ""
    coordinate = provenance.coordinate_in(page)
    if coordinate is None:
        return InstalledSkill(flavour, name, Presence.FOREIGN, body=page)
    return InstalledSkill(flavour, name, Presence.OURS, coordinate, page)


def _linked(
    project_directory: Path,
    flavour: SkillFlavour,
    name: str,
    presence: Presence,
    target: str,
) -> InstalledSkill:
    """A skill behind a link: what the link says, and the page it reaches — read only when the link
    really resolves INSIDE this project, because nothing out of it is ours to stamp or to remove."""
    page = project_directory / flavour.install_root / name / PAGE
    body = (_text_of(page) or "") if _inside_project(project_directory, page) else ""
    return InstalledSkill(flavour, name, presence, body=body, link=target)


def _inside_project(project_directory: Path, path: Path) -> bool:
    """Whether a path REALLY resolves inside the project.

    Resolved STRICTLY: a link that resolves to nothing — dangling, or a chain the filesystem will
    not follow — answers no, which is the same answer a link out of the project gets. The installer
    treats both as reaching no page at all. A non-strict resolve would answer yes for a dangling
    link whose text happens to point inside, and the page read would then be none anyway.
    """
    try:
        return path.resolve(strict=True).is_relative_to(project_directory.resolve(strict=True))
    except OSError:
        return False


def _link_target(path: Path) -> str | None:
    """What a symbolic link points at, or ``None`` when the path is not one."""
    if not path.is_symlink():
        return None
    try:
        return os.readlink(path)
    except OSError as error:
        raise ValueError(f"cannot read the symbolic link {path}: {error}") from error


def _is_directory_not_a_link(path: Path) -> bool:
    """Whether a path is a real directory, never one reached THROUGH a symbolic link.

    **@llmNote** ``Path.is_dir()`` follows links, and ``follow_symlinks=False`` only arrived in 3.13
    while this library supports 3.12 — so the test is spelled with ``lstat``. This is the one thing
    the cross-port note calls not optional: the Java port's own first version used the
    follow-by-default test here, and a linked skill directory then read back as a real one.
    """
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _marked_rule_files(project_directory: Path) -> dict[str, str]:
    """A rule file is read only when it already carries our markers — including BROKEN ones, so the
    planner can refuse them rather than silently skipping a file it cannot edit safely."""
    found: dict[str, str] = {}
    for relative in RULE_FILES:
        text = _text_of(project_directory / relative)
        if text is not None and _carries_markers(text):
            found[relative] = text
    return found


def _carries_markers(text: str) -> bool:
    scan = marked_block.scan(text)
    return bool(scan.regions) or bool(scan.problems)


def _output_directory(project_directory: Path) -> str:
    """The configured output directory, or the runtime's own default."""
    for table in _config_tables(project_directory):
        value = table.get(_OUTPUT_DIRECTORY_KEY)
        if isinstance(value, str) and value.strip():
            return value
    return DEFAULT_OUTPUT_DIRECTORY


def _config_tables(project_directory: Path) -> Iterable[dict[str, Any]]:
    """The configuration tables that can name an output directory, in the runtime's own order."""
    standalone = _toml_of(project_directory / _STANDALONE_CONFIG)
    if standalone is not None:
        yield standalone
    document = _toml_of(project_directory / _PYPROJECT)
    table = (document or {}).get("tool", {}).get("narrativetrace")
    if isinstance(table, dict):
        yield table


def _is_uv_project(project_directory: Path) -> bool:
    """Whether the managed section should spell commands ``uv run narrativetrace …``.

    A lock file is the certain signal; a ``pyproject.toml`` is the ordinary one, and this
    repository's own documentation spells every command that way for such a project.
    """
    return (project_directory / _LOCK_FILE).is_file() or (project_directory / _PYPROJECT).is_file()


def _toml_of(file: Path) -> dict[str, Any] | None:
    """A parsed TOML document, or ``None`` when absent or malformed.

    Malformed degrades to ``None`` rather than failing the run, matching the runtime's own reader: a
    project with a broken ``pyproject.toml`` has a problem the installer is not the one to report,
    and the only thing read out of it here is one directory name.
    """
    if not file.is_file():
        return None
    try:
        with file.open("rb") as handle:
            loaded: dict[str, Any] = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return loaded


def _text_of(file: Path) -> str | None:
    """The file's text, or ``None`` when it does not exist. An unreadable file is a failure, not
    ``None``.

    Decoded from BYTES rather than read as text: ``read_text`` applies universal newlines, so it
    would hand back ``\\n`` for a file that really holds ``\\r\\n`` — and every edit the installer
    plans is expressed against the file's exact bytes, line endings included.
    """
    if not file.is_file():
        return None
    try:
        return file.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"cannot read {file}: {error}") from error
