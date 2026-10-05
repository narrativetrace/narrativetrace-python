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

from pathlib import Path

import pytest
from narrativetrace_skills.catalogue.add_narrative_tracing import ADD_NARRATIVE_TRACING
from narrativetrace_skills.catalogue.narrativetrace_doctor import NARRATIVETRACE_DOCTOR
from narrativetrace_skills.replay import replay_skill
from narrativetrace_skills.skill import Skill


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


_REPO_ROOT = _repo_root()
_SKILLS: tuple[Skill, ...] = (NARRATIVETRACE_DOCTOR, ADD_NARRATIVE_TRACING)


@pytest.mark.parametrize("skill", _SKILLS, ids=[s.canonical_name for s in _SKILLS])
def test_every_step_with_something_mechanical_to_run_succeeds(skill: Skill) -> None:
    fixture_dir = _REPO_ROOT / skill.fixture
    results = replay_skill(skill, str(fixture_dir))
    failing = [r for r in results if not r.ok]
    assert failing == [], failing


@pytest.mark.parametrize("skill", _SKILLS, ids=[s.canonical_name for s in _SKILLS])
def test_at_least_one_step_actually_ran(skill: Skill) -> None:
    """The replay is not silently a no-op."""
    fixture_dir = _REPO_ROOT / skill.fixture
    results = replay_skill(skill, str(fixture_dir))
    assert any(r.ran for r in results)


def test_both_skills_share_the_same_fixture() -> None:
    assert (
        NARRATIVETRACE_DOCTOR.fixture == ADD_NARRATIVE_TRACING.fixture == "examples/sixty_seconds"
    )
