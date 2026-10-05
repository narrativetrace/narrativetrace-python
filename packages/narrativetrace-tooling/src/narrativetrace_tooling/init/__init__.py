# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The agent-skills installer behind ``narrativetrace init`` and ``narrativetrace uninstall``.

INTENT: copy the rendered skill pages a carrier ships into a consumer project, and write the
always-on pointer into that project's ``AGENTS.md`` — safely enough that a person can run it on a
repository they care about. "Safely enough" is structural, not careful:

* one read-only :class:`~narrativetrace_tooling.init.project_state.ProjectState` snapshot of the
  project, taken once;
* pure planners over ``(snapshot, carrier, options)``, so the plan a ``--dry-run`` prints is
  byte-for-byte the plan a real run applies;
* every action carrying the WHOLE text of the file before and after, so the executor asks the
  project nothing;
* one writer, temp-file-then-atomic-rename, which reports a refusal rather than raising it.

Nothing here renders a skill page: the installer copies bytes the catalogue's own render step
produced and this repository's drift gate pins. Rendering in two places is two places to diverge.

Guards follow one rule throughout: :class:`TypeError` when a required value is missing altogether,
:class:`ValueError` when a value is present and unusable. "No path given" and "a path that climbs
out of the project" are different mistakes, and a caller may well want to catch only the second.

**@llmNote** What this module re-exports IS the library's surface — everything an entry point needs
and nothing more: resolve or open a carrier, read a project, plan, apply, render, and ask whether
the carrier matches the release this project runs. The modules behind it are free to move.

Reached through the ``narrativetrace`` console script; an entry point imports this module and
nothing deeper.
"""

from __future__ import annotations

from narrativetrace_tooling.init.carrier import (
    Carrier,
    carrier_from_distribution,
    open_carrier,
    resolve_carrier,
)
from narrativetrace_tooling.init.catalogue import SkillCatalogue, SkillEntry, SkillFlavour
from narrativetrace_tooling.init.init_planner import plan_init
from narrativetrace_tooling.init.options import PERMISSIVE, InitOptions, Scope, Vendor
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.plan_executor import execute_plan
from narrativetrace_tooling.init.plan_renderer import render_plan, render_report
from narrativetrace_tooling.init.project_state import InstalledSkill, Presence, ProjectState
from narrativetrace_tooling.init.project_state_reader import read_project_state
from narrativetrace_tooling.init.refresh_planner import is_installed, plan_refresh
from narrativetrace_tooling.init.report import ExecutionReport, Status
from narrativetrace_tooling.init.uninstall_planner import plan_uninstall
from narrativetrace_tooling.init.version_guard import project_family_version, version_warning

__all__ = [
    "PERMISSIVE",
    "Carrier",
    "ExecutionReport",
    "InitOptions",
    "InitPlan",
    "InstalledSkill",
    "Presence",
    "ProjectState",
    "Scope",
    "SkillCatalogue",
    "SkillEntry",
    "SkillFlavour",
    "Status",
    "Vendor",
    "carrier_from_distribution",
    "execute_plan",
    "is_installed",
    "open_carrier",
    "plan_init",
    "plan_refresh",
    "plan_uninstall",
    "project_family_version",
    "read_project_state",
    "render_plan",
    "render_report",
    "resolve_carrier",
    "version_warning",
]
