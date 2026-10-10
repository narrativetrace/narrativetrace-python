# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A2: the real oracle replay, against the real fixture, no fakes, no LLM. This is what
proves H1 — the shipped catalogue's own step data still executes today against the packages
actually in this workspace. Both mechanical skills share one fixture (``examples/sixty_seconds``).

Never invoked by ``poe mutate``'s copied-tree run (``[tool.mutmut] source_paths`` only covers
``packages/narrativetrace/``, this distribution has no mutation config yet — see
``pyproject.toml``'s mutation-exempt/deferred table), so this file needs no special handling
there, unlike the CLI's own cwd-sensitive tests.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from narrativetrace_skills.catalogue import debug_commands, verify_commands
from narrativetrace_skills.catalogue.add_narrative_tracing import ADD_NARRATIVE_TRACING
from narrativetrace_skills.catalogue.add_narrativetrace_clarity import (
    ADD_NARRATIVETRACE_CLARITY,
)
from narrativetrace_skills.catalogue.clarity_commands import INSTALL_GATE
from narrativetrace_skills.catalogue.narrativetrace_debug import NARRATIVETRACE_DEBUG
from narrativetrace_skills.catalogue.narrativetrace_doctor import NARRATIVETRACE_DOCTOR
from narrativetrace_skills.catalogue.narrativetrace_feedback import NARRATIVETRACE_FEEDBACK
from narrativetrace_skills.catalogue.narrativetrace_verify import NARRATIVETRACE_VERIFY
from narrativetrace_skills.replay import replay_skill, run_replay_command
from narrativetrace_skills.skill import Skill


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


_REPO_ROOT = _repo_root()
_SKILLS: tuple[Skill, ...] = (
    NARRATIVETRACE_DOCTOR,
    ADD_NARRATIVE_TRACING,
    NARRATIVETRACE_FEEDBACK,
    ADD_NARRATIVETRACE_CLARITY,
)


_PLACEHOLDER = re.compile(r"<[^<>]+>")

_PLACEHOLDER_VALUES = {
    # A category that needs no doctor report (the fixture is a script walkthrough, not a project).
    "<category>": "library",
    # The fixture is a directory of scripts; its own root holds no virtual environment to walk.
    "<source-dir>": ".",
    # Thresholds no fixture class can miss: the replay proves the command RUNS, not that the
    # fixture's names are good.
    "<min-score>": "0.0",
    "<max-high-issues>": "1000",
}

# `uv add` in the fixture would rewrite THIS repository's shared workspace lockfile (the fixture is
# a workspace member with no pyproject of its own), so the replay runs the equivalent that leaves
# it alone: the clarity package is already a member of the workspace environment.
_REPLAY_EQUIVALENT = {INSTALL_GATE: "uv sync --all-packages"}


def _run_with_placeholders_filled(command: str, cwd: str) -> None:
    """Replays a command whose ``<placeholders>`` an agent would fill in, each with a harmless
    value of its own, and every other placeholder with a plain word. The catalogue keeps its
    placeholders -- an example sentence in their place could be filed as somebody's report."""
    filled = _PLACEHOLDER.sub(
        lambda m: _PLACEHOLDER_VALUES.get(m.group(0), "word"),
        _REPLAY_EQUIVALENT.get(command, command),
    )
    run_replay_command(filled, cwd)


def _skip_when_a_git_step_has_no_checkout(skill: Skill, fixture_dir: Path) -> None:
    """A step that runs ``git`` needs a git work tree; the public snapshot is staged without one."""
    commands: list[str] = []
    replay_skill(skill, str(fixture_dir), lambda command, cwd: commands.append(command))
    if not any(command.startswith("git ") for command in commands):
        return
    inside = subprocess.run(  # nosec B603, B607 - fixed git query
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=fixture_dir,
        capture_output=True,
        check=False,
    )
    if inside.returncode != 0:
        pytest.skip(f"{skill.canonical_name} runs git and {fixture_dir} is not in a git checkout")


@pytest.mark.parametrize("skill", _SKILLS, ids=[s.canonical_name for s in _SKILLS])
def test_every_step_with_something_mechanical_to_run_succeeds(skill: Skill) -> None:
    fixture_dir = _REPO_ROOT / skill.fixture
    _skip_when_a_git_step_has_no_checkout(skill, fixture_dir)
    results = replay_skill(skill, str(fixture_dir), _run_with_placeholders_filled)
    failing = [r for r in results if not r.ok]
    assert failing == [], failing


@pytest.mark.parametrize("skill", _SKILLS, ids=[s.canonical_name for s in _SKILLS])
def test_at_least_one_step_actually_ran(skill: Skill) -> None:
    """The replay is not silently a no-op: some step has a command to run. The commands themselves
    are NOT run here -- the real runner executes them against the live workspace (an install step
    rewrote this repository's lockfile once), and the test above is the one that runs them."""
    fixture_dir = _REPO_ROOT / skill.fixture
    results = replay_skill(skill, str(fixture_dir), lambda command, cwd: None)
    assert any(r.ran for r in results)


def test_every_skill_shares_the_same_fixture() -> None:
    assert {skill.fixture for skill in _SKILLS} == {"examples/sixty_seconds"}


def _trace_skill_replay(out: Path, approved: Path) -> Callable[[str, str], None]:
    """The verify and debug skills' commands, replayed against the fixture's own flow test with
    the plugin switched back on (this repository's session disables it) and every artifact
    redirected under ``tmp_path``, so the replay leaves the checkout clean. The approval run and
    the promotion verify run with approval mode on, as the pin has turned it on by then."""
    env = f"NARRATIVETRACE_OUTPUT_DIR={out} NARRATIVETRACE_APPROVED_DIR={approved}"
    flow = f"{env} uv run pytest -p narrativetrace -p no:cacheprovider test_place_order_flow.py"
    equivalents = {
        verify_commands.RUN_THE_PATH: flow,
        debug_commands.REPRODUCE: flow,
        verify_commands.RUN_THE_SUITE_FOR_REVIEW: f"NARRATIVETRACE_APPROVAL=true {flow} || true",
        verify_commands.RUN_THE_SUITE: f"NARRATIVETRACE_APPROVAL=true {flow}",
        verify_commands.APPROVAL_MODE_IS_ON: (
            f"NARRATIVETRACE_APPROVAL=true {verify_commands.APPROVAL_MODE_IS_ON}"
        ),
        verify_commands.APPROVE: f"{env} {verify_commands.APPROVE}",
    }

    def run(command: str, cwd: str) -> None:
        mapped = equivalents.get(command, command)
        mapped = mapped.replace('"narrative-traces/', f'"{out}/')
        mapped = mapped.replace('"test-narratives"', f'"{approved}"')
        run_replay_command(mapped, cwd)

    return run


@pytest.mark.parametrize(
    "skill", [NARRATIVETRACE_VERIFY, NARRATIVETRACE_DEBUG], ids=["verify", "debug"]
)
def test_a_trace_reading_skill_replays_its_loop_and_its_pin_end_to_end(
    skill: Skill, tmp_path: Path
) -> None:
    out, approved = tmp_path / "narrative-traces", tmp_path / "test-narratives"
    fixture_dir = _REPO_ROOT / skill.fixture

    results = replay_skill(skill, str(fixture_dir), _trace_skill_replay(out, approved))

    assert [r for r in results if not r.ok] == []
    structural = out / "structural" / "test_place_order_flow" / "test_customer_places_an_order.nt"
    pinned = approved / "test_place_order_flow" / "test_customer_places_an_order.approved.nt"
    assert pinned.read_text(encoding="utf-8") == structural.read_text(encoding="utf-8")
    assert list(approved.rglob("*.received.nt")) == []
