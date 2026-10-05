# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""An opened skills carrier: the catalogue, every flavour's rendered page, and the coordinate that
stamps whatever gets installed from it.

INTENT: the installer's read side. A carrier is opened once, validated whole, and then behaves as a
value — every page is in memory, so nothing downstream holds a file handle or can see a carrier
change under it mid-install.

Three ways in, all local, none of them a network call: an unpacked directory, a built wheel, or an
installed distribution resolved through :mod:`importlib.metadata`. That last one is the analogue of
the Java port's classloader lookup: it reads an installed distribution's own files WITHOUT importing
it, which is what lets this library read the copy the runtime bundles while never importing the
runtime.

**@llmNote** The preference order matters and is the ruled one: the ``narrativetrace-skills``
distribution the PROJECT resolves comes first, so the installed pages are at the project's own
version; the copy the core distribution bundles is the offline fallback; and an explicit path
overrides both.

**@llmNote** A carrier whose catalogue is malformed, whose catalogue lists a page the carrier does
not have, or whose name cannot produce a coordinate is REFUSED here, with a message naming the
entry. That is deliberate: validation happens before any plan exists, so a broken carrier can never
half-install.

**@sideEffects** Reads the given path, or an installed distribution's metadata and files, once at
open time. Never writes, never resolves anything over a network.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import metadata as importlib_metadata
from pathlib import Path
from types import MappingProxyType
from typing import Final
from urllib.parse import unquote, urlparse

from narrativetrace_tooling.init.catalogue import (
    SkillCatalogue,
    SkillEntry,
    SkillFlavour,
    read_catalogue,
)

CATALOGUE_FILE: Final = "catalogue.json"

CARRIER_ROOT: Final = "skills"
"""Where the payload lives inside the published carrier distribution."""

BUNDLED_ROOT: Final = "narrativetrace/_skills"
"""Where the byte-identical copy lives inside the core distribution."""

SKILLS_DISTRIBUTION: Final = "narrativetrace-skills"

CORE_DISTRIBUTION: Final = "narrativetrace"

UNKNOWN_VERSION: Final = "unknown"
"""The version part of a coordinate that names none — honest, and visibly stale."""

_COORDINATE_SEPARATOR: Final = "=="

_PREFERENCE: Final = ((SKILLS_DISTRIBUTION, CARRIER_ROOT), (CORE_DISTRIBUTION, BUNDLED_ROOT))

_ROOT_CANDIDATES: Final = ("", CARRIER_ROOT, BUNDLED_ROOT)

_ReadEntry = Callable[[str], str | None]


@dataclass(frozen=True, slots=True)
class Carrier:
    """A validated carrier, held as a value.

    :param coordinate: what every page installed from this carrier is stamped with — this runtime's
        own form, a PEP 440 pin (``narrativetrace-skills==1.2.3``)
    :param catalogue: the index, already validated
    :param pages: carrier-relative path -> the page's text, every page the catalogue lists
    """

    coordinate: str
    catalogue: SkillCatalogue
    pages: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pages", MappingProxyType(dict(self.pages)))
        assert _invariant(self), "a carrier must be complete the moment it exists"

    @property
    def skills(self) -> tuple[SkillEntry, ...]:
        """Every skill the carrier carries, in catalogue order."""
        return self.catalogue.skills

    def body(self, skill: SkillEntry, flavour: SkillFlavour) -> str:
        """The rendered page for one skill in one flavour, exactly as the carrier carries it.

        :raises ValueError: when the skill is not this carrier's
        """
        if skill is None:
            raise ValueError("a skill must be given")
        page = self.pages.get(skill.path_for(flavour))
        if page is None:
            raise ValueError(f"the carrier {self.coordinate} does not carry {skill.name}")
        return page


def _invariant(carrier: Carrier) -> bool:
    """Returns whether a carrier is complete: a two-part coordinate, and every listed page present.

    A carrier that failed this could half-install a project. Constructor guards make it true for
    every live instance; tests re-check it around each case that opens one.
    """
    parts = carrier.coordinate.split(_COORDINATE_SEPARATOR)
    return (
        len(parts) == 2
        and all(parts)
        and all(
            skill.path_for(flavour) in carrier.pages
            for skill in carrier.catalogue.skills
            for flavour in SkillFlavour
        )
    )


def open_carrier(source: Path) -> Carrier:
    """Opens a carrier from an unpacked directory or from a built wheel.

    A directory may be the carrier root itself, or a distribution root in either layout the family
    ships. The coordinate comes from the file or directory's own name.

    :raises ValueError: when the path does not exist, carries no catalogue, carries a catalogue that
        does not describe what is there, or has a name no coordinate can be read out of
    """
    if source is None:
        raise ValueError("a carrier path must be given")
    if not source.exists():
        raise ValueError(f"no carrier at {source}")
    return _open_directory(source) if source.is_dir() else _open_archive(source)


def carrier_from_distribution(distribution: str, root: str) -> Carrier | None:
    """Opens the carrier an INSTALLED distribution carries, or ``None`` when it carries none.

    ``None`` means "nothing here", never "something is wrong": a distribution that is not installed,
    or one installed without the payload (an older release, or an editable install of a data-only
    distribution), is a reason to try the next candidate. A carrier that IS there and is broken
    still raises — a refusal a person can act on beats a silent fallback to a different carrier.

    :param distribution: the distribution name, e.g. ``narrativetrace-skills``
    :param root: the payload's path inside it, e.g. :data:`CARRIER_ROOT`
    """
    try:
        installed = importlib_metadata.distribution(distribution)
    except importlib_metadata.PackageNotFoundError:
        return None
    found = _first_with_catalogue(
        _directory_source(candidate) for candidate in _payload_candidates(installed, root)
    )
    if found is None:
        return None
    return _read(_coordinate(distribution, installed.version), *found)


def resolve_carrier(from_path: Path | None = None) -> Carrier:
    """The carrier an install should use, in the ruled preference order.

    ``from_path`` first, then the ``narrativetrace-skills`` distribution the project resolves, then
    the copy the core distribution bundles. No branch reaches a network.

    :raises ValueError: when nothing resolves, naming both distributions it looked in
    """
    if from_path is not None:
        return open_carrier(from_path)
    for distribution, root in _PREFERENCE:
        found = carrier_from_distribution(distribution, root)
        if found is not None:
            return found
    looked_in = ", ".join(distribution for distribution, _ in _PREFERENCE)
    raise ValueError(
        f"no skills carrier: none of {looked_in} is installed with one — install"
        f" {SKILLS_DISTRIBUTION}, or pass a path to an unpacked carrier or a built wheel"
    )


# --- opening ------------------------------------------------------------------------------------


def _first_with_catalogue(sources: Iterable[_ReadEntry]) -> tuple[_ReadEntry, str] | None:
    """The first source that holds a catalogue, with the catalogue's text, or ``None``.

    Finding the payload root and reading the catalogue are the SAME question, asked once: a caller
    that located the root by looking for ``catalogue.json`` and then read it again would leave an
    unreachable "carries no catalogue" branch behind, which is a branch no test can honestly cover.
    """
    for read_entry in sources:
        text = read_entry(CATALOGUE_FILE)
        if text is not None:
            return read_entry, text
    return None


def _open_directory(directory: Path) -> Carrier:
    coordinate = _coordinate_of_name(directory.name)
    found = _first_with_catalogue(
        _directory_source(directory / relative if relative else directory)
        for relative in _ROOT_CANDIDATES
    )
    if found is None:
        raise ValueError(f"the carrier {coordinate} carries no {CATALOGUE_FILE}")
    return _read(coordinate, *found)


def _open_archive(archive_path: Path) -> Carrier:
    coordinate = _coordinate_of_wheel_name(archive_path.name)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            found = _first_with_catalogue(
                _archive_source(archive, names, relative) for relative in _ROOT_CANDIDATES
            )
            if found is None:
                raise ValueError(f"the carrier {coordinate} carries no {CATALOGUE_FILE}")
            return _read(coordinate, *found)
    except zipfile.BadZipFile as error:
        raise ValueError(f"cannot read the carrier archive {archive_path}: {error}") from error


def _archive_entry(root: str, relative: str) -> str:
    return f"{root}/{relative}" if root else relative


def _archive_source(archive: zipfile.ZipFile, names: set[str], root: str) -> _ReadEntry:
    def read(relative: str) -> str | None:
        entry = _archive_entry(root, relative)
        if entry not in names:
            return None
        return _decoded(archive.read(entry), f"{archive.filename}!{entry}")

    return read


def _directory_source(root: Path) -> _ReadEntry:
    def read(relative: str) -> str | None:
        file = root / relative
        if not file.is_file():
            return None
        try:
            return _decoded(file.read_bytes(), str(file))
        except OSError as error:
            raise ValueError(f"cannot read the carrier file {file}: {error}") from error

    return read


def _decoded(raw: bytes, where: str) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"cannot read the carrier file {where}: not UTF-8 ({error})") from error


def _read(coordinate: str, read_entry: _ReadEntry, catalogue_text: str) -> Carrier:
    """Validates the whole carrier, then freezes it: every listed page is read here or nowhere.

    The catalogue arrives already read, from :func:`_first_with_catalogue` — that is what located
    the payload root in the first place.
    """
    catalogue = _read_catalogue(coordinate, catalogue_text)
    pages: dict[str, str] = {}
    for skill in catalogue.skills:
        for flavour in SkillFlavour:
            path = skill.path_for(flavour)
            page = read_entry(path)
            if page is None:
                raise ValueError(
                    f"the carrier {coordinate} lists {skill.name} at {path},"
                    " which it does not carry"
                )
            pages[path] = page
    return Carrier(coordinate, catalogue, pages)


def _read_catalogue(coordinate: str, text: str) -> SkillCatalogue:
    try:
        return read_catalogue(text)
    except ValueError as error:
        raise ValueError(
            f"the carrier {coordinate}'s {CATALOGUE_FILE} is unusable: {error}"
        ) from error


# --- where an installed distribution keeps its payload --------------------------------------------


def _payload_candidates(installed: importlib_metadata.Distribution, root: str) -> tuple[Path, ...]:
    """Every place this distribution's payload could be, most normal first.

    An ordinary install unpacks the payload beside the importable packages, which
    ``locate_file`` resolves. An EDITABLE install leaves it in the project directory instead, named
    by ``direct_url.json`` — with or without this family's ``src/`` layout in between.
    """
    candidates = [Path(str(installed.locate_file(root)))]
    project = _editable_project(installed)
    if project is not None:
        candidates += [project / root, project / "src" / root]
    return tuple(candidates)


def _editable_project(installed: importlib_metadata.Distribution) -> Path | None:
    """The project directory an editable install points back at, or ``None``."""
    recorded = installed.read_text("direct_url.json")
    if recorded is None:
        return None
    try:
        url = json.loads(recorded).get("url")
    except ValueError:
        return None
    parsed = urlparse(url) if isinstance(url, str) else None
    if parsed is None or parsed.scheme != "file":
        return None
    return Path(_local_path(unquote(parsed.path)))


def _local_path(path: str) -> str:
    """A ``file://`` URL's path as this platform reads it: Windows drives arrive as ``/C:/...``."""
    return path[1:] if len(path) > 2 and path[0] == "/" and path[2] == ":" else path


# --- coordinates ---------------------------------------------------------------------------------


def _coordinate(distribution: str, version: str) -> str:
    """The coordinate for one distribution and version, validated.

    Validated rather than trusted: this string is STAMPED into every page the carrier installs and
    read back by the doctor, so a part carrying the separator, whitespace or a path segment is
    refused before any page is written.
    """
    for part in (distribution, version):
        if not _is_coordinate_part(part):
            raise ValueError(
                f'a carrier is stamped with its own coordinate, and "{distribution}-{version}" does'
                f" not name one — a coordinate reads <distribution>{_COORDINATE_SEPARATOR}<version>"
            )
    return f"{_normalised(distribution)}{_COORDINATE_SEPARATOR}{version}"


def _is_coordinate_part(part: str) -> bool:
    forbidden = (_COORDINATE_SEPARATOR, "=", "/", "\\")
    return (
        bool(part.strip())
        and part == part.strip()
        and not any(token in part for token in forbidden)
        and part not in ("..", ".")
        and not any(character.isspace() for character in part)
    )


def _normalised(distribution: str) -> str:
    """A distribution name as a wheel writes it back: underscores are hyphens (PEP 503/427)."""
    return distribution.replace("_", "-")


def _coordinate_of_name(name: str) -> str:
    """The coordinate an unpacked directory's own name yields.

    The version starts at the first ``-`` followed by a digit, so ``narrativetrace_skills-1.2.3``
    reads as a name and a version while ``narrativetrace_skills`` reads as a name with no version at
    all — honest, and visibly stale, where a guess would be silently wrong.
    """
    dash = _version_dash(name)
    return (
        _coordinate(name, UNKNOWN_VERSION)
        if dash < 0
        else _coordinate(name[:dash], name[dash + 1 :])
    )


def _coordinate_of_wheel_name(file_name: str) -> str:
    """The coordinate a wheel's file name yields: ``<name>-<version>-<tags…>.whl`` (PEP 427)."""
    stem = file_name[: -len(".whl")] if file_name.endswith(".whl") else file_name
    parts = stem.split("-")
    if len(parts) < 2:
        return _coordinate(stem, UNKNOWN_VERSION)
    return _coordinate(parts[0], parts[1])


def _version_dash(name: str) -> int:
    """The index of the ``-`` that starts a version, i.e. one followed by a digit."""
    return next(
        (
            index
            for index in range(len(name) - 1)
            if name[index] == "-" and name[index + 1].isdigit()
        ),
        -1,
    )
