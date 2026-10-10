# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Which catalogue skill fixes each class of doctor finding — the table
:func:`~narrativetrace_tooling.doctor.finding.passed`/:func:`~narrativetrace_tooling.doctor.finding.failed`
read to fill in :attr:`~narrativetrace_tooling.doctor.types.Finding.skill`. Mirrors the Java port's
``FindingSkills``.

INTENT: a finding tells a person what is wrong and how to fix it; an agent with the skills installed
can also be told WHICH tested procedure to follow next, by name, instead of improvising one. That
mapping belongs in one greppable place, not sprinkled across every check where a new check can
quietly ship without anybody deciding.

**@llmNote** The rule behind the table: a check that fires because the INSTALL is incomplete points
at ``add-narrative-tracing`` (it owns the dependency block, the redaction-marker rule and the pytest
plugin wiring); a check that fires on an already-wired project behaving wrongly points at
``narrativetrace-doctor`` (its steps own proving redaction, reading a rendered trace, and the
approval-trace flow). Approval mode switched off under committed baselines points at
``narrativetrace-verify``, whose pin step is where the switch is thrown. Two ids carry NO skill, and
that is a decision rather than an omission: no skill upgrades a Python interpreter, and no skill can
install the skills.
"""

from __future__ import annotations

from typing import Final

from narrativetrace_tooling.frameworks.table import wiring_check_ids

ADD_NARRATIVE_TRACING: Final = "add-narrative-tracing"
"""The skill a first install follows: dependencies, the redaction-marker rule, plugin wiring."""

NARRATIVETRACE_DOCTOR: Final = "narrativetrace-doctor"
"""The skill a wired-but-misbehaving project follows: diagnosis, read-only."""

NARRATIVETRACE_VERIFY: Final = "narrativetrace-verify"
"""The skill that reads what a change did and pins it: its pin step turns approval mode on and
promotes the first baselines behind the user's yes."""

_BY_ID: Final[dict[str, str]] = {
    "toolchain.pytest-version": ADD_NARRATIVE_TRACING,
    "toolchain.package-versions": ADD_NARRATIVE_TRACING,
    "config.pytest-plugin-registered": ADD_NARRATIVE_TRACING,
    "config.output-env": NARRATIVETRACE_DOCTOR,
    "config.unknown-keys": NARRATIVETRACE_DOCTOR,
    "config.approval-mode": NARRATIVETRACE_VERIFY,
    "trap.parameter-names": ADD_NARRATIVE_TRACING,
    "trap.silent-sink": NARRATIVETRACE_DOCTOR,
    "trap.redaction-proof": NARRATIVETRACE_DOCTOR,
    "trap.approval-traces": NARRATIVETRACE_DOCTOR,
    "trap.llms-before-you-start": ADD_NARRATIVE_TRACING,
    # Every config.<framework>-* check, derived from the framework table: the skill's one framework
    # step runs the doctor and applies each fix, so a new row can never ship undecided.
    **dict.fromkeys(wiring_check_ids(), ADD_NARRATIVE_TRACING),
}

_NO_SKILL: Final = frozenset(
    {
        # No skill upgrades a Python interpreter: the fix is pyenv, uv's own toolchain, or a CI
        # image.
        "toolchain.python-version",
        # The finding IS that the skills are absent; naming one would point at a missing page.
        "config.skills-installed",
    }
)


def for_check(check_id: str) -> str | None:
    """The catalogue skill that fixes this class of finding, or ``None`` when none does."""
    return _BY_ID.get(check_id)


def knows(check_id: str) -> bool:
    """Whether the table has a decision — a skill or a deliberate none — for this check id."""
    return check_id in _BY_ID or check_id in _NO_SKILL
