# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What one detected platform's pointer file looks like in a project — the installer's own reading,
handed to the doctor so both agree on what "present" means.

INTENT: the doctor must not scan marker text itself
(:mod:`~narrativetrace_tooling.init.marked_block` is the one place that decides what counts as a
marker), so the installer's package turns a
:class:`~narrativetrace_tooling.init.project_state.ProjectState` into these five-field facts and
the doctor only judges them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.project_state import ProjectState
from narrativetrace_tooling.platforms.table import ROWS, PlatformRow


@unique
class Status(Enum):
    """What is at a pointer's path."""

    ABSENT = "absent"
    """Nothing is there."""

    LINKED = "linked"
    """The path, or a directory above it, is a symbolic link; nothing is read or written."""

    FOREIGN = "foreign"
    """A file is there, but it does not carry exactly one NarrativeTrace section."""

    SECTION = "section"
    """A file with exactly one NarrativeTrace section, stamped or not."""


@dataclass(frozen=True, slots=True)
class PointerReading:
    """One detected platform's pointer.

    :param platform_id: the platform-table row id
    :param platform_name: the platform as a reader names it
    :param path: the pointer file, project-relative
    :param status: what is at that path
    :param coordinate: the carrier coordinate on the section's opening marker; ``""`` unless the
        status is :attr:`Status.SECTION`, and ``""`` there too when the section carries no stamp
    """

    platform_id: str
    platform_name: str
    path: str
    status: Status
    coordinate: str

    def __post_init__(self) -> None:
        if self.coordinate and self.status is not Status.SECTION:
            raise ValueError("only a section carries a coordinate")


def read_all(state: ProjectState) -> tuple[PointerReading, ...]:
    """One reading per DETECTED platform whose row has a pointer, in platform-table order. A
    platform the project is not on has nothing to be missing, and a row with no pointer has nothing
    to read.

    :raises TypeError: when no snapshot is given
    """
    if not isinstance(state, ProjectState):
        raise TypeError("reading pointers needs a project state")
    return tuple(
        _read(row, state) for row in ROWS if row.pointer.path and row.id in state.detected_platforms
    )


def _read(row: PlatformRow, state: ProjectState) -> PointerReading:
    path = row.pointer.path

    def reading(status: Status, coordinate: str = "") -> PointerReading:
        return PointerReading(row.id, row.name, path, status, coordinate)

    if path in state.pointers_behind_links:
        return reading(Status.LINKED)
    text = state.pointer_files.get(path)
    if text is None:
        return reading(Status.ABSENT)
    scan = marked_block.scan(text)
    if not scan.has_exactly_one_region():
        return reading(Status.FOREIGN)
    return reading(Status.SECTION, scan.regions[0].coordinate)
