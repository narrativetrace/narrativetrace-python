# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``config.skills-installed`` — the NarrativeTrace agent skills this project's carrier ships are
installed under ``.agents/skills/``, and stamped with a release this project actually runs.

Reads what the installer's own :class:`~narrativetrace_tooling.init.project_state.ProjectState`
reader found — a page counts as ours only when it carries the provenance line ``init`` writes — so
the doctor and the installer can never disagree about which directory belongs to whom.

**@llmNote** Unlike the Java port, this runtime's core distribution always bundles a fallback
carrier as package data (Phase 3 milestone 1) — the running process IS a dependency of every
consumer, so a carrier is essentially always resolvable. "Cannot tell" is therefore gated on the
PROJECT'S resolved release instead of on carrier resolution: a project with no readable
``narrativetrace`` version at all (the empty-project path the install prompt starts from) is the one
case the doctor cannot judge.

**@llmNote** "Current" compares a stamp's VERSION half against the project's resolved release,
never the whole coordinate: the two distributions this port ships (the core, and the published
``narrativetrace-skills`` carrier) can be pinned independently (D1), so a stamp naming either one at
the matching version is current.

**@llmNote** Only ``.agents/skills/`` counts. The vendor copy is written only where a project is
detected as that vendor's, so a project carrying the vendor copy alone is a project the
open-standard install never reached.
"""

from __future__ import annotations

from narrativetrace_tooling.doctor.doc_urls import DOC
from narrativetrace_tooling.doctor.finding import failed, passed
from narrativetrace_tooling.doctor.types import DoctorSnapshot, Finding
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.project_state import InstalledSkill, Presence

ID = "config.skills-installed"

_NOT_OURS = " (there, but not ours)"

# Quoted verbatim by documentation/agent-skills.md's "From a registry" section (rule 8, docs as
# tests) — the marker pair around these three fields is that embed's source, never typed into the
# page.
# snippet:begin registryMessages
_INIT_COMMAND = "uv run narrativetrace init --dry-run"

_READ_THE_DIFF = f"Run `{_INIT_COMMAND}`, read the diff, then run it without the flag."

_FROM_A_REGISTRY = (
    " Pages that are there without our line usually came from a registry (npx skills add, a plugin"
    " or workspace install). A page identical to this release's is adopted, and no --force is"
    " needed."
)
"""What a page with no provenance line most often IS: a registry install of this repository's own
rendered pages (design D5 state 3). Naming the case matters because the obvious reading of "not
ours" is "somebody else's work", which invites a ``--force`` nobody needs."""

# snippet:end registryMessages

_DOC_URL = DOC["agent_skills_installing"]


def check_skills_installed(snapshot: DoctorSnapshot) -> Finding:
    """Worst first: nothing installed, then a wrong stamp, then a partial install."""
    if snapshot.narrativetrace_version is None:
        return passed(
            ID,
            "this project's narrativetrace version could not be determined — cannot tell whether"
            " the agent skills are current",
            _DOC_URL,
        )
    ours = _ours(snapshot)
    if not ours:
        return _not_installed(snapshot)
    stale = _stale(ours, snapshot.narrativetrace_version)
    if stale:
        return _stale_finding(stale, snapshot.narrativetrace_version)
    missing = _missing(snapshot)
    return _incomplete(missing) if missing else _up_to_date(ours)


def _found(snapshot: DoctorSnapshot, name: str) -> InstalledSkill | None:
    return next(
        (
            skill
            for skill in snapshot.installed_skills
            if skill.flavour is SkillFlavour.AGENTS and skill.name == name
        ),
        None,
    )


def _is_ours(snapshot: DoctorSnapshot, name: str) -> bool:
    found = _found(snapshot, name)
    return found is not None and found.presence is Presence.OURS


def _ours(snapshot: DoctorSnapshot) -> tuple[InstalledSkill, ...]:
    found = (_found(snapshot, name) for name in snapshot.catalogue_skill_names)
    return tuple(skill for skill in found if skill is not None and skill.presence is Presence.OURS)


def _present(snapshot: DoctorSnapshot) -> tuple[str, ...]:
    """The catalogue's skills that have a directory in this project. Asked only from
    :func:`_not_installed`, where nothing of ours is installed by construction — so "it is there"
    already means "it is somebody else's"."""
    return tuple(
        name for name in snapshot.catalogue_skill_names if _found(snapshot, name) is not None
    )


def _missing(snapshot: DoctorSnapshot) -> tuple[str, ...]:
    """The catalogue's skills that are absent, or present as somebody else's — named for a
    reader."""
    return tuple(
        f"{name}{_NOT_OURS}" if _found(snapshot, name) is not None else name
        for name in snapshot.catalogue_skill_names
        if not _is_ours(snapshot, name)
    )


def _version_of(coordinate: str) -> str:
    """The version half of a ``<distribution>==<version>`` stamp, or the whole stamp when it does
    not have that shape — compared as it stands, which reads as stale unless the project's own
    version happens to be spelled exactly the same way."""
    _distribution, separator, version = coordinate.partition("==")
    return version if separator else coordinate


def _stale(ours: tuple[InstalledSkill, ...], narrativetrace_version: str) -> tuple[str, ...]:
    """Every distinct stamp among the installed skills that does not name this project's own
    release — sorted, so a reader sees the whole picture."""
    return tuple(
        sorted(
            {
                skill.coordinate
                for skill in ours
                if _version_of(skill.coordinate) != narrativetrace_version
            }
        )
    )


def _not_installed(snapshot: DoctorSnapshot) -> Finding:
    foreign = _present(snapshot)
    detail = f" — {', '.join(foreign)} is there, not ours" if foreign else ""
    install_root = SkillFlavour.AGENTS.install_root
    return failed(
        ID,
        f"the NarrativeTrace agent skills are not installed under {install_root}/{detail}",
        _READ_THE_DIFF + (_FROM_A_REGISTRY if foreign else ""),
        _DOC_URL,
    )


def _stale_finding(stale: tuple[str, ...], narrativetrace_version: str) -> Finding:
    return failed(
        ID,
        f"agent skills installed from {', '.join(stale)}, project resolves"
        f" narrativetrace=={narrativetrace_version}",
        f"Re-run `{_INIT_COMMAND}` and apply it — the installed pages describe a different release"
        " of NarrativeTrace than this project uses.",
        _DOC_URL,
    )


def _incomplete(missing: tuple[str, ...]) -> Finding:
    return failed(
        ID,
        f"the agent skills are installed, but {', '.join(missing)} is missing",
        f"Run `{_INIT_COMMAND}` to add the missing page(s). A page identical to this release's is"
        " adopted as it stands; --force is only for a directory somebody else really owns.",
        _DOC_URL,
    )


def _up_to_date(ours: tuple[InstalledSkill, ...]) -> Finding:
    return passed(
        ID,
        f"all {len(ours)} agent skill(s) are installed and current",
        _DOC_URL,
    )
