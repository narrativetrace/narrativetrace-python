# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The platform table — Phase 8, platform pointers: ONE committed registry of the agent platforms
NarrativeTrace is used from, how a project proves it is on one, which pointer ``init`` writes for
it, how a stranger installs the skills, and which evidence lane exercises it. Mirrors Java's
``PlatformTable``; the row shape, the row ids and the lane ids are the cross-port contract, the
install paths are this runtime's own.

INTENT: the framework table's sibling, same shape. ``init``'s plan, ``uninstall``, the doctor's
``config.skills-installed``, the Cursor plugin manifest and ``documentation/use-with-your-agent.md``
all read these rows, and none of them is typed twice.

**@llmNote** Every platform here already discovers the pages ``init`` writes under
``.agents/skills`` (and ``.claude/skills``); a row never adds a third page flavour. Row ids are a
cross-port contract — append, never rename. The platform facts carry their verification date because
a docs-as-tests check cannot reach the vendors: re-verify them at each release and move the date.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final

MANUAL: Final = "manual"
"""The :attr:`PlatformRow.evidence_lane` of a platform no automated trial exercises."""

VERIFIED: Final = "2026-10-10"
"""The date every fact below was last checked against the vendors' own documentation."""

_KEBAB: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_DATE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_INIT: Final = "run `uv run narrativetrace init` in the project"


def _require_project_relative(path: str, what: str = "a pointer path") -> None:
    """A path that names something INSIDE the project: not empty, not ``.`` (the project itself),
    not absolute, and never climbing out with ``..``."""
    parts = PurePosixPath(path).parts
    if not path.strip() or not parts or path.startswith("/") or ".." in parts or "\\" in path:
        raise ValueError(f"{what} is project-relative and stays inside it, got {path!r}")


def _is_calendar_date(text: str) -> bool:
    """``yyyy-mm-dd`` in ASCII digits AND a real day: ``2026-13-45`` is no date."""
    if _DATE.fullmatch(text) is None:
        return False
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


@dataclass(frozen=True, slots=True)
class NoPointer:
    """The platform needs no pointer: it reads ``.agents/skills`` and ``AGENTS.md`` on its own."""

    @property
    def path(self) -> str:
        """``""`` — there is no pointer file."""
        return ""


@dataclass(frozen=True, slots=True)
class ManagedSection:
    """The same managed section ``AGENTS.md`` carries, in a platform's own always-on memory file
    (Replit's ``replit.md``) — same markers, same coordinate stamp."""

    path: str

    def __post_init__(self) -> None:
        _require_project_relative(self.path)


@dataclass(frozen=True, slots=True)
class Rule:
    """One rule file of the platform's own format (a Cursor ``.mdc`` rule) carrying the pointer
    sentence inside a managed section — never a copy of the skill pages."""

    path: str
    text: str

    def __post_init__(self) -> None:
        _require_project_relative(self.path)
        if not self.text.strip():
            raise ValueError("a rule pointer carries text")


Pointer = NoPointer | ManagedSection | Rule


@dataclass(frozen=True, slots=True)
class PlatformRow:
    """One row: marker → pointer → install path for a stranger → evidence lane.

    :param id: the stable row id (``cursor``, ``antigravity``, …) — a cross-port contract
    :param name: the platform as a reader names it
    :param marker_paths: project-relative paths whose existence proves the platform is in use; any
        one is enough, matched as exact paths so a near-miss such as ``.cursorx/`` proves nothing
    :param pointer: what ``init`` writes for this platform
    :param install_path: how a stranger gets the skills on this platform, as the page prints it
    :param agent_finds: what the platform's agent will find in a project that ran ``init``
    :param evidence_lane: the Tier B lane id that exercises the platform, or :data:`MANUAL`
    :param verified: the date the row's platform facts were last checked against the vendor's own
        documentation, ``yyyy-mm-dd``
    """

    id: str
    name: str
    marker_paths: tuple[str, ...]
    pointer: Pointer
    install_path: str
    agent_finds: str
    evidence_lane: str
    verified: str

    def __post_init__(self) -> None:
        if _KEBAB.fullmatch(self.id) is None:
            raise ValueError(f"a row id is kebab-case, got {self.id!r}")
        for column, value in (
            ("name", self.name),
            ("install path", self.install_path),
            ("agent-finds text", self.agent_finds),
        ):
            if not value.strip():
                raise ValueError(f"row {self.id} leaves its {column} empty")
        if not self.marker_paths:
            raise ValueError(f"row {self.id} has no marker path")
        for marker in self.marker_paths:
            _require_project_relative(marker, f"row {self.id}'s marker path")
        if _KEBAB.fullmatch(self.evidence_lane) is None:
            raise ValueError(f"row {self.id} names a lane id or {MANUAL}")
        if not _is_calendar_date(self.verified):
            raise ValueError(f"row {self.id} carries a yyyy-mm-dd verification date")


ROWS: Final[tuple[PlatformRow, ...]] = (
    PlatformRow(
        "cursor",
        "Cursor",
        (".cursor",),
        Rule(
            ".cursor/rules/narrativetrace.mdc",
            "The NarrativeTrace skills live under `.agents/skills` — read them before changing"
            " traced code, and run the NarrativeTrace doctor to check the install.",
        ),
        "Install the plugin from the public repository's `.cursor-plugin` manifest, or " + _INIT,
        "the skills in `.agents/skills` (Cursor also reads `.claude/skills`), and the one rule"
        " `.cursor/rules/narrativetrace.mdc` that points at them",
        "cursor",
        VERIFIED,
    ),
    PlatformRow(
        "replit",
        "Replit",
        ("replit.md", ".replit"),
        ManagedSection("replit.md"),
        "Import the public repository from GitHub (paste its URL, preview the skills, add them),"
        " or " + _INIT,
        "the skills in `.agents/skills`, and a NarrativeTrace section in `replit.md`, the project"
        " memory the Replit agent reads first",
        MANUAL,
        VERIFIED,
    ),
    PlatformRow(
        "antigravity",
        "Antigravity",
        (".agents/rules", ".agents/workflows", ".agent"),
        NoPointer(),
        "Nothing to install beyond the project itself: " + _INIT + " and commit the skills (the"
        " `agy` CLI and the IDE read them as workspace skills)",
        "the skills in `.agents/skills`, which Antigravity reads as workspace skills, and the"
        " section in `AGENTS.md`, which it loads as rules",
        "antigravity",
        VERIFIED,
    ),
    PlatformRow(
        "github-copilot",
        "GitHub Copilot",
        (".github/copilot-instructions.md",),
        NoPointer(),
        "Nothing to install beyond the repository itself: " + _INIT + " and commit the skills",
        "the skills in `.agents/skills` (Copilot also reads `.claude/skills` and"
        " `.github/skills`), and the section in `AGENTS.md`",
        MANUAL,
        VERIFIED,
    ),
    PlatformRow(
        "claude-code",
        "Claude Code",
        (".claude",),
        NoPointer(),
        "Add the repository as a plugin marketplace and install its plugin, or " + _INIT,
        "the skills in `.claude/skills` and `.agents/skills`, and the section in `AGENTS.md` that"
        " `CLAUDE.md` imports",
        "claude",
        VERIFIED,
    ),
)


def row(row_id: str) -> PlatformRow:
    """The row with this id.

    :raises KeyError: when the table has none — naming the id, so a typo is never a silent miss.
    """
    for candidate in ROWS:
        if candidate.id == row_id:
            return candidate
    raise KeyError(f"no platform row {row_id}")
