# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``replay_skill`` (generic replayer, unit-level) — fake-run tests. The real oracle replay against
the shipped catalogue's own fixture lives in ``test_replay_fixture.py``, Tier A2."""

from __future__ import annotations

import dataclasses

from narrativetrace_skills.catalogue.narrativetrace_doctor import NARRATIVETRACE_DOCTOR
from narrativetrace_skills.replay import StepReplayResult, replay_skill
from narrativetrace_skills.skill import CommandStep, Skill, SkillStep, SnippetStep


def _with_steps(*steps: SkillStep) -> Skill:
    """A stand-in skill (borrowing the real doctor's other fields) with just the given steps —
    the replayer only ever looks at `steps`, so nothing else about the skill matters here."""
    return dataclasses.replace(NARRATIVETRACE_DOCTOR, steps=steps)


class TestReplaySkillUnit:
    def test_a_step_with_neither_commands_nor_verify_is_not_ran(self) -> None:
        skill = _with_steps(SkillStep(title="narrative only", body=CommandStep(commands=())))
        [result] = replay_skill(skill, "/does-not-matter", run=lambda *_: None)
        assert result.title == "narrative only"
        assert result.ran is False
        assert result.ok is True

    def test_runs_every_command_and_the_verify_deduplicated(self) -> None:
        calls: list[tuple[str, str]] = []
        skill = _with_steps(
            SkillStep(
                title="install",
                body=CommandStep(commands=("uv sync --all-packages",)),
                verify="uv sync --all-packages",
            )
        )
        [result] = replay_skill(
            skill, "/fixture", run=lambda command, cwd: calls.append((command, cwd))
        )
        assert result == StepReplayResult(title="install", ran=True, ok=True, error=None)
        assert calls == [("uv sync --all-packages", "/fixture")]

    def test_runs_commands_then_a_distinct_verify(self) -> None:
        calls: list[str] = []
        skill = _with_steps(
            SkillStep(
                title="two",
                body=CommandStep(commands=("uv sync",)),
                verify="uv run narrativetrace doctor",
            )
        )
        replay_skill(skill, "/fixture", run=lambda command, cwd: calls.append(command))
        assert calls == ["uv sync", "uv run narrativetrace doctor"]

    def test_reports_a_failing_step_by_name_and_message_without_raising(self) -> None:
        def _boom(command: str, cwd: str) -> None:
            raise RuntimeError("boom")

        skill = _with_steps(SkillStep(title="flaky", body=CommandStep(commands=("uv sync",))))
        [result] = replay_skill(skill, "/fixture", run=_boom)
        assert result.ran is True
        assert result.ok is False
        assert result.error is not None and "boom" in result.error

    def test_a_snippet_step_with_no_verify_is_not_ran(self) -> None:
        skill = _with_steps(
            SkillStep(title="show it", body=SnippetStep(path="x.py", language="python"))
        )
        [result] = replay_skill(skill, "/fixture", run=lambda *_: None)
        assert result.ran is False
        assert result.ok is True

    def test_a_snippet_step_with_a_verify_runs_the_verify(self) -> None:
        calls: list[str] = []
        skill = _with_steps(
            SkillStep(
                title="show it",
                body=SnippetStep(path="x.py", language="python"),
                verify="uv run python x.py",
            )
        )
        [result] = replay_skill(skill, "/fixture", run=lambda command, cwd: calls.append(command))
        assert result.ran is True
        assert calls == ["uv run python x.py"]

    def test_multiple_steps_each_get_their_own_result(self) -> None:
        skill = _with_steps(
            SkillStep(title="a", body=CommandStep(commands=("uv sync",))),
            SkillStep(title="b", body=CommandStep(commands=())),
        )
        results = replay_skill(skill, "/fixture", run=lambda *_: None)
        assert [r.title for r in results] == ["a", "b"]
        assert [r.ran for r in results] == [True, False]
