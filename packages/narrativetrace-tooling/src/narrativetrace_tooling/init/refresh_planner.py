# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Decides what an internal refresh would rewrite: the pages and the managed section a previous
install left behind, brought up to the carrier now resolved.

INTENT: a refresh may KEEP an install current; it may never start one. That is the whole of the
difference from the install planner, and it is why this planner exists rather than a flag — "never
create" has to be true by construction, not by a caller remembering an option.

**@llmNote** This runtime has no build hook of the right altitude, so nothing calls a refresh
automatically (that was ruled: staleness is the doctor's finding, and re-running ``init`` is the
refresh). The planner exists because ``init``'s own hidden refresh mode is defined as "the
``ReplaceBlock`` actions only", and defining it here keeps the never-create rule in one place.

**@sideEffects** None. Pure, like the other two planners.
"""

from __future__ import annotations

from collections.abc import Iterator

from narrativetrace_tooling.init.action import Action, ReplaceBlock
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.init_planner import plan_init
from narrativetrace_tooling.init.options import InitOptions
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.project_state import InstalledSkill, Presence, ProjectState


def plan_refresh(state: ProjectState, carrier: Carrier) -> InitPlan:
    """The plan a refresh against this carrier would apply — empty unless something is stale."""
    if state is None or carrier is None:
        raise TypeError("planning a refresh needs a project state and a carrier")
    return InitPlan(carrier.coordinate, False, _rewrites(state, carrier))


def is_installed(state: ProjectState) -> bool:
    """Whether this project carries an install of ours at all — one skill directory whose page has
    our provenance line.

    **@llmNote** This is the question to ask BEFORE reaching for a carrier. A project that never ran
    ``init`` must never resolve one, or every run in every project would talk about skills nobody
    installed. A directory somebody else owns is not an install of ours, however it is named.
    """
    if state is None:
        raise TypeError("asking what a project carries needs a project state")
    return next(_ours(state), None) is not None


def _rewrites(state: ProjectState, carrier: Carrier) -> tuple[Action, ...]:
    """The install plan, kept down to the actions that REWRITE something already ours.

    Every other kind — a page to create, a section to append, an import line to add, a refusal — is
    dropped here, which is what keeps a refresh from starting an install nobody asked for.
    """
    if not _is_stale(state, carrier.coordinate):
        return ()
    planned = plan_init(state, carrier, InitOptions())
    return tuple(action for action in planned.actions if isinstance(action, ReplaceBlock))


def _is_stale(state: ProjectState, coordinate: str) -> bool:
    """Whether this project carries an install of ours from a DIFFERENT carrier. A project with no
    install of ours is never stale: a refresh renews what init put there and starts nothing."""
    return any(skill.coordinate != coordinate for skill in _ours(state))


def _ours(state: ProjectState) -> Iterator[InstalledSkill]:
    return (skill for skill in state.installed_skills if skill.presence is Presence.OURS)
