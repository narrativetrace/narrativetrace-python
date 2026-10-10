# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Behaviour the registry work implemented but no test reached — the milestone's adversarial pass,
kept down to the cases that close a real gap.

Dropped from the generated set, deliberately: everything that re-tested ``pathlib``, everything
already pinned by ``test_run.py``, ``test_registry_delivery.py`` or
``test_isolated_agent_config.py`` under a different name, and two tests whose NAMES claimed more
than their bodies did (one created the ledger's parent directory itself and then asserted the
writer had, one passed ``{}`` while claiming to pass ``None``).

Dropped because it passed for the WRONG reason, which is worth recording: a test asserting that
``--agent-command ""`` skips the agent step. An empty command is falsy, so it falls through to the
PLATFORM PRESET and the agent does run — the assertion only held because the Claude preset's
``argv[0]`` is ``claude``, which ``RecordingSpawn`` then classified as a pre-step program by NAME.
It classifies by role now (an agent turn is the call that streams into the transcript); see that
class's own note.
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import isolated_agent_config as config
import pytest
import registry_delivery as delivery
import run
from test_run import RecordingSpawn, _run_args


@pytest.fixture
def registry_case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A throwaway repo holding one registry case, with ``run.py``'s path constants and the real
    vendor configuration all pointed inside it. Returns ``(repo_root, case_dir)``."""
    repo_root = tmp_path / "repo"
    evals_dir = repo_root / "evals"
    case_dir = evals_dir / "skill" / "case"
    (case_dir / "graders").mkdir(parents=True)
    (case_dir / "prompt.md").write_text("prompt", encoding="utf-8")
    (case_dir / "case.json").write_text(
        '{"registry": "npx-skills", "fixture": "fixtures/demo"}', encoding="utf-8"
    )
    fixture = repo_root / "fixtures" / "demo"
    fixture.mkdir(parents=True)
    (fixture / "marker.txt").write_text("fixture-content", encoding="utf-8")
    real_config = tmp_path / "real-config"
    real_config.mkdir()
    (real_config / ".credentials.json").write_text('{"token":"t"}', encoding="utf-8")
    monkeypatch.setattr(run, "_REPO_ROOT", repo_root)
    monkeypatch.setattr(run, "_EVALS_DIR", evals_dir)
    monkeypatch.setattr(run, "real_config_dir", lambda: real_config)
    return repo_root, case_dir


def _deps(repo_root: Path, spy: RecordingSpawn) -> run.RunDeps:
    return run.RunDeps(
        spawn=spy, clock=lambda: date(2026, 10, 7), ledger_path=repo_root / "runs.jsonl"
    )


class TestTheVendorConfigurationsUnhappyShapes:
    def test_seeding_from_a_path_that_is_a_file_rather_than_a_directory_finds_no_login(
        self, tmp_path: Path
    ) -> None:
        """``HOME`` can point at anything. A configuration path that is a regular file has no login
        under it, which is the documented no-op rather than a crash — and a crash here would blame
        the harness for a machine's own arrangement."""
        not_a_directory = tmp_path / "claude"
        not_a_directory.write_text("this is a file", encoding="utf-8")

        assert config.seed_login(not_a_directory, tmp_path / "work") is False
        assert config.config_dir(tmp_path / "work").is_dir()


class TestTheCaseManifestsUnhappyShapes:
    def test_a_malformed_manifest_fails_loudly_rather_than_reading_as_no_registry(
        self, tmp_path: Path
    ) -> None:
        """Unparseable JSON must not fall through to "this case declares no registry": that would
        run a registry case as a plain prompt replay."""
        (tmp_path / "case.json").write_text("{broken json", encoding="utf-8")

        with pytest.raises(json.JSONDecodeError):
            delivery.registry_for_case(tmp_path)

    def test_a_registry_declared_as_a_number_is_refused_by_the_vocabulary(
        self, tmp_path: Path
    ) -> None:
        """The ``isinstance`` half of the guard, which no other test reaches: a JSON value of the
        wrong TYPE is as much outside the closed vocabulary as a misspelled id."""
        (tmp_path / "case.json").write_text('{"registry": 123}', encoding="utf-8")

        with pytest.raises(ValueError, match="123"):
            delivery.registry_for_case(tmp_path)

    def test_a_manifest_that_names_no_fixture_fails_at_the_read(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A case file somebody meant to fill in is an error, not a default: scaffolding "the
        skill's usual fixture" for a case that asked for a particular one would grade the wrong
        tree. (The message is a bare ``KeyError`` today — TODO carries naming the file.)"""
        evals_dir = tmp_path / "evals"
        case_dir = evals_dir / "skill" / "case"
        case_dir.mkdir(parents=True)
        (case_dir / "case.json").write_text('{"registry": "npx-skills"}', encoding="utf-8")
        monkeypatch.setattr(run, "_EVALS_DIR", evals_dir)

        with pytest.raises(KeyError):
            run._case_fixture("skill", "case")


class TestTheScaffoldsUnhappyShapes:
    def test_a_fixture_that_is_not_there_fails_rather_than_scaffolding_an_empty_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty scratch directory would reach the grader and fail every assertion for a reason
        the case never touched — a harness result wearing a product result's clothes."""
        monkeypatch.setattr(run, "_REPO_ROOT", tmp_path)

        with pytest.raises(FileNotFoundError):
            run._scaffold_fixture("fixtures/not-there")


class TestTheStagedSnapshotsArgvSafety:
    def test_a_path_with_spaces_stays_one_argv_element(self) -> None:
        """The staged tree lives under a temp directory whose name the harness does not choose. A
        path with a space in it has to arrive at ``git`` and ``tar`` as ONE argument — the property
        the argv-only seam exists for, asserted here against the exact lists."""
        commands = delivery.staging_commands(Path("/repo dir"), Path("/scratch dir/staged tree"))

        assert commands[0][2] == "/repo dir"
        assert commands[0][6] == "/scratch dir/staged tree.tar"
        assert commands[1] == (
            "tar",
            "-xf",
            "/scratch dir/staged tree.tar",
            "-C",
            "/scratch dir/staged tree",
        )


class TestTheAgentCommandTemplatesEdges:
    def test_a_template_with_no_prompt_placeholder_is_simply_tokenised(self) -> None:
        """An operator-supplied ``--agent-command`` that forgot ``{prompt}`` must not grow one: the
        command runs as written, and the trial's own log shows the agent got no prompt."""
        assert run._tokenize_agent_command("tool --flag value", "ignored") == [
            "tool",
            "--flag",
            "value",
        ]

    def test_every_prompt_placeholder_in_a_template_is_substituted(self) -> None:
        """``str.replace`` replaces all of them. Worth pinning rather than assuming: a template
        that names the prompt twice and got it once would send the agent half a task."""
        argv = run._tokenize_agent_command('tool "{prompt}" and "{prompt}"', "value")

        assert argv == ["tool", "value", "and", "value"]

    def test_an_empty_prompt_still_reaches_the_agent_as_an_argv_element(self) -> None:
        """It must not vanish from the argv: a command one argument short is a different command,
        and the agent's own refusal is the honest outcome."""
        assert run._tokenize_agent_command('echo "{prompt}"', "") == ["echo", ""]


class TestADefaultSpawnersEnvironmentMerge:
    def test_an_injected_entry_wins_over_the_same_key_in_the_ambient_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole isolation rests on this ORDER, and only at the real process boundary can it be
        proven: an operator running a trial with their own ``CLAUDE_CONFIG_DIR`` already exported
        must still get the trial's directory, not theirs."""
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/the/operators/own")
        script = (
            "import os, pathlib; "
            "pathlib.Path('seen.txt').write_text(os.environ['CLAUDE_CONFIG_DIR'])"
        )

        run.default_spawner(
            ["python3", "-c", script], tmp_path, {"CLAUDE_CONFIG_DIR": "/the/trials/own"}
        )

        assert (tmp_path / "seen.txt").read_text(encoding="utf-8") == "/the/trials/own"


class TestARegistryCaseCombinedWithTheOtherOutcomes:
    def test_a_grader_that_fails_after_a_green_pre_step_still_writes_a_fail_row(
        self, registry_case: tuple[Path, Path]
    ) -> None:
        """The two kinds of "not a pass" must stay distinct: a pre-step that failed delivered
        nothing and writes NO row, while a delivered tree the grader then rejected is a verdict and
        gets one."""
        repo_root, case_dir = registry_case
        spy = RecordingSpawn(grader_raises=subprocess.CalledProcessError(1, ["sh"]))

        run._run_one_trial(
            _run_args(skill="skill", case_name="case"),
            case_dir,
            "prompt",
            1,
            _deps(repo_root, spy),
        )

        row = json.loads((repo_root / "runs.jsonl").read_text(encoding="utf-8"))
        assert row["result"] == "fail"
        assert spy.pre_step_calls != []

    def test_an_agent_that_crashes_after_a_green_pre_step_writes_no_row(
        self, registry_case: tuple[Path, Path]
    ) -> None:
        """A registry case inherits the crash rule unchanged: the pre-step succeeding does not make
        a crashed agent command into a graded outcome."""
        repo_root, case_dir = registry_case
        spy = RecordingSpawn(agent_raises=subprocess.CalledProcessError(1, ["echo"]))

        with pytest.raises(subprocess.CalledProcessError):
            run._run_one_trial(
                _run_args(skill="skill", case_name="case"),
                case_dir,
                "prompt",
                1,
                _deps(repo_root, spy),
            )

        assert not (repo_root / "runs.jsonl").exists()
        assert spy.grader_calls == []

    def test_several_trials_of_one_case_record_their_own_outcomes(
        self, registry_case: tuple[Path, Path]
    ) -> None:
        """One row per trial, each its own verdict — not the last trial's repeated, and not one row
        for the run."""
        repo_root, _ = registry_case
        graded = [0]

        def _fail_the_second_grader(argv: list[str], cwd: Path, env: object) -> None:
            if argv[:1] == ["sh"]:
                graded[0] += 1
                if graded[0] == 2:
                    raise subprocess.CalledProcessError(1, ["sh"])

        spy = RecordingSpawn(on_call=_fail_the_second_grader)

        assert (
            run.run_trials(
                _run_args(skill="skill", case_name="case", trials=2), _deps(repo_root, spy)
            )
            == 0
        )

        rows = [
            json.loads(line)
            for line in (repo_root / "runs.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert [row["result"] for row in rows] == ["pass", "fail"]
        assert [row["trial"] for row in rows] == [1, 2]
