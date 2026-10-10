# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace feedback`` — drafts a problem report about NarrativeTrace itself, checks it
carries no values, and shows the person how to file it.

Ports Java's ``FeedbackArguments``/``FeedbackVerb`` over the same tooling library. INTENT: the whole
decision is the user's, and this verb is built so that it cannot be anybody else's. It writes two
files and prints text. It opens no browser, runs no ``gh``, and makes no request of its own — the
only outward-facing thing it does is ask an already-installed ``gh`` whether it is signed in, and
only on the channel that would need it (:mod:`narrativetrace.doctor.gh_auth_probe`).

**@llmNote** Every channel re-drafts from the flags it was given rather than reading a draft back
from disk. That is deliberate: there is no hidden state between invocations, so a report can never
be filed under a draft that was edited after it was shown. "Never edit the draft after showing it —
draft it again and show it again" is enforced by there being nothing else to do.

**@llmNote** The doctor's JSON is produced by RUNNING the doctor over this project's snapshot, not
by reading a report file off disk. This runtime has no build task that writes one, and running it
means the attachment can never be a stale report from a tree that has since changed.

**@sideEffects** Writes ``build/narrativetrace/feedback/feedback-draft.md`` and ``feedback-body.md``
under the project, and only when the gate cleared the report.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from narrativetrace_tooling.doctor.doctor import run_doctor
from narrativetrace_tooling.doctor.render import render_json
from narrativetrace_tooling.feedback import (
    PRIVACY_NOTE,
    RUNTIME,
    AgentIdentity,
    Drafted,
    FeedbackCategory,
    FeedbackReport,
    ProblemNarrative,
    Refused,
    attachments_for,
    choose_trace,
    gh_command_line,
    install_coordinate,
    issue_form_url,
)
from narrativetrace_tooling.feedback import draft as draft_report

if TYPE_CHECKING:
    from narrativetrace.doctor.cli_bin import CliDeps
    from narrativetrace_tooling.doctor.types import DoctorSnapshot

CHANNELS: Final = ("draft", "url", "gh")
"""The three channels, in the order the skill offers them."""

OUTPUT_DIRECTORY: Final = "build/narrativetrace/feedback"
"""Where the two files land, relative to the project. Under ``build/`` because that is this
runtime's scratch directory, it is git-ignored by convention, and the doctor's own project walk
excludes it — so a drafted report never becomes an input to the next diagnosis."""

DRAFT_FILE: Final = f"{OUTPUT_DIRECTORY}/feedback-draft.md"
BODY_FILE: Final = f"{OUTPUT_DIRECTORY}/feedback-body.md"

NO_GH: Final = (
    "gh is not installed or not signed in. Use `narrativetrace feedback url` instead: it needs no"
    " tool and no credential beyond the browser you are already signed in to."
)
"""What to do instead when ``gh`` cannot be used. An unavailable channel is a fact, not an error."""

DOCTOR_UNAVAILABLE: Final = "the doctor could not run: no readable pyproject.toml at this project"
"""Why a report may carry no doctor JSON (Q3 as ruled, for the prompt and library categories)."""

_FIELD_FOR: Final[dict[str, str]] = {
    "--category": "category",
    "--step": "step",
    "--did": "did",
    "--happened": "happened",
    "--expected": "expected",
    "--language": "language",
    "--agent-product": "agent_product",
    "--agent-model": "agent_model",
    "--trace": "trace",
}
"""Every flag that takes a value, and the field it fills. Written out rather than derived from the
flag's spelling: the mapping is what makes "is this a flag at all" and "where does its value go"
one decision, so an unrecognised flag can never reach the state as a field nobody declared."""

_JSON: Final = "--json"
_HELP: Final = ("--help", "-h")


@dataclass(frozen=True, slots=True)
class FeedbackArguments:
    """What the verb was asked to do.

    :param channel: ``draft``, ``url`` or ``gh``
    :param trace: a path suffix naming the structural trace to attach, or ``""`` to let the verb
        choose
    :param error: why the command line could not be read, or ``None`` when it could
    """

    channel: str = ""
    category: str = ""
    step: str = ""
    did: str = ""
    happened: str = ""
    expected: str = ""
    language: str = "en"
    agent_product: str = ""
    agent_model: str = ""
    trace: str = ""
    as_json: bool = False
    help_wanted: bool = False
    error: str | None = None

    def report(self, snapshot: DoctorSnapshot, doctor_report_json: str) -> FeedbackReport:
        """The report these arguments and this project describe."""
        return FeedbackReport(
            runtime=RUNTIME,
            category=FeedbackCategory.of_id(self.category),
            install=install_coordinate(snapshot),
            step=self.step,
            narrative=ProblemNarrative(self.did, self.happened, self.expected),
            language=self.language,
            agent=AgentIdentity(self.agent_product, self.agent_model),
            attachments=attachments_for(snapshot, doctor_report_json, DOCTOR_UNAVAILABLE),
        )


def parse_feedback_arguments(arguments: Sequence[str]) -> FeedbackArguments:
    """Reads the arguments that follow the verb; the first of them is the channel.

    :raises TypeError: when no argument sequence is given
    """
    if arguments is None:
        raise TypeError("a command line is a sequence of arguments, never None")
    parsed = FeedbackArguments()
    index = 0
    while index < len(arguments):
        parsed, index = _read_one(parsed, arguments, index)
    return _validated(parsed)


def _read_one(
    parsed: FeedbackArguments, arguments: Sequence[str], index: int
) -> tuple[FeedbackArguments, int]:
    argument = arguments[index]
    if not argument.startswith("-") and not parsed.channel:
        return replace(parsed, channel=argument), index + 1
    name, separator, inline = argument.partition("=")
    if name in _HELP:
        return replace(parsed, help_wanted=True), index + 1
    if name == _JSON:
        return replace(parsed, as_json=True), index + 1
    if name not in _FIELD_FOR:
        return _failed(parsed, f'unknown option: "{argument}"'), index + 1
    value = inline if separator else _at(arguments, index + 1)
    if not value:
        return _failed(parsed, f"{name} needs a value"), index + 1
    return _valued(parsed, name, value), index + (1 if separator else 2)


def _valued(parsed: FeedbackArguments, name: str, value: str) -> FeedbackArguments:
    override: dict[str, Any] = {_FIELD_FOR[name]: value}
    return replace(parsed, **override)


def _failed(parsed: FeedbackArguments, message: str) -> FeedbackArguments:
    """Records why the line could not be read, keeping the FIRST problem found."""
    return parsed if parsed.error is not None else replace(parsed, error=message)


def _at(arguments: Sequence[str], index: int) -> str | None:
    return arguments[index] if index < len(arguments) else None


def _validated(parsed: FeedbackArguments) -> FeedbackArguments:
    """Everything a channel cannot run without, checked in the order a person types it.

    Asking for the usage short-circuits every other check: that is when somebody asks for it.
    """
    if parsed.help_wanted or parsed.error is not None:
        return parsed
    if parsed.channel not in CHANNELS:
        return _failed(parsed, _wrong_channel(parsed.channel))
    return _with_required_fields_checked(parsed)


def _wrong_channel(channel: str) -> str:
    if not channel:
        return f"feedback needs a channel: {', '.join(CHANNELS)}"
    return f'unknown feedback channel: "{channel}"'


def _with_required_fields_checked(parsed: FeedbackArguments) -> FeedbackArguments:
    checked = _with_category_checked(parsed)
    for flag in ("--step", "--did", "--happened", "--expected"):
        if not getattr(checked, flag.removeprefix("--")).strip():
            checked = _failed(checked, f"{flag} is required — a report without it says nothing")
    return checked


def _with_category_checked(parsed: FeedbackArguments) -> FeedbackArguments:
    if not parsed.category:
        return _failed(parsed, "--category needs a value: prompt, skill, doctor or library")
    try:
        FeedbackCategory.of_id(parsed.category)
    except ValueError as error:
        return _failed(parsed, str(error))
    return parsed


def run_feedback(rest: Sequence[str], deps: CliDeps, usage: str) -> int:
    """Runs the verb once argv has been recognised as ``feedback``. Returns the exit code."""
    parsed = parse_feedback_arguments(rest)
    if parsed.help_wanted:
        deps.log(usage)
        return 0
    if parsed.error is not None:
        deps.error(f"{parsed.error}\n\n{usage}")
        return 2
    try:
        return _draft_then_print(parsed, deps)
    except ValueError as error:
        deps.error(str(error))
        return 2
    except OSError as error:
        deps.error(f"could not write under {OUTPUT_DIRECTORY}: {error}")
        return 1


def _draft_then_print(parsed: FeedbackArguments, deps: CliDeps) -> int:
    snapshot = deps.build_snapshot(deps.cwd, deps.env)
    outcome = draft_report(parsed.report(snapshot, _doctor_report_json(snapshot)))
    if isinstance(outcome, Refused):
        deps.error(
            _refused_json(parsed, outcome) if parsed.as_json else outcome.describe().rstrip()
        )
        return 2
    _write(Path(deps.cwd), outcome)
    return _print(parsed, outcome, deps, choose_trace(snapshot, parsed.trace).reason)


def _doctor_report_json(snapshot: DoctorSnapshot) -> str:
    """The doctor's own report for this project, or ``""`` when it cannot run at all."""
    if snapshot.root_pyproject is None:
        return ""
    return render_json(run_doctor(snapshot))


def _print(parsed: FeedbackArguments, outcome: Drafted, deps: CliDeps, trace_note: str) -> int:
    if parsed.channel == "url":
        return _print_url(parsed, outcome, deps)
    if parsed.channel == "gh":
        return _print_gh(parsed, outcome, deps)
    return _print_draft(parsed, outcome, deps, trace_note)


def _print_draft(
    parsed: FeedbackArguments, outcome: Drafted, deps: CliDeps, trace_note: str
) -> int:
    if parsed.as_json:
        deps.log(
            _envelope(
                "draft",
                "drafted",
                0,
                draftFile=DRAFT_FILE,
                bodyFile=BODY_FILE,
                traceNote=trace_note,
                **_report_facts(outcome.report),
            )
        )
        return 0
    written = f"Written to {DRAFT_FILE} and {BODY_FILE}."
    note = f"\nNo structural trace attached: {trace_note}" if trace_note else ""
    deps.log(f"{outcome.draft}\n{written}{note}")
    return 0


def _print_url(parsed: FeedbackArguments, outcome: Drafted, deps: CliDeps) -> int:
    url = issue_form_url(outcome.report)
    if parsed.as_json:
        deps.log(_envelope("url", "ready", 0, url=url, bodyFile=BODY_FILE))
        return 0
    deps.log(
        f"{url}\n\nOpen that in your own browser, where you are already signed in, then paste the"
        f" contents of {BODY_FILE} into the report's last box and submit it.\n\n{PRIVACY_NOTE}"
    )
    return 0


def _print_gh(parsed: FeedbackArguments, outcome: Drafted, deps: CliDeps) -> int:
    if not deps.gh_authenticated():
        deps.error(_envelope("gh", "unavailable", 1, reason=NO_GH) if parsed.as_json else NO_GH)
        return 1
    command = gh_command_line(outcome.report, BODY_FILE)
    if parsed.as_json:
        deps.log(_envelope("gh", "ready", 0, command=command))
        return 0
    deps.log(
        f"{command}\n\nThat line is printed, not run. Running it files the report under your own"
        f" GitHub account.\n\n{PRIVACY_NOTE}"
    )
    return 0


def _report_facts(report: FeedbackReport) -> dict[str, str]:
    return {
        "runtime": report.runtime,
        "category": report.category.id,
        "install": report.install,
        "step": report.step,
        "language": report.language,
        "agent": report.agent.describe(),
    }


def _envelope(verb: str, status: str, exit_code: int, **members: str) -> str:
    """The ``--json`` envelope for one path. Every envelope names the verb it came from, because an
    agent that pipelines ``draft`` into ``url`` needs to tell which answer it is holding — and the
    exit code is in BOTH the envelope and the process, so neither reader has to infer it."""
    return json.dumps({"verb": verb, "status": status, **members, "exitCode": exit_code}, indent=2)


def _refused_json(parsed: FeedbackArguments, refused: Refused) -> str:
    return json.dumps(
        {
            "verb": parsed.channel,
            "status": "refused",
            "violations": [
                {"field": v.field, "rule": v.rule.id, "reason": v.rule.reason}
                for v in refused.violations
            ],
            "exitCode": 2,
        },
        indent=2,
    )


def _write(project: Path, outcome: Drafted) -> None:
    directory = project / OUTPUT_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    (project / DRAFT_FILE).write_text(outcome.draft, encoding="utf-8")
    (project / BODY_FILE).write_text(outcome.body, encoding="utf-8")
