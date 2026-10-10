# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace feedback`` through the launcher, driven with injected dependencies so no case
spawns a process or reaches a network.

The project is a real temporary directory — the verb's visible effect is two files, and a fake
filesystem would prove only that the fake agrees with itself. The ``gh`` answer is injected
(:data:`~narrativetrace.doctor.cli_bin.CliDeps.gh_authenticated`), so both of its branches are
reached here while all four outcomes of the probe itself are tested in
``test_gh_auth_probe.py`` — neither file starts a process.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from narrativetrace.doctor.cli_bin import CliDeps, run_cli
from narrativetrace.doctor.feedback_cli import (
    BODY_FILE,
    DOCTOR_UNAVAILABLE,
    DRAFT_FILE,
    NO_GH,
    OUTPUT_DIRECTORY,
)
from narrativetrace_tooling.doctor.types import DoctorSnapshot, PackageInfo
from narrativetrace_tooling.feedback.matchers import REDACTION_MARKER

_REQUIRED = (
    "--category",
    "doctor",
    "--step",
    "trap.redaction-proof",
    "--did",
    "ran the doctor, applied the fix it printed, ran it again",
    "--happened",
    "the same check still failed, with the same message",
    "--expected",
    "the check to pass once the test asserts the marker",
)

_STRUCTURAL_TRACE = """scenario: Order is placed

- OrderService.place_order(customer_id, total)
  - Inventory.reserve(sku) → value
"""


class Run:
    """One launcher invocation's dependencies and everything it wrote, per stream."""

    def __init__(
        self,
        project: Path,
        *,
        gh_signed_in: bool = False,
        snapshot: DoctorSnapshot | None = None,
    ) -> None:
        self.project = project
        self.out: list[str] = []
        self.err: list[str] = []
        self.gh_asked = 0
        self._gh_signed_in = gh_signed_in
        self._snapshot = snapshot if snapshot is not None else a_snapshot(project)

    def _gh_authenticated(self) -> bool:
        self.gh_asked += 1
        return self._gh_signed_in

    def cli(self, *argv: str) -> int:
        deps = CliDeps(
            cwd=str(self.project),
            env={},
            build_snapshot=lambda cwd, env: self._snapshot,
            open_carrier=_unreachable_carrier,
            project_version=lambda: "0.2.0",
            log=self.out.append,
            error=self.err.append,
            gh_authenticated=self._gh_authenticated,
        )
        return run_cli(list(argv), deps)

    def feedback(self, channel: str, *argv: str) -> int:
        return self.cli("feedback", channel, *_REQUIRED, *argv)

    @property
    def stdout(self) -> str:
        return "\n".join(self.out)

    @property
    def stderr(self) -> str:
        return "\n".join(self.err)

    def written(self, relative: str) -> str:
        return (self.project / relative).read_text(encoding="utf-8")


def _unreachable_carrier(from_path: str | None) -> Any:
    raise AssertionError("the feedback verb must not open a skills carrier")


def a_snapshot(project: Path, **overrides: Any) -> DoctorSnapshot:
    """A project the doctor can read, with one attachable structural trace."""
    arguments: dict[str, Any] = {
        "cwd": str(project),
        "python_version": "3.12.4",
        "env": {},
        "root_pyproject": {"project": {"name": "orders", "dependencies": ["narrativetrace"]}},
        "narrativetrace_config": {},
        "source_files": {"tests/test_orders.py": "def test_orders() -> None:\n    assert True\n"},
        "output_files": {"structural/OrderServiceTest/order_is_placed.nt": _STRUCTURAL_TRACE},
        "installed_packages": {
            "narrativetrace": PackageInfo(name="narrativetrace", version="0.2.0")
        },
    }
    arguments.update(overrides)
    return DoctorSnapshot(**arguments)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    directory = tmp_path / "project"
    directory.mkdir()
    return directory


class TestTheDraftChannel:
    def test_prints_the_whole_draft_and_writes_both_files(self, project: Path) -> None:
        run = Run(project)

        assert run.feedback("draft") == 0
        assert "# NarrativeTrace problem report (draft — nothing has been filed)" in run.stdout
        assert run.written(BODY_FILE) in run.written(DRAFT_FILE)
        assert f"Written to {DRAFT_FILE} and {BODY_FILE}." in run.stdout

    def test_the_printed_draft_is_the_file_byte_for_byte(self, project: Path) -> None:
        """A draft the agent SHOWS and a draft on disk that differ is the one thing a report's
        approval cannot survive."""
        run = Run(project)
        run.feedback("draft")

        assert run.written(DRAFT_FILE) in run.stdout

    def test_the_report_carries_what_the_project_resolved(self, project: Path) -> None:
        run = Run(project)
        run.feedback("draft")

        assert "- install: narrativetrace==0.2.0" in run.written(BODY_FILE)
        assert "- runtime: python" in run.written(BODY_FILE)

    def test_it_attaches_the_doctors_own_generated_report(self, project: Path) -> None:
        run = Run(project)
        run.feedback("draft")

        body = run.written(BODY_FILE)

        assert '"trap.redaction-proof"' in body
        assert REDACTION_MARKER in body, "the doctor's own check text names the marker"

    def test_it_attaches_one_structural_trace(self, project: Path) -> None:
        run = Run(project)
        run.feedback("draft")

        assert "- OrderService.place_order(customer_id, total)" in run.written(BODY_FILE)

    def test_a_project_with_no_attachable_trace_says_why(self, project: Path) -> None:
        run = Run(project, snapshot=a_snapshot(project, output_files={}))

        assert run.feedback("draft") == 0
        assert "No structural trace attached: no structural trace was found" in run.stdout

    def test_a_named_trace_is_honoured(self, project: Path) -> None:
        run = Run(project)

        assert run.feedback("draft", "--trace", "order_is_placed.nt") == 0
        assert "No structural trace attached" not in run.stdout

    def test_the_json_envelope_names_the_verb_the_files_and_the_exit_code(
        self, project: Path
    ) -> None:
        run = Run(project)

        assert run.feedback("draft", "--json") == 0

        envelope = json.loads(run.stdout)

        assert envelope["verb"] == "draft"
        assert envelope["status"] == "drafted"
        assert envelope["draftFile"] == DRAFT_FILE
        assert envelope["bodyFile"] == BODY_FILE
        assert envelope["runtime"] == "python"
        assert envelope["exitCode"] == 0


class TestTheUrlChannel:
    def test_prints_the_pre_filled_url_and_how_to_use_it(self, project: Path) -> None:
        run = Run(project)

        assert run.feedback("url") == 0
        assert "https://github.com/narrativetrace/narrativetrace-python/issues/new?" in run.stdout
        assert f"paste the contents of {BODY_FILE}" in run.stdout
        assert "Filing on GitHub is public" in run.stdout

    def test_the_body_file_is_written_so_there_is_something_to_paste(self, project: Path) -> None:
        run = Run(project)
        run.feedback("url")

        assert (project / BODY_FILE).is_file()

    def test_the_json_envelope_carries_the_url_and_the_body_file(self, project: Path) -> None:
        run = Run(project)

        assert run.feedback("url", "--json") == 0

        envelope = json.loads(run.stdout)

        assert envelope["verb"] == "url"
        assert envelope["url"].startswith("https://github.com/")
        assert envelope["bodyFile"] == BODY_FILE

    def test_it_never_asks_gh_anything(self, project: Path) -> None:
        """The one outward-facing question belongs to the one channel that needs it."""
        run = Run(project)
        run.feedback("url")

        assert run.gh_asked == 0


class TestTheGhChannel:
    def test_prints_the_exact_line_when_gh_is_signed_in(self, project: Path) -> None:
        run = Run(project, gh_signed_in=True)

        assert run.feedback("gh") == 0
        assert "gh issue create --repo narrativetrace/narrativetrace-python" in run.stdout
        assert f"--body-file {BODY_FILE}" in run.stdout
        assert "That line is printed, not run." in run.stdout

    def test_it_exits_one_and_points_at_the_url_when_gh_cannot_be_used(self, project: Path) -> None:
        """An unavailable channel is a fact, not an error: exit 1 means the verb ran and this path
        is not open."""
        run = Run(project, gh_signed_in=False)

        assert run.feedback("gh") == 1
        assert run.stderr == NO_GH
        assert run.stdout == ""

    def test_it_asks_gh_exactly_once(self, project: Path) -> None:
        run = Run(project, gh_signed_in=True)
        run.feedback("gh")

        assert run.gh_asked == 1

    def test_the_json_envelope_carries_the_command(self, project: Path) -> None:
        run = Run(project, gh_signed_in=True)

        assert run.feedback("gh", "--json") == 0

        envelope = json.loads(run.stdout)

        assert envelope["verb"] == "gh"
        assert envelope["command"].startswith("gh issue create ")
        assert envelope["exitCode"] == 0

    def test_the_json_envelope_says_unavailable_with_the_exit_code_in_it(
        self, project: Path
    ) -> None:
        run = Run(project, gh_signed_in=False)

        assert run.feedback("gh", "--json") == 1

        envelope = json.loads(run.stderr)

        assert envelope["status"] == "unavailable"
        assert envelope["exitCode"] == 1


class TestTheGateIsTheVerbsHardGate:
    def test_a_report_carrying_a_value_exits_two_and_names_the_rule(self, project: Path) -> None:
        run = Run(project)

        exit_code = run.cli(
            "feedback",
            "draft",
            "--category",
            "doctor",
            "--step",
            "trap.redaction-proof",
            "--did",
            'it rendered as OrderService.place_order(id: "C-1")',
            "--happened",
            "it failed",
            "--expected",
            "it to pass",
        )

        assert exit_code == 2
        assert "This report cannot be filed." in run.stderr
        assert "did: vf.rendered-call" in run.stderr

    def test_nothing_is_written_while_a_violation_stands(self, project: Path) -> None:
        """The gate runs BEFORE the draft, the URL and the body file exist. A gate that ran
        afterwards would be a warning, and a warning on this path is a leak with a note."""
        run = Run(project)

        run.cli(
            "feedback",
            "url",
            "--category",
            "doctor",
            "--step",
            "trap.redaction-proof",
            "--did",
            "ada@example.com hit it",
            "--happened",
            "it failed",
            "--expected",
            "it to pass",
        )

        assert not (project / OUTPUT_DIRECTORY).exists()

    def test_the_refusal_json_names_every_field_rule_and_reason(self, project: Path) -> None:
        run = Run(project)

        exit_code = run.cli(
            "feedback",
            "gh",
            "--json",
            "--category",
            "doctor",
            "--step",
            "trap.redaction-proof",
            "--did",
            f"ada@example.com saw {REDACTION_MARKER} in the output",
            "--happened",
            "it failed",
            "--expected",
            "it to pass",
        )

        assert exit_code == 2

        envelope = json.loads(run.stderr)

        assert envelope["verb"] == "gh"
        assert envelope["status"] == "refused"
        assert [v["rule"] for v in envelope["violations"]] == ["vf.marker", "vf.email"]
        assert all(v["field"] == "did" for v in envelope["violations"])
        assert all(v["reason"] for v in envelope["violations"])
        assert envelope["exitCode"] == 2

    def test_a_home_path_is_normalised_rather_than_refused(self, project: Path) -> None:
        """Normalisation runs BEFORE the gate, so the one mistake nobody makes on purpose costs a
        rewrite rather than a refusal — and the verb's output is where that order is visible."""
        run = Run(project)

        exit_code = run.cli(
            "feedback",
            "draft",
            "--category",
            "doctor",
            "--step",
            "trap.redaction-proof",
            "--did",
            "ran it from /Users/ada/work/orders",
            "--happened",
            "it failed",
            "--expected",
            "it to pass",
        )

        assert exit_code == 0
        assert "ran it from ~/work/orders" in run.written(BODY_FILE)
        assert "/Users/ada" not in run.written(DRAFT_FILE)

    def test_a_refused_gh_report_never_reaches_the_probe(self, project: Path) -> None:
        """The gate is first, so a refused report does not even get as far as asking whether the
        channel is open."""
        run = Run(project, gh_signed_in=True)

        run.cli(
            "feedback",
            "gh",
            "--category",
            "doctor",
            "--step",
            "s",
            "--did",
            "[REDACTED]",
            "--happened",
            "h",
            "--expected",
            "e",
        )

        assert run.gh_asked == 0


class TestAProjectTheDoctorCannotRead:
    def test_a_prompt_report_may_still_be_filed_and_says_why_there_is_no_doctor_json(
        self, project: Path
    ) -> None:
        """Q3 as ruled: allowed for the prompt and library categories, when the doctor cannot run
        at all."""
        run = Run(project, snapshot=a_snapshot(project, root_pyproject=None))

        exit_code = run.cli(
            "feedback",
            "draft",
            "--category",
            "prompt",
            "--step",
            "step 2 of the install prompt",
            "--did",
            "followed the prompt as published",
            "--happened",
            "step 2 named a file that does not exist",
            "--expected",
            "the file the step names to be there",
        )

        assert exit_code == 0
        assert f"No doctor report: {DOCTOR_UNAVAILABLE}" in run.written(BODY_FILE)

    def test_a_doctor_report_is_refused_without_the_doctors_json(self, project: Path) -> None:
        run = Run(project, snapshot=a_snapshot(project, root_pyproject=None))

        exit_code = run.cli(
            "feedback",
            "draft",
            "--category",
            "doctor",
            "--step",
            "trap.redaction-proof",
            "--did",
            "ran the doctor",
            "--happened",
            "it failed",
            "--expected",
            "it to pass",
        )

        assert exit_code == 2
        assert "needs the doctor's JSON report" in run.stderr


class TestTheLauncherSurface:
    def test_the_top_level_usage_lists_the_feedback_verb(self, project: Path) -> None:
        run = Run(project)

        assert run.cli("--help") == 0
        assert "  narrativetrace feedback" in run.stdout
        assert "  feedback   Drafts a problem report" in run.stdout

    def test_the_verbs_own_usage_names_the_three_channels_and_the_exit_codes(
        self, project: Path
    ) -> None:
        run = Run(project)

        assert run.cli("feedback", "--help") == 0
        for channel in ("draft", "url", "gh"):
            assert f"  {channel}  " in run.stdout
        assert (
            "Exit 0 = drafted, 1 = that channel is not available, 2 = could not run" in run.stdout
        )

    def test_a_missing_flag_exits_two_with_the_verbs_usage(self, project: Path) -> None:
        run = Run(project)

        assert run.cli("feedback", "draft") == 2
        assert "--category needs a value" in run.stderr
        assert "narrativetrace feedback <draft|url|gh> [options]" in run.stderr

    def test_the_verb_never_opens_a_skills_carrier(self, project: Path) -> None:
        """Asserted by the dependency raising: a verb that asked for one would be reaching for
        something it has no business reading."""
        run = Run(project)

        assert run.feedback("draft") == 0


class TestWritingTheTwoFiles:
    def test_a_filesystem_that_refuses_exits_one_rather_than_crashing(self, project: Path) -> None:
        """Exit 1, not 2: the command was typed correctly, it could not do the work. The launcher's
        whole contract is to return an exit code."""
        blocker = project / "build"
        blocker.write_text("not a directory\n", encoding="utf-8")
        run = Run(project)

        assert run.feedback("draft") == 1
        assert f"could not write under {OUTPUT_DIRECTORY}" in run.stderr

    def test_a_second_run_overwrites_rather_than_appending(self, project: Path) -> None:
        run = Run(project)
        run.feedback("draft")
        first = run.written(BODY_FILE)

        run.feedback("draft")

        assert run.written(BODY_FILE) == first
