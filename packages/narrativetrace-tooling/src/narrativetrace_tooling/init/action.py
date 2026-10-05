# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""One thing an install or an uninstall would do to one path.

INTENT: the unit a plan is made of, and the reason a plan can be printed as a diff before anything
happens. Every action that touches a file carries the file's WHOLE text before and after, so the
executor needs no knowledge of the project and the renderer can diff without reading the disk.

**@llmNote** Paths are project-relative and normalised — an absolute path, or one that climbs out
with ``..``, is refused at construction. That is the only thing standing between a hand-written plan
and a write outside the project.

**@pattern** A closed union of frozen dataclasses, not a class hierarchy: :data:`Action` and
:data:`FileEdit` are unions, so ``isinstance`` narrows, a ``match`` over the kinds can be checked
exhaustively by a type checker, and a new kind of action is a type error everywhere it matters
rather than a silent no-op.

Guards follow the package rule: :class:`TypeError` when a required value is missing altogether,
:class:`ValueError` when a value is present and unusable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import ClassVar

from narrativetrace_tooling.init import marked_block


def require_project_relative(path: Path) -> Path:
    """The same path, normalised.

    :raises TypeError: when no path is given
    :raises ValueError: when the path is absolute, empty, or climbs out of the project with ``..``
    """
    if not isinstance(path, PurePath):
        raise TypeError(f"an action needs a path, never {type(path).__name__}")
    normalised = Path(os.path.normpath(path))
    climbs_out = normalised.parts and normalised.parts[0] == os.pardir
    if path.is_absolute() or str(normalised) in (".", "") or climbs_out:
        raise ValueError(
            f'an action\'s path must be project-relative and stay inside it, got "{path}"'
        )
    return normalised


def require_action_text(text: str) -> None:
    """Text an action carries is never missing; absence is the empty string."""
    if not isinstance(text, str):
        raise TypeError(f'an action\'s text is "" when absent, never {type(text).__name__}')


@dataclass(frozen=True, slots=True)
class CreateFile:
    """Writes a file that is not there yet."""

    path: Path
    content: str

    kind: ClassVar[str] = "create"

    def __post_init__(self) -> None:
        require_action_text(self.content)
        object.__setattr__(self, "path", require_project_relative(self.path))

    @property
    def before(self) -> str:
        """``""`` — the file does not exist yet."""
        return ""

    @property
    def after(self) -> str:
        return self.content


@dataclass(frozen=True, slots=True)
class ReplaceBlock:
    """Rewrites a file whose NarrativeTrace-owned region changed — the managed block between the
    markers, or, for a copied ``SKILL.md``, the whole page."""

    path: Path
    before: str
    after: str

    kind: ClassVar[str] = "replace"

    def __post_init__(self) -> None:
        require_action_text(self.before)
        require_action_text(self.after)
        object.__setattr__(self, "path", require_project_relative(self.path))


@dataclass(frozen=True, slots=True)
class AppendBlock:
    """Adds the managed block to the end of an existing file, after one blank line."""

    path: Path
    before: str
    block: str

    kind: ClassVar[str] = "append"

    def __post_init__(self) -> None:
        require_action_text(self.before)
        require_action_text(self.block)
        object.__setattr__(self, "path", require_project_relative(self.path))

    @property
    def after(self) -> str:
        return marked_block.append(self.before, self.block)


@dataclass(frozen=True, slots=True)
class AppendLine:
    """Adds one line to the end of an existing file, after one blank line."""

    path: Path
    before: str
    line: str

    kind: ClassVar[str] = "append-line"

    def __post_init__(self) -> None:
        require_action_text(self.before)
        require_action_text(self.line)
        object.__setattr__(self, "path", require_project_relative(self.path))

    @property
    def after(self) -> str:
        return marked_block.append(self.before, self.line + marked_block.eol_of(self.before))


@dataclass(frozen=True, slots=True)
class DeleteFile:
    """Removes a file the installer wrote."""

    path: Path
    before: str

    kind: ClassVar[str] = "delete"

    def __post_init__(self) -> None:
        require_action_text(self.before)
        object.__setattr__(self, "path", require_project_relative(self.path))

    @property
    def after(self) -> str:
        """``""`` — the file is gone."""
        return ""


@dataclass(frozen=True, slots=True)
class DeleteDirectory:
    """Removes a directory the installer created, once its files are gone.

    **@llmNote** Never recursive: a directory that still holds somebody else's file is left alone
    and reported, because deleting it would take that file with it.
    """

    path: Path

    kind: ClassVar[str] = "delete-directory"

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", require_project_relative(self.path))


@dataclass(frozen=True, slots=True)
class Refuse:
    """Something the installer will NOT do, and why.

    **@llmNote** A refusal is reported, never raised: the rest of the plan proceeds, and the run
    exits 1 so a script notices.
    """

    path: Path
    reason: str

    kind: ClassVar[str] = "refuse"

    def __post_init__(self) -> None:
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("a refusal must carry a reason naming what it refused")
        object.__setattr__(self, "path", require_project_relative(self.path))


FileEdit = CreateFile | ReplaceBlock | AppendBlock | AppendLine | DeleteFile
"""An action that leaves one file with a known text.

``before`` is ``""`` for a file that does not exist yet, ``after`` is ``""`` for one being deleted.
"""

Action = FileEdit | DeleteDirectory | Refuse
"""Every kind of action a plan can hold."""
