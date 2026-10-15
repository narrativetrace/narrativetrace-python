# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The properties the platform pointers have to hold for files nobody wrote by hand (Phase 8,
platform pointers): the same four an installer owes ``AGENTS.md`` — nothing left to do after an
install, a round trip that gives the project back, one write per path, nothing outside the project
— plus the one that is theirs: a pointer is written only where its marker is.

Every property runs against a real temp directory, because "apply" is only meaningful against a
filesystem. The strategies are the menu ``test_installer_props`` uses, so the two files diff.
"""

from __future__ import annotations

from pathlib import Path

import carriers
import projects
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from test_installer_props import (
    CONTEXT_FILE,
    UNTOUCHED_CONTEXT_FILE,
    _apply,
    _edits,
    _ending_with_newline,
    _in_a_temporary_project,
    _paths,
)

from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.init_planner import plan_init
from narrativetrace_tooling.init.options import PERMISSIVE
from narrativetrace_tooling.init.plan_executor import execute_plan
from narrativetrace_tooling.init.project_state_reader import read_project_state
from narrativetrace_tooling.init.uninstall_planner import plan_uninstall

RULE = ".cursor/rules/narrativetrace.mdc"
POINTERS = ("replit.md", RULE)

_MARKER_MENU: list[tuple[str, ...]] = [
    (),
    (".replit",),
    (".cursor/",),
    (".replit", ".cursor/"),
    (".cursorx/",),
    ("replit.md",),
]
"""Which platform markers the project carries, near misses included."""

_MARKER_CHOICES = st.sampled_from(_MARKER_MENU)


@pytest.fixture(scope="session")
def shared_carrier(tmp_path_factory: pytest.TempPathFactory) -> Carrier:
    return carriers.fake(tmp_path_factory.mktemp("pointer-carrier"), "doctor")


def _mark(project: Path, markers: tuple[str, ...]) -> None:
    for marker in markers:
        if marker.endswith("/"):
            (project / marker).mkdir(parents=True, exist_ok=True)
        elif not (project / marker).exists():
            (project / marker).write_bytes(b"")


def _pointer_paths(plan_paths: list[Path]) -> set[str]:
    return {path.as_posix() for path in plan_paths} & set(POINTERS)


@settings(max_examples=60, deadline=None)
@given(markers=_MARKER_CHOICES, replit_md=CONTEXT_FILE)
def test_planning_after_applying_finds_no_pointer_left_to_write(
    shared_carrier: Carrier, markers: tuple[str, ...], replit_md: str
) -> None:
    files = [("replit.md", replit_md)] if "replit.md" in markers else []
    with _in_a_temporary_project(files) as project:
        _mark(project, markers)
        execute_plan(plan_init(read_project_state(project), shared_carrier, PERMISSIVE), project)

        second = plan_init(read_project_state(project), shared_carrier, PERMISSIVE)

        assert _pointer_paths([edit.path for edit in _edits(second)]) == set()


@settings(max_examples=60, deadline=None)
@given(markers=_MARKER_CHOICES, replit_md=UNTOUCHED_CONTEXT_FILE)
def test_installing_then_uninstalling_gives_the_pointer_files_back(
    shared_carrier: Carrier, markers: tuple[str, ...], replit_md: str
) -> None:
    """A pointer file that did not exist is gone again; one the user wrote is back to its bytes (a
    file appended to is left ending with a newline — the documented difference)."""
    files = [("replit.md", replit_md)] if "replit.md" in markers else []
    with _in_a_temporary_project(files) as project:
        _mark(project, markers)
        before = projects.snapshot_of(project)

        _apply(project, plan_init(read_project_state(project), shared_carrier, PERMISSIVE))
        _apply(project, plan_uninstall(read_project_state(project), PERMISSIVE))

        after = projects.snapshot_of(project)
        for path in POINTERS:
            if path in before:
                assert after[path] in (before[path], _ending_with_newline(before[path])), path
            else:
                assert path not in after, f"{path} was left behind"


@settings(max_examples=60, deadline=None)
@given(markers=_MARKER_CHOICES, replit_md=CONTEXT_FILE)
def test_a_pointer_is_planned_only_where_its_marker_is(
    shared_carrier: Carrier, markers: tuple[str, ...], replit_md: str
) -> None:
    """The marker decides, never a flag: ``PERMISSIVE`` grants every permission and a project with
    no marker still gets no pointer — and a near miss (``.cursorx/``) proves nothing."""
    files = [("replit.md", replit_md)] if "replit.md" in markers else []
    with _in_a_temporary_project(files) as project:
        _mark(project, markers)

        plan = plan_init(read_project_state(project), shared_carrier, PERMISSIVE)

        planned = _pointer_paths(_paths(plan))
        assert (RULE in planned) == (".cursor/" in markers)
        assert ("replit.md" in planned) == bool({".replit", "replit.md"} & set(markers))


@settings(max_examples=60, deadline=None)
@given(markers=_MARKER_CHOICES, replit_md=CONTEXT_FILE, rule=CONTEXT_FILE)
def test_a_plan_never_touches_one_path_twice_or_leaves_the_project(
    shared_carrier: Carrier, markers: tuple[str, ...], replit_md: str, rule: str
) -> None:
    files = [("replit.md", replit_md)] if "replit.md" in markers else []
    with _in_a_temporary_project(files) as scratch:
        project = scratch.resolve()
        _mark(project, markers)
        if ".cursor/" in markers:
            (project / RULE).parent.mkdir(parents=True, exist_ok=True)
            (project / RULE).write_bytes(rule.encode("utf-8"))

        install = plan_init(read_project_state(project), shared_carrier, PERMISSIVE)
        _apply(project, install)
        uninstall = plan_uninstall(read_project_state(project), PERMISSIVE)

        for plan in (install, uninstall):
            assert len(set(_paths(plan))) == len(_paths(plan))
            for action in plan.actions:
                assert (project / action.path).resolve().is_relative_to(project)


def test_the_marker_menu_really_covers_the_cases_the_properties_are_about() -> None:
    """A property over a strategy that never generates the interesting case proves nothing."""
    menu = {marker for choice in _MARKER_MENU for marker in choice}

    assert {".replit", ".cursor/", ".cursorx/", "replit.md"} <= menu
    assert () in _MARKER_MENU, "a project on no platform at all"
    assert any(len(choice) > 1 for choice in _MARKER_MENU), "two markers at once"
