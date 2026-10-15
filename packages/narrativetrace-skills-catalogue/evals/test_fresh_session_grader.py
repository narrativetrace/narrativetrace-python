# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The fresh-session grader: the session AFTER the install must see the skills it left. Ports
Java's ``grade_the_fresh_session.py`` -- item 166 (2026-10-10), an install that went green and a
next session that listed no skill.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
# Beside the graders, or one level down in mutmut's ``mutants/`` copy (which copies only the
# ``test*.py`` files). The grader is loaded by path -- the way the verifier runs it -- so no
# global ``sys.path`` change is needed; the grader puts its own ``transcript`` neighbour on it.
_EVALS = next(d for d in (_HERE, _HERE.parent) if (d / "add-narrative-tracing").is_dir())
_CASE_DIR = _EVALS / "add-narrative-tracing"
_SPEC = importlib.util.spec_from_file_location(
    "grade_the_fresh_session", _CASE_DIR / "grade_the_fresh_session.py"
)
assert _SPEC is not None and _SPEC.loader is not None
grader = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = grader
_SPEC.loader.exec_module(grader)
transcript = grader.transcript
from narrativetrace_skills import SKILLS  # noqa: E402

_ALL = [skill.canonical_name for skill in SKILLS]


def _bash(command: str) -> dict[str, object]:
    return _tool("Bash", {"command": command})


def _tool(name: str, tool_input: dict[str, object]) -> dict[str, object]:
    block = {"type": "tool_use", "id": "t1", "name": name, "input": tool_input}
    return {"type": "assistant", "message": {"content": [block]}}


def _init(skills: list[str]) -> dict[str, object]:
    return {"type": "system", "subtype": "init", "skills": skills}


def _transcript(tmp_path: Path, *fresh_events: dict[str, object]) -> Path:
    lines = [{"nt_turn": 1, "role": "user", "text": "install"}, _init([])]
    lines += [{"nt_turn": 2, "role": "user", "text": "yes, run it"}, _init([])]
    lines += [{"nt_turn": 3, "role": "user", "text": "check"}, *fresh_events]
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


def _grade(path: Path) -> str | None:
    verdict: str | None = grader.verdict(transcript.read(path))
    return verdict


def test_the_expected_skills_are_the_catalogues_own() -> None:
    assert sorted(grader.EXPECTED_SKILLS) == sorted(_ALL)


def test_passes_when_every_skill_is_listed_and_the_doctor_skill_is_called(tmp_path: Path) -> None:
    path = _transcript(tmp_path, _init(_ALL), _tool("Skill", {"skill": "narrativetrace-doctor"}))

    assert _grade(path) is None


@pytest.mark.parametrize(
    "command", ["uv run narrativetrace doctor", "narrativetrace  doctor --json"]
)
def test_passes_when_the_doctor_command_is_run_instead(tmp_path: Path, command: str) -> None:
    assert _grade(_transcript(tmp_path, _init(_ALL), _bash(command))) is None


def test_fails_naming_the_missing_skills_when_the_session_lists_none(tmp_path: Path) -> None:
    """The defect still open: no skill listed, whatever the agent then did."""
    message = _grade(_transcript(tmp_path, _init([]), _bash("uv run narrativetrace doctor")))

    assert message is not None
    assert "init event does not list these skills" in message
    assert "(it lists: nothing)" in message
    assert "narrativetrace-doctor" in message


def test_fails_when_one_skill_is_missing(tmp_path: Path) -> None:
    listed = [name for name in _ALL if name != "narrativetrace-debug"]

    message = _grade(_transcript(tmp_path, _init(listed), _bash("narrativetrace doctor")))

    assert message is not None
    assert "narrativetrace-debug" in message


def test_fails_as_a_model_reading_when_the_skills_are_listed_but_never_used(
    tmp_path: Path,
) -> None:
    message = _grade(_transcript(tmp_path, _init(_ALL), _bash("ls -la")))

    assert message is not None
    assert "listed the skills but reached for neither" in message


def test_a_neighbouring_skill_call_is_not_the_doctor(tmp_path: Path) -> None:
    path = _transcript(tmp_path, _init(_ALL), _tool("Skill", {"skill": "narrativetrace-verify"}))

    assert _grade(path) is not None


def test_grades_the_only_turn_of_a_one_turn_case(tmp_path: Path) -> None:
    """The installer-delivery case: the harness installed, the agent gets ONE fresh turn, and that
    turn is the last one."""
    lines = [
        {"nt_turn": 1, "role": "user", "text": "check"},
        _init(_ALL),
        _tool("Skill", {"skill": "narrativetrace-doctor"}),
    ]
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    assert _grade(path) is None


def test_a_one_turn_case_fails_on_the_skills_its_one_turn_does_not_list(tmp_path: Path) -> None:
    lines = [{"nt_turn": 1, "role": "user", "text": "check"}, _init(["narrativetrace-doctor"])]
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")

    message = _grade(path)

    assert message is not None
    assert "does not list these skills" in message


def test_fails_when_the_transcript_records_no_turn_at_all(tmp_path: Path) -> None:
    path = tmp_path / "transcript.jsonl"
    path.write_text("", encoding="utf-8")

    assert _grade(path) == "the transcript records no turn at all"


def test_the_script_exits_one_with_the_reason_when_there_is_no_transcript(tmp_path: Path) -> None:
    script = _CASE_DIR / "grade_the_fresh_session.py"

    done = subprocess.run(  # nosec B603 - this interpreter, this repository's own grader
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
        cwd=tmp_path,
        check=False,
    )

    assert done.returncode == 1
    assert "no transcript at $NARRATIVETRACE_TRANSCRIPT" in done.stderr


def test_the_script_exits_zero_on_a_passing_transcript(tmp_path: Path) -> None:
    path = _transcript(tmp_path, _init(_ALL), _tool("Skill", {"skill": "narrativetrace-doctor"}))

    done = subprocess.run(  # nosec B603 - this interpreter, this repository's own grader
        [sys.executable, str(_CASE_DIR / "grade_the_fresh_session.py")],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "NARRATIVETRACE_TRANSCRIPT": str(path)},
        cwd=tmp_path,
        check=False,
    )

    assert done.returncode == 0, done.stderr
    assert "doctor (skill)" in done.stdout
