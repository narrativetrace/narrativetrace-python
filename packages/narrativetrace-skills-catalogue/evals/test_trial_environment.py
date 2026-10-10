# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A trial's evidence -- the transcript and the recording stand-ins' log -- lives OUTSIDE the
scaffolded project, and only the grader is told where. Ports Java's ``TrialEnvironmentTest``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import isolated_agent_config
import pytest
from trial_environment import TrialEnvironment

_AMBIENT_PATH = "/usr/local/bin:/usr/bin:/bin"


def _stand_in(environment: TrialEnvironment, name: str) -> Path:
    return Path(environment.agent_environment["PATH"].split(":")[0]) / name


class TestTheEvidence:
    def test_lives_in_the_work_directory_and_never_in_the_project(self, tmp_path: Path) -> None:
        work = tmp_path / "work"

        environment = TrialEnvironment.under(work, _AMBIENT_PATH)

        assert environment.transcript == work / "transcript.jsonl"
        assert environment.blocked_invocations == work / "gh-invocations.log"

    def test_the_agent_is_never_told_where_its_own_evidence_is(self, tmp_path: Path) -> None:
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)

        told = " ".join(environment.agent_environment.values())

        assert "transcript.jsonl" not in told
        assert "gh-invocations.log" not in told
        assert "NARRATIVETRACE_TRANSCRIPT" not in environment.agent_environment
        assert "NARRATIVETRACE_GH_LOG" not in environment.agent_environment

    def test_the_grader_is_told_where_both_pieces_are_on_top_of_the_agents_environment(
        self, tmp_path: Path
    ) -> None:
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)

        grader = environment.grader_environment

        assert grader["NARRATIVETRACE_TRANSCRIPT"] == str(environment.transcript)
        assert grader["NARRATIVETRACE_GH_LOG"] == str(environment.blocked_invocations)
        assert {k: grader[k] for k in environment.agent_environment} == (
            environment.agent_environment
        )

    def test_refuses_a_work_directory_whose_path_could_break_out_of_the_stand_ins_quoting(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match=r"\Aa trial's work directory may not carry a '"):
            TrialEnvironment.under(tmp_path / "it's", _AMBIENT_PATH)

        assert not (tmp_path / "it's").exists()


class TestTheAgentsEnvironment:
    def test_puts_the_stand_ins_first_on_path_with_the_inherited_path_behind_them(
        self, tmp_path: Path
    ) -> None:
        work = tmp_path / "work"

        environment = TrialEnvironment.under(work, _AMBIENT_PATH)

        assert environment.agent_environment["PATH"] == f"{work / 'bin'}:{_AMBIENT_PATH}"

    def test_runs_every_trial_against_a_throwaway_agent_configuration(self, tmp_path: Path) -> None:
        work = tmp_path / "work"

        environment = TrialEnvironment.under(work, _AMBIENT_PATH)

        assert environment.agent_environment["CLAUDE_CONFIG_DIR"] == str(
            isolated_agent_config.config_dir(work)
        )

    def test_writes_no_bytecode_into_a_committed_case_directory(self, tmp_path: Path) -> None:
        """A grader imports a shared helper beside it; without this, ``__pycache__`` lands in the
        repository the trial is testing."""
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)

        assert environment.agent_environment["PYTHONDONTWRITEBYTECODE"] == "1"


class TestTheTranscript:
    def test_records_each_turn_as_one_json_line_naming_the_turn_and_the_users_own_words(
        self, tmp_path: Path
    ) -> None:
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)

        environment.record_user_turn(1, "report this")
        environment.record_user_turn(2, "yes, file it")

        lines = environment.transcript.read_text(encoding="utf-8").splitlines()
        assert [json.loads(line) for line in lines] == [
            {"nt_turn": 1, "role": "user", "text": "report this"},
            {"nt_turn": 2, "role": "user", "text": "yes, file it"},
        ]

    def test_a_marker_stays_one_line_whatever_the_turns_text_carries(self, tmp_path: Path) -> None:
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)
        text = 'a "quoted"\nmulti-line\r\tprompt \\ with \x01 control'

        environment.record_user_turn(1, text)

        lines = environment.transcript.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["text"] == text

    def test_appends_after_what_the_agent_already_wrote(self, tmp_path: Path) -> None:
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)
        environment.record_user_turn(1, "first")
        with environment.transcript.open("a", encoding="utf-8") as handle:
            handle.write('{"type":"result","result":"done"}\n')

        environment.record_user_turn(2, "second")

        lines = environment.transcript.read_text(encoding="utf-8").splitlines()
        assert [json.loads(line).get("nt_turn") for line in lines] == [1, None, 2]


class TestKeepingTheEvidence:
    def test_copies_both_pieces_somewhere_durable_when_asked_to(self, tmp_path: Path) -> None:
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)
        environment.record_user_turn(1, "report this")
        environment.blocked_invocations.write_text("gh issue create\n", encoding="utf-8")
        destination = tmp_path / "kept" / "trial-1"

        kept = environment.keep_evidence_under(destination)

        assert kept == destination
        assert (destination / "transcript.jsonl").read_text(
            encoding="utf-8"
        ) == environment.transcript.read_text(encoding="utf-8")
        assert (destination / "gh-invocations.log").read_text(
            encoding="utf-8"
        ) == "gh issue create\n"

    def test_keeps_what_exists_and_does_not_invent_what_does_not(self, tmp_path: Path) -> None:
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)
        environment.record_user_turn(1, "report this")
        destination = tmp_path / "kept"

        environment.keep_evidence_under(destination)

        assert sorted(p.name for p in destination.iterdir()) == ["transcript.jsonl"]


def _run_stand_in(
    environment: TrialEnvironment, name: str, *args: str, path: str
) -> subprocess.CompletedProcess[str]:
    """Runs a stand-in the way an agent's shell would, under an explicit (often minimal) PATH."""
    return subprocess.run(  # nosec B603 - a fixed argv this test builds
        [str(_stand_in(environment, name)), *args],
        env={"PATH": path},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


class TestTheGhStandIn:
    def test_records_what_it_was_asked_and_files_nothing(self, tmp_path: Path) -> None:
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)
        bin_dir = str(_stand_in(environment, "gh").parent)

        result = _run_stand_in(
            environment,
            "gh",
            "issue",
            "create",
            "--title",
            "two words",
            path=f"{bin_dir}:{_AMBIENT_PATH}",
        )

        assert result.returncode == 0
        assert result.stdout == ""
        assert environment.blocked_invocations.read_text(encoding="utf-8") == (
            "gh issue create --title two words\n"
        )


class _RealCurl:
    """A stand-in for the REAL curl, placed BEHIND the trial's stub on PATH: it writes down that it
    was reached, with its argv, so a test can tell "served" from "blocked" without a network."""

    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True)
        self.reached = directory / "reached.log"
        script = directory / "curl"
        script.write_text(
            "#!/bin/sh\n"
            f"printf 'real curl' >> '{self.reached}'\n"
            f"for arg in \"$@\"; do printf ' %s' \"$arg\" >> '{self.reached}'; done\n"
            "printf 'llms body'\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        self.directory = directory

    def calls(self) -> str:
        return self.reached.read_text(encoding="utf-8") if self.reached.exists() else ""


class TestTheCurlStandIn:
    """Every test here runs under a MINIMAL PATH -- the stub's own directory and the fake real curl,
    nothing else. Java's first version called ``dirname``, a two-entry PATH had none, the stand-in
    could not recognise its own directory and exec'd itself for 39 minutes. Keep it minimal."""

    def _setup(self, tmp_path: Path) -> tuple[TrialEnvironment, _RealCurl, str]:
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)
        real = _RealCurl(tmp_path / "real-bin")
        minimal = f"{_stand_in(environment, 'curl').parent}:{real.directory}"
        return environment, real, minimal

    def test_serves_the_published_site_through_the_real_curl_behind_it(
        self, tmp_path: Path
    ) -> None:
        environment, real, path = self._setup(tmp_path)

        result = _run_stand_in(
            environment, "curl", "-sL", "https://narrativetrace.ai/python/llms.txt", path=path
        )

        assert result.returncode == 0
        assert result.stdout == "llms body"
        assert real.calls() == "real curl -sL https://narrativetrace.ai/python/llms.txt"
        assert environment.blocked_invocations.read_text(encoding="utf-8") == (
            "curl -sL https://narrativetrace.ai/python/llms.txt\n"
        )

    @pytest.mark.parametrize(
        "url",
        [
            "http://narrativetrace.ai",
            "https://narrativetrace.ai",
            "https://narrativetrace.ai/",
        ],
    )
    def test_serves_the_bare_site_on_either_scheme(self, tmp_path: Path, url: str) -> None:
        environment, real, path = self._setup(tmp_path)

        assert _run_stand_in(environment, "curl", url, path=path).returncode == 0
        assert real.calls() == f"real curl {url}"

    @pytest.mark.parametrize(
        "url",
        [
            "https://api.github.com/repos/narrativetrace/narrativetrace-python",
            "https://narrativetrace.ai.evil.example/llms.txt",
            "https://evil.example/https://narrativetrace.ai/",
            "https://narrativetrace.aix/llms.txt",
            "https://user@narrativetrace.ai.evil.example/",
        ],
    )
    def test_answers_could_not_resolve_host_for_any_other_host(
        self, tmp_path: Path, url: str
    ) -> None:
        environment, real, path = self._setup(tmp_path)

        result = _run_stand_in(environment, "curl", "-s", url, path=path)

        assert result.returncode == 6
        assert real.calls() == ""
        assert environment.blocked_invocations.read_text(encoding="utf-8") == f"curl -s {url}\n"

    def test_one_foreign_url_in_the_same_invocation_blocks_the_whole_request(
        self, tmp_path: Path
    ) -> None:
        environment, real, path = self._setup(tmp_path)

        result = _run_stand_in(
            environment,
            "curl",
            "https://narrativetrace.ai/python/llms.txt",
            "https://api.github.com/",
            path=path,
        )

        assert result.returncode == 6
        assert real.calls() == ""

    def test_an_invocation_naming_no_url_is_not_served(self, tmp_path: Path) -> None:
        environment, real, path = self._setup(tmp_path)

        result = _run_stand_in(environment, "curl", "--version", path=path)

        assert result.returncode == 6
        assert real.calls() == ""

    def test_with_nothing_but_itself_on_path_it_exits_instead_of_exec_ing_itself(
        self, tmp_path: Path
    ) -> None:
        environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)
        only_itself = str(_stand_in(environment, "curl").parent)

        result = _run_stand_in(
            environment, "curl", "https://narrativetrace.ai/python/llms.txt", path=only_itself
        )

        assert result.returncode == 6

    def test_a_second_copy_of_itself_on_path_is_not_mistaken_for_the_real_curl(
        self, tmp_path: Path
    ) -> None:
        """The same file reached through another directory -- a symlinked bin dir -- is still the
        stand-in, and the recursion guard stops it rather than the shell's process limit."""
        environment, real, _ = self._setup(tmp_path)
        alias = tmp_path / "alias-bin"
        alias.symlink_to(_stand_in(environment, "curl").parent)
        path = f"{_stand_in(environment, 'curl').parent}:{alias}:{real.directory}"

        result = _run_stand_in(
            environment, "curl", "https://narrativetrace.ai/python/llms.txt", path=path
        )

        assert result.returncode == 0
        assert real.calls() == "real curl https://narrativetrace.ai/python/llms.txt"

    def test_a_copy_of_itself_further_down_path_stops_on_the_recursion_guard(
        self, tmp_path: Path
    ) -> None:
        """A COPY is a different file, so neither the directory nor ``-ef`` recognises it: only the
        marker the first stand-in exported stops the copy from serving -- or from looping."""
        environment, real, _ = self._setup(tmp_path)
        copy_dir = tmp_path / "copy-bin"
        copy_dir.mkdir()
        shutil.copy2(_stand_in(environment, "curl"), copy_dir / "curl")
        path = f"{_stand_in(environment, 'curl').parent}:{copy_dir}:{real.directory}"

        result = _run_stand_in(
            environment, "curl", "https://narrativetrace.ai/python/llms.txt", path=path
        )

        assert result.returncode == 6
        assert real.calls() == ""
        assert environment.blocked_invocations.read_text(encoding="utf-8").count("\n") == 2

    def test_both_stand_ins_record_into_the_same_log(self, tmp_path: Path) -> None:
        environment, _, path = self._setup(tmp_path)

        _run_stand_in(environment, "gh", "auth", "status", path=path)
        _run_stand_in(environment, "curl", "https://api.github.com/", path=path)

        assert environment.blocked_invocations.read_text(encoding="utf-8") == (
            "gh auth status\ncurl https://api.github.com/\n"
        )


def test_the_stand_ins_are_executable(tmp_path: Path) -> None:
    environment = TrialEnvironment.under(tmp_path / "work", _AMBIENT_PATH)

    for name in ("gh", "curl"):
        assert os.access(_stand_in(environment, name), os.X_OK)
