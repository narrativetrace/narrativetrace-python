# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The properties an installer has to hold for files nobody wrote by hand.

Four of them: planning after applying finds nothing left to do, applying the same plan twice changes
nothing the second time, installing and then uninstalling gives the project back, and a plan never
touches one path twice. Each runs against a real temp directory, because "apply" is only meaningful
against a filesystem.

Named after the Java port's ``InstallerPropertyTest`` so the two lists diff; its jqwik generators
become Hypothesis strategies over the same line menu.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterable, Iterator
from pathlib import Path

import carriers
import projects
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.action import FileEdit
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.init_planner import plan_init
from narrativetrace_tooling.init.options import PERMISSIVE
from narrativetrace_tooling.init.plan import InitPlan
from narrativetrace_tooling.init.plan_executor import execute_plan
from narrativetrace_tooling.init.project_state_reader import read_project_state
from narrativetrace_tooling.init.uninstall_planner import plan_uninstall

BOM = "﻿"

_ANY_LINE = [
    "# Title",
    "",
    "some prose about the project",
    "```",
    "@AGENTS.md",
    "@AGENTS.md   ",
    "  <!-- narrativetrace:start -->",
    "<!-- narrativetrace:start narrativetrace-skills==0.0.1 -->",
    "<!-- narrativetrace:end -->",
    "<!-- narrativetrace:created -->",
    "<!-- narrativetrace:skills:start -->",
]
"""Context-file lines as they come: markers, fences, import lines, our own created note."""

_UNTOUCHED_LINE = [
    "# Title",
    "",
    "some prose about the project",
    "```",
    "  indented",
    "<!-- an unrelated comment -->",
    "@SOMETHING.md",
    "tail",
]
"""The same, minus anything of ours: the shape the round trip is defined for."""


def _files(lines: list[str]) -> st.SearchStrategy[str]:
    """Joins lines with one of the two line endings, and sometimes drops the final newline or adds a
    byte-order mark."""
    return st.builds(
        _assemble,
        st.lists(st.sampled_from(lines), max_size=10),
        st.sampled_from(["\n", "\r\n"]),
        st.booleans(),
        st.booleans(),
    )


def _assemble(lines: list[str], eol: str, final_newline: bool, bom: bool) -> str:
    if not lines:
        return ""
    joined = eol.join(lines) + (eol if final_newline else "")
    return BOM + joined if bom else joined


CONTEXT_FILE = _files(_ANY_LINE)

UNTOUCHED_CONTEXT_FILE = _files(_UNTOUCHED_LINE)


@pytest.fixture(scope="session")
def shared_carrier(tmp_path_factory: pytest.TempPathFactory) -> Carrier:
    """One hand-built carrier for the whole session — the properties build hundreds of projects and
    none of them cares which skills the carrier lists.

    Session-scoped on purpose: a function-scoped fixture would be built once and reused across every
    generated example, which Hypothesis rightly refuses.
    """
    return carriers.fake(tmp_path_factory.mktemp("shared-carrier"), "doctor", "clarity")


def _write(file: Path, content: str) -> None:
    file.write_bytes(content.encode("utf-8"))


def _edits(plan: InitPlan) -> list[FileEdit]:
    return [action for action in plan.actions if isinstance(action, FileEdit)]


def _paths(plan: InitPlan) -> list[Path]:
    return [action.path for action in plan.actions]


def _ending_with_newline(content: str) -> str:
    """The one documented exception to the round trip: a file the installer APPENDED to is left
    ending with a newline, because a block has to start on its own line and nothing records that the
    file lacked one."""
    if not content or content.endswith(("\n", "\r")):
        return content
    return content + marked_block.eol_of(content)


def _apply(project: Path, plan: InitPlan) -> None:
    execute_plan(plan, project)


def _install(project: Path, carrier: Carrier) -> InitPlan:
    plan = plan_init(read_project_state(project), carrier, PERMISSIVE)
    _apply(project, plan)
    return plan


@contextlib.contextmanager
def _in_a_temporary_project(contents: Iterable[tuple[str, str]]) -> Iterator[Path]:
    """A fresh temp project holding the given files, deleted whatever happened.

    The create-run-delete shape and the whole-tree readings live in ``projects``, shared with
    ``test_registry_tree_props``: one of those readings has to be careful about symbolic links, and
    two careful implementations are one to get wrong.
    """
    with projects.in_a_temporary_one("narrativetrace-install") as project:
        for name, content in contents:
            _write(project / name, content)
        yield project


@settings(max_examples=60, deadline=None)
@given(agents_md=CONTEXT_FILE, claude_md=CONTEXT_FILE)
def test_planning_after_applying_finds_nothing_left_to_do(
    shared_carrier: Carrier, agents_md: str, claude_md: str
) -> None:
    """A refusal may repeat — it is a decision about a file, not a change to one — so what must be
    empty is the set of EDITS."""
    with _in_a_temporary_project([("AGENTS.md", agents_md), ("CLAUDE.md", claude_md)]) as project:
        _install(project, shared_carrier)

        second = plan_init(read_project_state(project), shared_carrier, PERMISSIVE)

        assert _edits(second) == [], "a second install of the same carrier has nothing to write"


@settings(max_examples=60, deadline=None)
@given(agents_md=CONTEXT_FILE)
def test_applying_the_same_plan_twice_changes_nothing_the_second_time(
    shared_carrier: Carrier, agents_md: str
) -> None:
    """Idempotence of the APPLY, not of the plan: every action carries the whole text it produces,
    so replaying one is a write of bytes that are already there."""
    with _in_a_temporary_project([("AGENTS.md", agents_md)]) as project:
        plan = _install(project, shared_carrier)
        once = projects.snapshot_of(project)

        _apply(project, plan)

        assert projects.snapshot_of(project) == once


@settings(max_examples=60, deadline=None)
@given(agents_md=UNTOUCHED_CONTEXT_FILE, claude_md=UNTOUCHED_CONTEXT_FILE)
def test_installing_then_uninstalling_leaves_the_project_as_it_was(
    shared_carrier: Carrier, agents_md: str, claude_md: str
) -> None:
    """The one documented difference: a file the installer appended to is left ending with a
    newline, because a block has to start on its own line and nothing records that it lacked one."""
    with _in_a_temporary_project([("AGENTS.md", agents_md), ("CLAUDE.md", claude_md)]) as project:
        before = projects.snapshot_of(project)

        _install(project, shared_carrier)
        _apply(project, plan_uninstall(read_project_state(project), PERMISSIVE))

        after = projects.snapshot_of(project)
        assert after.keys() == before.keys(), "no file gained or lost"
        for path, content in after.items():
            assert content in (before[path], _ending_with_newline(before[path])), path


@settings(max_examples=60, deadline=None)
@given(agents_md=CONTEXT_FILE, claude_md=CONTEXT_FILE)
def test_a_plan_never_touches_one_path_twice(
    shared_carrier: Carrier, agents_md: str, claude_md: str
) -> None:
    with _in_a_temporary_project([("AGENTS.md", agents_md), ("CLAUDE.md", claude_md)]) as project:
        (project / ".claude").mkdir()

        install = plan_init(read_project_state(project), shared_carrier, PERMISSIVE)
        _apply(project, install)
        uninstall = plan_uninstall(read_project_state(project), PERMISSIVE)

        for plan in (install, uninstall):
            assert len(set(_paths(plan))) == len(_paths(plan))


@settings(max_examples=60, deadline=None)
@given(agents_md=CONTEXT_FILE)
def test_what_was_planned_is_what_the_files_say(shared_carrier: Carrier, agents_md: str) -> None:
    with _in_a_temporary_project([("AGENTS.md", agents_md)]) as project:
        plan = plan_init(read_project_state(project), shared_carrier, PERMISSIVE)
        _apply(project, plan)

        for edit in _edits(plan):
            file = project / edit.path
            written = file.read_bytes().decode("utf-8") if file.exists() else ""
            assert written == edit.after, str(edit.path)


@settings(max_examples=60, deadline=None)
@given(agents_md=CONTEXT_FILE, claude_md=CONTEXT_FILE)
def test_an_install_never_writes_outside_the_project(
    shared_carrier: Carrier, agents_md: str, claude_md: str
) -> None:
    """The guard on every action's path, stated as a property: whatever a generated context file
    contains, every path a plan names stays inside the project it was planned for."""
    with _in_a_temporary_project([("AGENTS.md", agents_md), ("CLAUDE.md", claude_md)]) as scratch:
        project = scratch.resolve()

        plan = plan_init(read_project_state(project), shared_carrier, PERMISSIVE)

        for action in plan.actions:
            assert (project / action.path).resolve().is_relative_to(project)


def test_the_generator_really_produces_the_shapes_the_properties_are_about() -> None:
    """A property over a strategy that never generates the interesting case proves nothing. One
    example-based check that the menu can produce a CRLF file, a byte-order mark, a file with no
    final newline and one of our own markers."""
    examples = {
        _assemble(_ANY_LINE, eol, final, bom)
        for eol in ("\n", "\r\n")
        for final in (True, False)
        for bom in (True, False)
    }

    assert any("\r\n" in example for example in examples)
    assert any(example.startswith(BOM) for example in examples)
    assert any(not example.endswith(("\n", "\r")) for example in examples)
    assert all(marked_block.START in example for example in examples)
    assert _assemble([], "\n", True, True) == ""
