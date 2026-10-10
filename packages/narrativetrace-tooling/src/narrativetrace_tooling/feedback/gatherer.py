# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What the verb can learn about a project without being told: which NarrativeTrace it resolved, and
which structural trace is safe to attach.

Ports Java ``FeedbackGatherer``. INTENT: the two facts triage needs most are the two a reporter is
least likely to get right by hand. The install coordinate decides whether a defect is already fixed;
the structural trace shows the shape of the call that misbehaved. Both are read from the doctor's
own snapshot, so the report and the doctor cannot disagree about the project they describe.

**@llmNote** A trace is chosen only if it is BOTH a structural trace by grammar and clean by every
value-free rule, and when none is, the choice says WHY rather than attaching nothing silently. A
report that quietly lost its attachment is a report whose author thinks they filed more than they
did.

**@sideEffects** None: pure functions over a snapshot. Running the doctor and reading the project is
the entry point's job, and the result is passed in here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from narrativetrace_tooling.doctor.types import DoctorSnapshot
from narrativetrace_tooling.feedback.check import rules_refusing
from narrativetrace_tooling.feedback.report import Attachments
from narrativetrace_tooling.feedback.structural_trace import looks_structural

INSTALL_UNKNOWN: Final = "no NarrativeTrace distribution is installed in this project"
"""What the install field says when the project resolved none of ours. A blank field would read, to
triage, as a verb that failed to look."""

_DISTRIBUTION_PREFIX: Final = "narrativetrace"

_STRUCTURAL_SUFFIX: Final = ".nt"


@dataclass(frozen=True, slots=True)
class TraceChoice:
    """Which structural trace was chosen, or why none was.

    :param content: the trace's content, or ``""`` when none was chosen
    :param reason: why nothing was chosen, or ``""`` when something was
    """

    content: str
    reason: str

    def __post_init__(self) -> None:
        if self.content is None or self.reason is None:
            raise TypeError("a trace choice is content or a reason, never None")
        if bool(self.content.strip()) == bool(self.reason.strip()):
            raise ValueError(
                "a choice attached a trace or says why it did not, never both and never neither"
            )


def install_coordinate(snapshot: DoctorSnapshot) -> str:
    """Every NarrativeTrace distribution this project resolved, with its version, or a stated
    unknown.

    **@llmNote** Sorted by distribution NAME rather than by the rendered ``name==version`` string.
    ``-`` sorts before ``=``, so sorting the rendered form puts ``narrativetrace-pytest`` ahead of
    the core distribution — stable, but not the order a reader expects, and triage reads this field
    first.

    **@llmNote** The distribution name is matched on the family prefix followed by nothing or a
    hyphen, never by ``startswith`` alone: ``narrativetracer`` is somebody else's package, and
    naming it in our own install coordinate would send triage after a version that is not ours.
    """
    ours = sorted(name for name in snapshot.installed_packages if _is_ours(name))
    if not ours:
        return INSTALL_UNKNOWN
    return ", ".join(f"{name}=={snapshot.installed_packages[name].version}" for name in ours)


def _is_ours(distribution: str) -> bool:
    return distribution == _DISTRIBUTION_PREFIX or distribution.startswith(
        f"{_DISTRIBUTION_PREFIX}-"
    )


def choose_trace(snapshot: DoctorSnapshot, preferred_path: str) -> TraceChoice:
    """The structural trace to attach.

    :param preferred_path: a path suffix the user named, or ``""`` to let the verb choose
    """
    candidates = _structural_candidates(snapshot)
    if preferred_path.strip():
        return _named(candidates, preferred_path)
    for content in candidates.values():
        if _is_attachable(content):
            return TraceChoice(content, "")
    return TraceChoice("", _refusal_for(candidates))


def attachments_for(
    snapshot: DoctorSnapshot, doctor_report_json: str, doctor_unavailable: str
) -> Attachments:
    """The attachment set: the doctor's JSON when there is one, and at most one structural trace.

    :param doctor_unavailable: why there is no doctor report; required when
        ``doctor_report_json`` is blank, because "no report and no reason" reads to triage as a
        reporter who did not bother rather than as a project whose build cannot run the doctor
    """
    trace = choose_trace(snapshot, "").content
    if doctor_report_json.strip():
        return Attachments.of(doctor_report_json, trace)
    return Attachments.without_doctor_report(doctor_unavailable, trace)


def _structural_candidates(snapshot: DoctorSnapshot) -> dict[str, str]:
    """Every ``.nt`` the snapshot saw, in path order so two runs choose the same one."""
    seen = {
        path: content
        for files in (snapshot.output_files, snapshot.approved_dir_files)
        for path, content in files.items()
        if path.endswith(_STRUCTURAL_SUFFIX)
    }
    return {path: seen[path] for path in sorted(seen)}


def _named(candidates: dict[str, str], preferred_path: str) -> TraceChoice:
    for path, content in candidates.items():
        if path.endswith(preferred_path):
            if _is_attachable(content):
                return TraceChoice(content, "")
            return TraceChoice("", f"{preferred_path} {_why_not(content)}")
    return TraceChoice("", f"{preferred_path} was not found under this project's output")


def _is_attachable(content: str) -> bool:
    return looks_structural(content) and not rules_refusing(content)


def _refusal_for(candidates: dict[str, str]) -> str:
    if not candidates:
        return "no structural trace was found under this project's output"
    path, content = next(iter(candidates.items()))
    return f"no attachable structural trace: {path} {_why_not(content)}"


def _why_not(content: str) -> str:
    """Why one candidate was not attachable, in the words the verb prints."""
    if not looks_structural(content):
        return "is not a structural trace"
    return "breaks " + ", ".join(rule.id for rule in rules_refusing(content))
