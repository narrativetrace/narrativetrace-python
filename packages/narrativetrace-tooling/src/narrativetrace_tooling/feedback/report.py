# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""One problem report, gathered: which runtime and install, which part of the product, which step,
the three sentences, the language it is written in, who drafted it, and at most two attachments.

Ports Java's ``FeedbackReport`` and its parts. INTENT: the single object the gate, the draft, the
issue-form URL and the ``gh`` line all read, so none of them can disagree about what is being filed.
Every runtime in the family gathers the same fields under the same names — the issue form is shared,
so the field set is a cross-runtime contract, not a Python shape.

Guards follow this library's own rule: :class:`TypeError` when a required value is missing
altogether, :class:`ValueError` when a value is present and unusable.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Final

from narrativetrace_tooling.feedback.check import DOCTOR_REPORT_FIELD

_MANDATORY_TEXT: Final = ("runtime", "install", "step", "language")
"""The text fields a report cannot exist without. Named once, so the constructor's guard and the
invariant can never check different sets."""


class FeedbackCategory(Enum):
    """Which part of NarrativeTrace a report is about — the one field that decides where it is
    triaged and what it must carry.

    A closed set, not free text: the issue form renders it as a dropdown, the ``category:<id>``
    label comes from it, and :attr:`requires_doctor_report` is the one rule that depends on it.
    """

    PROMPT = ("prompt", False)
    """The published install prompt, or any text an adopter was told to follow."""

    SKILL = ("skill", True)
    """A catalogue skill: a step that does not work, a verify that cannot be met, wrong wording."""

    DOCTOR = ("doctor", True)
    """A doctor check: wrong finding, wrong fix, a fix that does not work."""

    LIBRARY = ("library", False)
    """The library itself: capture, rendering, redaction, an integration."""

    def __init__(self, category_id: str, requires_doctor_report: bool) -> None:
        self._id = category_id
        self._requires_doctor_report = requires_doctor_report

    @property
    def id(self) -> str:
        """The lower-case id the form's dropdown and the ``category:`` label carry."""
        return self._id

    @property
    def requires_doctor_report(self) -> bool:
        """Whether a report in this category is only meaningful with the doctor's JSON attached.

        Q3 as ruled: required for ``doctor`` and ``skill``, allowed to be absent for ``prompt`` and
        ``library``, where the project's build may not be able to run the doctor at all.
        """
        return self._requires_doctor_report

    @classmethod
    def of_id(cls, category_id: str) -> FeedbackCategory:
        """The category with this id.

        :raises ValueError: on an unknown id — a category is a closed set, and a silent fallback
            would file a report into the wrong triage queue
        """
        for category in cls:
            if category.id == category_id:
                return category
        raise ValueError(
            f'unknown category "{category_id}" — one of prompt, skill, doctor, library'
        )


@dataclass(frozen=True, slots=True)
class ProblemNarrative:
    """The three sentences that are the report: what was done, what happened, what was expected.

    INTENT: all three are mandatory, and that is the whole design of the field set. "It does not
    work" is not a report; the difference between what happened and what was expected is what makes
    one triageable without a conversation, and a conversation is exactly what nobody gets when the
    reporter is an agent that has already ended its session.
    """

    did: str
    happened: str
    expected: str

    def __post_init__(self) -> None:
        for name in ("did", "happened", "expected"):
            value = getattr(self, name)
            if value is None:
                raise TypeError(f'a report\'s "{name}" is text, never None')
            if not value.strip():
                raise ValueError(
                    f'a report\'s "{name}" must say something — all three sentences are mandatory'
                )


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    """Which agent product and model drafted the report, as the agent itself reports them.

    INTENT: triage needs to know whether a wording problem is one model's reading or everybody's.
    Neither field is verified and neither is required — an agent that will not name itself still
    gets to file — so "unknown" is ``""`` on both, never ``None`` and never a guess.
    """

    product: str
    model: str

    def __post_init__(self) -> None:
        if self.product is None or self.model is None:
            raise TypeError(
                'an unknown agent product or model is "", never None — see AgentIdentity.unknown()'
            )

    @classmethod
    def unknown(cls) -> AgentIdentity:
        """An agent that did not name itself."""
        return cls("", "")

    def describe(self) -> str:
        """The one line the report prints, or ``""`` when nothing is known."""
        if not self.product and not self.model:
            return ""
        return self.product if not self.model else f"{self.product} / {self.model}"


@dataclass(frozen=True, slots=True)
class Attachments:
    """The only two attachment kinds a report may carry: the doctor's own JSON report, and at most
    one structural trace.

    INTENT: a closed set, because every other artifact a project has carries runtime values. A
    rendered narrative, a log file and a source file are all refused by construction here rather
    than by a rule — there is no field to put them in.

    **@llmNote** :attr:`doctor_report` and :attr:`doctor_unavailable` are exclusive and exhaustive
    (Q3 as ruled): exactly one is non-empty. "No doctor report and no reason" would read, to triage,
    as a reporter who did not bother rather than as a project whose build cannot run the task — and
    those two get different answers.

    :param doctor_report: the doctor's JSON report verbatim, or ``""``
    :param doctor_unavailable: why there is no doctor report, or ``""`` when there is one
    :param structural_trace: one ``.nt`` file's content, or ``""``
    """

    doctor_report: str
    doctor_unavailable: str
    structural_trace: str

    def __post_init__(self) -> None:
        if (
            self.doctor_report is None
            or self.doctor_unavailable is None
            or self.structural_trace is None
        ):
            raise TypeError('an absent attachment is "", never None')
        if bool(self.doctor_report.strip()) == bool(self.doctor_unavailable.strip()):
            raise ValueError(
                "a report carries the doctor's JSON or says why it has none, never both and never"
                " neither"
            )

    @classmethod
    def of(cls, doctor_report: str, structural_trace: str) -> Attachments:
        """A report with the doctor's JSON, and optionally one structural trace."""
        return cls(doctor_report, "", structural_trace)

    @classmethod
    def without_doctor_report(cls, reason: str, structural_trace: str) -> Attachments:
        """A report whose project could not run the doctor, with the reason it could not."""
        return cls("", reason, structural_trace)

    @property
    def has_doctor_report(self) -> bool:
        return bool(self.doctor_report.strip())

    @property
    def has_structural_trace(self) -> bool:
        return bool(self.structural_trace.strip())


@dataclass(frozen=True, slots=True)
class FeedbackReport:
    """One gathered problem report.

    :param runtime: this runtime's own id — canonical, because it becomes a ``runtime:`` label
    :param install: the NarrativeTrace coordinates this project's build declares
    :param step: the doctor check id, the skill and step, or the prompt step number
    :param language: the BCP 47 tag of the language the report is written in (D8: the user's own
        language in the body; the form is English with a language field)
    """

    runtime: str
    category: FeedbackCategory
    install: str
    step: str
    narrative: ProblemNarrative
    language: str
    agent: AgentIdentity
    attachments: Attachments

    def __post_init__(self) -> None:
        self._require_parts()
        self._require_text()
        if not _runtime_is_label_shaped(self.runtime):
            raise ValueError(
                'a report\'s "runtime" becomes a runtime: label, so it must be lower case with no'
                f" spaces — got {self.runtime!r}"
            )
        if self.category.requires_doctor_report and not self.attachments.has_doctor_report:
            raise ValueError(
                f'a "{self.category.id}" report needs the doctor\'s JSON report — run the doctor,'
                " or file this under prompt or library instead"
            )
        assert _invariant(self), "a gathered report must describe one problem once"

    def _require_parts(self) -> None:
        if (
            self.category is None
            or self.narrative is None
            or self.agent is None
            or self.attachments is None
        ):
            raise TypeError(
                "a report needs a category, a narrative, an agent identity and an attachment set"
            )

    def _require_text(self) -> None:
        for name in _MANDATORY_TEXT:
            value: str | None = getattr(self, name)
            if value is None:
                raise TypeError(f'a report\'s "{name}" is text, never None')
            if not value.strip():
                raise ValueError(f'a report\'s "{name}" must not be blank')

    def fields(self) -> dict[str, str]:
        """Every field the gate inspects, in the order a refusal lists them.

        Insertion-ordered, so the same report always refuses in the same words — which is what lets
        a test assert on them. Deliberately EVERY field that reaches a URL or a body file, including
        the install coordinate and the agent line: those two look harmless and are the two a
        wrapper script is most likely to interpolate something into.
        """
        return {
            "install": self.install,
            "step": self.step,
            "did": self.narrative.did,
            "happened": self.narrative.happened,
            "expected": self.narrative.expected,
            "agent": self.agent.describe(),
            DOCTOR_REPORT_FIELD: self.attachments.doctor_report,
            "trace": self.attachments.structural_trace,
        }

    def with_fields(self, **overrides: Any) -> FeedbackReport:
        """This report with the named fields replaced — every guard runs again on the copy."""
        return replace(self, **overrides)


def _runtime_is_label_shaped(runtime: str) -> bool:
    """Whether this runtime id can become a ``runtime:<id>`` label the host will accept."""
    return runtime == runtime.lower() and " " not in runtime


def _attachments_are_consistent(report: FeedbackReport) -> bool:
    """The attachment set's own exclusivity, and the category's rule about it."""
    attachments = report.attachments
    return attachments.has_doctor_report == (not attachments.doctor_unavailable.strip()) and (
        attachments.has_doctor_report or not report.category.requires_doctor_report
    )


def _invariant(report: FeedbackReport) -> bool:
    """Returns whether a report is in a state the rest of the verb may rely on.

    The categories that apply here, of the nine: no blank mandatory text; a canonical runtime
    (lower case, no spaces) because it becomes a label; the attachment set's own exclusivity; the
    category's doctor-report rule; and no field that is ``None``, because the gate represents an
    absent field as ``""`` and would read a ``None`` as a field nobody inspected.

    Constructor guards make this true for every live instance; tests re-check it around each case.
    """
    return (
        all(getattr(report, name).strip() for name in _MANDATORY_TEXT)
        and _runtime_is_label_shaped(report.runtime)
        and _attachments_are_consistent(report)
        and all(text is not None for text in report.fields().values())
    )
