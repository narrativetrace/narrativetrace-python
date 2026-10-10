# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``add-narrativetrace-clarity``: installs the clarity gate, reads its report, renames what it
flags and re-runs until the gate is clean. The Java reference's clarity skill, ported to this
runtime's gate -- a console script that scans Python SOURCE, so there is no test-runner path."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from narrativetrace_skills import (
    SKILLS,
    command_strings,
    find_skill,
    publishing_not_pre_approved,
    render_claude_skill,
    render_codex_skill,
)
from narrativetrace_skills.catalogue.add_narrativetrace_clarity import (
    ADD_NARRATIVETRACE_CLARITY,
)
from narrativetrace_skills.catalogue.clarity_commands import REPORTS_FRESH_CODE


def _resolve(path: str) -> str:
    raise AssertionError(f"this skill embeds no snippet, asked for {path}")


class TestTheSkillIsInTheCatalogue:
    def test_is_found_under_its_canonical_name(self) -> None:
        assert find_skill("add-narrativetrace-clarity") is ADD_NARRATIVETRACE_CLARITY
        assert ADD_NARRATIVETRACE_CLARITY in SKILLS

    def test_pre_approves_exactly_the_toolchain_a_non_publishing_skill_may(self) -> None:
        assert ADD_NARRATIVETRACE_CLARITY.allowed_tools == ("uv", "git")
        assert publishing_not_pre_approved(SKILLS) == ()

    def test_claude_page_grants_uv_and_git_and_codex_page_grants_nothing(self) -> None:
        claude = render_claude_skill(ADD_NARRATIVETRACE_CLARITY, _resolve)
        codex = render_codex_skill(ADD_NARRATIVETRACE_CLARITY, _resolve)
        assert "allowed-tools: Bash(uv *), Bash(git *)\n" in claude
        assert "allowed-tools" not in codex

    def test_sits_beside_the_other_skills_on_the_shared_fixture(self) -> None:
        assert ADD_NARRATIVETRACE_CLARITY.fixture == "examples/sixty_seconds"


class TestTheCommands:
    def test_the_dependency_goes_in_the_dev_group_not_the_runtime_dependencies(self) -> None:
        assert "uv add --dev narrativetrace-clarity" in command_strings(ADD_NARRATIVETRACE_CLARITY)

    def test_every_scan_names_a_source_directory_and_never_the_project_root(self) -> None:
        # `rglob("*.py")` under "." walks .venv, so a bare "." scores the dependencies' names.
        scans = [
            c
            for c in command_strings(ADD_NARRATIVETRACE_CLARITY)
            if "narrativetrace-clarity " in c and "--help" not in c
        ]
        assert len(scans) >= 2
        for scan in scans:
            assert scan.startswith("uv run narrativetrace-clarity <source-dir> "), scan
            assert " . " not in f"{scan} ", scan

    def test_the_rerun_carries_both_thresholds_and_the_first_scan_carries_none(self) -> None:
        scans = [
            c
            for c in command_strings(ADD_NARRATIVETRACE_CLARITY)
            if c.startswith("uv run narrativetrace-clarity <source-dir>")
        ]
        assert "--min-score" not in scans[0]
        assert "--max-high-issues" not in scans[0]
        assert "--min-score <min-score> --max-high-issues <max-high-issues>" in scans[-1]

    def test_the_test_suite_runs_between_the_renames_and_the_rerun(self) -> None:
        titles = [step.title for step in ADD_NARRATIVETRACE_CLARITY.steps]
        tests = next(i for i, t in enumerate(titles) if t.startswith("Run the project's tests"))
        rename = next(i for i, t in enumerate(titles) if t.startswith("Read the report"))
        rerun = next(i for i, t in enumerate(titles) if t.startswith("Re-run"))
        assert rename < tests < rerun

    def test_no_command_raises_a_threshold_or_turns_the_gate_advisory(self) -> None:
        for command in command_strings(ADD_NARRATIVETRACE_CLARITY):
            assert "--warn-only" not in command


class TestTheFreshReportCheckBites:
    """The scan exits 0 and writes NOTHING when it finds no class, so the previous run's files
    would pass any check that only asked whether they exist."""

    @staticmethod
    def _run(cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # nosec B603 - this interpreter, the catalogue's own snippet
            [sys.executable, "-I", "-c", REPORTS_FRESH_CODE],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _write(cwd: Path, scenarios: list[dict[str, object]], markdown: str = "# report\n") -> None:
        out = cwd / "build" / "narrativetrace"
        out.mkdir(parents=True)
        (out / "clarity-results.json").write_text(
            json.dumps({"version": "1.0", "scenarios": scenarios}), encoding="utf-8"
        )
        (out / ("clarity-report" + ".md")).write_text(markdown, encoding="utf-8")

    def test_accepts_a_fresh_nonempty_pair(self, tmp_path: Path) -> None:
        self._write(tmp_path, [{"name": "A", "issues": []}])
        assert self._run(tmp_path).returncode == 0

    def test_refuses_a_directory_the_scan_never_wrote(self, tmp_path: Path) -> None:
        assert self._run(tmp_path).returncode == 1

    def test_refuses_a_report_with_no_scenarios(self, tmp_path: Path) -> None:
        self._write(tmp_path, [])
        assert self._run(tmp_path).returncode == 1

    def test_refuses_an_empty_markdown_report(self, tmp_path: Path) -> None:
        self._write(tmp_path, [{"name": "A", "issues": []}], markdown="")
        assert self._run(tmp_path).returncode == 1

    def test_refuses_a_pair_left_over_from_an_earlier_run(self, tmp_path: Path) -> None:
        self._write(tmp_path, [{"name": "A", "issues": []}])
        old = time.time() - 3600
        for artefact in (tmp_path / "build" / "narrativetrace").iterdir():
            os.utime(artefact, (old, old))
        result = self._run(tmp_path)
        assert result.returncode == 1
        assert "stale" in result.stderr

    def test_refuses_a_results_file_that_is_not_json(self, tmp_path: Path) -> None:
        self._write(tmp_path, [{"name": "A", "issues": []}])
        (tmp_path / "build" / "narrativetrace" / "clarity-results.json").write_text("{")
        assert self._run(tmp_path).returncode == 1

    @pytest.mark.parametrize("scenarios", ['"x"', "null", "{}"])
    def test_refuses_scenarios_that_are_not_a_nonempty_list(
        self, tmp_path: Path, scenarios: str
    ) -> None:
        self._write(tmp_path, [{"name": "A", "issues": []}])
        results = tmp_path / "build" / "narrativetrace" / "clarity-results.json"
        results.write_text('{"scenarios": ' + scenarios + "}", encoding="utf-8")
        assert self._run(tmp_path).returncode == 1


class TestTheRules:
    def test_never_lowers_a_threshold_to_hide_a_failure(self) -> None:
        assert any("threshold" in r.rule.lower() for r in ADD_NARRATIVETRACE_CLARITY.never)

    def test_never_calls_a_scan_that_found_nothing_a_pass(self) -> None:
        assert any("found nothing" in r.rule for r in ADD_NARRATIVETRACE_CLARITY.never)

    def test_never_harvests_a_glossary_just_to_read_vocabulary(self) -> None:
        assert any("glossary" in r.rule.lower() for r in ADD_NARRATIVETRACE_CLARITY.never)

    def test_always_renames_in_snake_case_because_the_suggestions_examples_are_camel_case(
        self,
    ) -> None:
        assert any(
            "snake_case" in r.rule and "camelCase" in r.reason
            for r in ADD_NARRATIVETRACE_CLARITY.always
        )

    def test_hands_a_tracing_problem_to_the_doctor(self) -> None:
        assert "narrativetrace-doctor" in ADD_NARRATIVETRACE_CLARITY.description
