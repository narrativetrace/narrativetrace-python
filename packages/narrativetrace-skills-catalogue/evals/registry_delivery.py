# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""INTENT: how the case a runner is driving got its skill pages -- by a REGISTRY, or by the harness
itself. One declaration in ``case.json`` answers all three questions that follow from it: whether
the harness may put any page of its own in the project, what runs before the agent starts, and
which vendor configuration every command of the trial uses.

The vocabulary of registries is CLOSED (:data:`REGISTRIES`). A case file is data, and data that may
name any executable is a shell this harness does not have: each id owns the exact argv a documented
registry line amounts to, so a case replays what a reader runs and can name nothing else.

The tree those tools read is this repository's own registry surface (:data:`REGISTRY_SURFACE`)
staged out of ``HEAD``, never out of the working tree -- for the same reason the publish script and
the vendor validation stage it that way: a registry serves what was committed, so a trial run
against uncommitted edits would grade a tree no reader can get. The staged path stands in for the
GitHub shorthand a reader types, because public ``main`` still carries the release BEFORE the one
these cases describe (design D8).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

import isolated_agent_config
from narrativetrace_skills import MARKETPLACE

Registry = Literal["claude-marketplace", "npx-skills"]
"""The closed vocabulary of registry deliveries a Tier B case may declare."""

REGISTRIES: tuple[Registry, ...] = get_args(Registry)

REGISTRY_SURFACE: tuple[str, ...] = (".claude-plugin", ".claude/skills", ".agents/skills")
"""What a registry actually reads: the plugin marketplace file and both rendered page flavours.

Every documented registry tool scans some subset of these three and nothing else of the repository,
so staging exactly them keeps a trial's tree honest in both directions -- nothing a reader cannot
see, and nothing a reader can see left out.
"""

_FIELD = "registry"

_MANIFEST = "case.json"


def is_registry(value: str) -> bool:
    """Whether ``value`` is one of the registries a case may declare."""
    return value in REGISTRIES


def staging_commands(repo_root: Path, into: Path) -> tuple[tuple[str, ...], ...]:
    """The commands that fill ``into`` with :data:`REGISTRY_SURFACE` as of ``HEAD`` of the
    repository at ``repo_root``.

    Both run with any working directory -- every path is absolute, and ``git`` is pointed at the
    repository with ``-C`` rather than inheriting it.

    **@llmNote** Two argv lists, never a shell string: ``git archive`` writes the tar and ``tar``
    unpacks it, and no argument is ever reinterpreted. The tarball lands BESIDE the staged tree, so
    the tree holds exactly what ``git archive`` put there -- a registry tool scans every file under
    the root it is given, and a clone of the public repository shows no tarball at its own root.
    """
    archive = str(into.with_name(f"{into.name}.tar"))
    return (
        (
            "git",
            "-C",
            str(repo_root),
            "archive",
            "--format=tar",
            "-o",
            archive,
            "HEAD",
            "--",
            *REGISTRY_SURFACE,
        ),
        ("tar", "-xf", archive, "-C", str(into)),
    )


def commands_for(registry: Registry, repo_root: Path, staged: Path) -> tuple[tuple[str, ...], ...]:
    """Everything ``registry`` runs before the agent starts: the staging of ``HEAD``'s registry
    surface, then the registry tool's own documented lines against the staged tree."""
    return (*staging_commands(repo_root, staged), *_registry_commands(registry, staged))


def registry_for_case(case_dir: Path) -> Registry | None:
    """The registry ``case_dir``'s own ``case.json`` declares, or ``None`` when it declares none.

    **@llmNote** An id outside :data:`REGISTRIES` raises; it is never read as an absent pre-step. A
    registry case that silently ran no pre-step would pass as a plain prompt replay while its name
    and its ledger row still claimed a registry.
    """
    manifest = case_dir / _MANIFEST
    if not manifest.is_file():
        return None
    declared: object = json.loads(manifest.read_text(encoding="utf-8")).get(_FIELD)
    if declared is None:
        return None
    if not isinstance(declared, str) or not is_registry(declared):
        raise ValueError(
            f'{manifest} declares "{_FIELD}": {declared!r}, which is not one of '
            f"{', '.join(REGISTRIES)}"
        )
    return declared  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class RegistryDelivery:
    """How one case's skill pages reach the project, built once per case by the runner.

    Both fields or neither: a step with no work directory would run a vendor tool against the
    ambient configuration, and a work directory with no step would isolate a trial that installs
    nothing.

    :param registry: the registry that delivers the pages, or ``None`` for the ordinary case
    :param work_dir: a directory the trial owns and the runner deletes -- the isolated vendor
        configuration and the staged snapshot both live inside it, never inside the graded project
    """

    registry: Registry | None = None
    work_dir: Path | None = None

    def __post_init__(self) -> None:
        if (self.registry is None) != (self.work_dir is None):
            raise ValueError(
                "a RegistryDelivery carries a pre-step and the work directory it runs in, or "
                "neither"
            )
        if self.registry is not None and not is_registry(self.registry):
            raise ValueError(f"{self.registry!r} is not one of {', '.join(REGISTRIES)}")

    @property
    def delivers_the_skills(self) -> bool:
        """Whether a registry puts this case's pages in place.

        When it does, the harness puts NONE of its own rendered pages in the project: what such a
        case measures is the state the registry left behind, and a page the harness wrote over it
        would answer the case's own question for it. For ``npx skills add`` the difference is fatal
        rather than cosmetic -- that tool makes ``.claude/skills/<name>`` a LINK.
        """
        return self.registry is not None

    @property
    def staged_snapshot(self) -> Path:
        """The tree the registry tool reads, outside the graded project."""
        if self.work_dir is None:
            raise RuntimeError("a delivery that delivers nothing stages nothing")
        return self.work_dir / "staged"

    @property
    def environment(self) -> dict[str, str]:
        """The environment every command of this trial runs with; empty for the ordinary case."""
        if self.work_dir is None:
            return {}
        return isolated_agent_config.env(self.work_dir)

    def commands(self, repo_root: Path) -> tuple[tuple[str, ...], ...]:
        """Everything that runs before the agent starts, in order; empty for the ordinary case."""
        if self.registry is None:
            return ()
        return commands_for(self.registry, repo_root, self.staged_snapshot)


def _registry_commands(registry: Registry, staged: Path) -> tuple[tuple[str, ...], ...]:
    """The tool's own lines -- what the documentation tells a reader to run, and nothing beside."""
    if registry == "claude-marketplace":
        return _marketplace_commands(staged)
    if registry == "npx-skills":
        # Unpinned on purpose: the case exists to keep a published, versionless line honest, and a
        # pinned replay is blind to the one failure it is there to catch. The resolved version
        # belongs in the run's record, not in the argv.
        return (("npx", "--yes", "skills", "add", str(staged), "-y"),)
    raise ValueError(f"{registry!r} is not one of {', '.join(REGISTRIES)}")


def _marketplace_commands(staged: Path) -> tuple[tuple[str, ...], ...]:
    """Add the marketplace, install its one plugin, then READ the install back.

    The third line is the pre-step's own self-check: a plugin whose inventory cannot be read is not
    installed, and ``details`` exits non-zero for one that is not there, so a silently empty install
    can never pass for a delivered one.
    """
    plugin = MARKETPLACE.name
    install_id = f"{plugin}@{plugin}"
    return (
        ("claude", "plugin", "marketplace", "add", str(staged)),
        ("claude", "plugin", "install", install_id),
        ("claude", "plugin", "details", install_id),
    )
