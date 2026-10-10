# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The hard gate: every :class:`~narrativetrace_tooling.feedback.rules.ValueFreeRule` over every
field of a report, before anything exists that a person could file.

Ports Java ``ValueFreeCheck``. INTENT: with no private inbox, a filed report is public from the
first second — so the check runs BEFORE the draft, the URL and the body file exist, and the verb
refuses to produce any of them while a violation stands. A gate that ran afterwards would be a
warning, and a warning on this path is a leak with a note attached.

**@llmNote** Every rule is reported, not the first: a report that leaks two different shapes should
be fixed once, not twice. Order is field order then rule order, so the same report always refuses in
the same words — which is what lets a test assert on them.

**@llmNote** Which rules apply is a property of the FIELD, not of the report: see
:data:`DOCTOR_REPORT_FIELD` for the one exemption and why it exists. :func:`rules_refusing` is the
text-scoped reading with no field to exempt, and it is what the shared
``hostile-corpus/feedback.json`` replay uses — so a corpus row's verdict never depends on which
field a value happened to arrive in.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Final

from narrativetrace_tooling.feedback.rules import ALL_RULES, MARKER, ValueFreeRule

DOCTOR_REPORT_FIELD: Final = "doctor report"
"""The field whose text is the doctor's OWN generated JSON, and the one field
:data:`~narrativetrace_tooling.feedback.rules.MARKER` cannot read.

The doctor's check vocabulary NAMES the redaction marker: ``trap.redaction-proof`` is the check "a
test asserts the literal ``[REDACTED]``", and its message, its fix AND its pass message all quote
that literal. So one rule, read against this one field, refused every report from every project
that has NarrativeTrace installed at all, and the verb could draft nothing. Found in Java's
milestone 2 by running the real verb against a real project, after 654 green tests missed it — the
hand-written doctor report every test started from paraphrased the finding, and a paraphrase has no
marker in it.

**@llmNote** Named by a string because that is what a field map is keyed by, so this constant and
the report's own field names have to agree: a renamed field silently re-arms the rule. The report
type asserts it carries exactly this key."""


@dataclass(frozen=True, slots=True)
class ValueFreeViolation:
    """One refusal: the report field that carried the offending text, and the rule that refused it.

    INTENT: a refusal has to be actionable. "This report cannot be filed" sends a person looking
    through every field; "``happened`` breaks ``vf.rendered-call``" sends them to one line.
    """

    field: str
    rule: ValueFreeRule

    def __post_init__(self) -> None:
        if self.rule is None:
            raise TypeError("a violation names the rule that refused it, never None")
        if not self.field or not self.field.strip():
            raise ValueError("a violation names the field it was found in")

    def describe(self) -> str:
        """The one line a refusal prints: the field, the rule id, and what to do about it."""
        return f"{self.field}: {self.rule.id} — {self.rule.reason}"


def rules_refusing(text: str) -> tuple[ValueFreeRule, ...]:
    """Every rule that refuses this one piece of text, in rule order; empty means it may be filed.

    Text-scoped, with no field to exempt — see this module's docstring.

    :raises TypeError: when ``text`` is ``None`` — an absent field is ``""``
    """
    if text is None:
        raise TypeError('the gate reads text, never None — an absent field is ""')
    return tuple(rule for rule in ALL_RULES if rule.rejects(text))


def violations(fields: Mapping[str, str]) -> tuple[ValueFreeViolation, ...]:
    """Every violation across a report's named fields, in field order then rule order.

    :param fields: field name to its text, in the order a refusal should list them
    :raises TypeError: when the mapping or any value is ``None`` — the drafter represents an absent
        field as ``""``, so a ``None`` here is a caller's bug and must not be read as empty: a field
        read as empty is a field no rule looked at
    """
    if fields is None:
        raise TypeError("the gate reads a report's fields, never None")
    found: list[ValueFreeViolation] = []
    for name, text in fields.items():
        if text is None:
            raise TypeError(f'field "{name}" is None — an absent field is ""')
        readable = _readable(name, text)
        found.extend(
            ValueFreeViolation(name, rule) for rule in _rules_for(name) if rule.rejects(readable)
        )
    return tuple(found)


def _readable(field_name: str, text: str) -> str:
    """The text the rules read for one field: the field itself, except the doctor's report, which
    is read as the strings its JSON carries, one per line.

    INTENT: JSON escapes a newline as the two characters ``\\n``, so a framework fix line that
    starts with a Python decorator reads, raw, as ``…\\n@app.get(`` — and ``n@app.get`` is an
    email address to the email rule: every report from a FastAPI project was refused. Decoded, the
    decorator starts its own line again. No rule is weaker on the decoded strings (an email, a home
    path or a credential in a message is still there, an escaped control character is now the
    character itself). Keys are read too — the doctor's are fixed names, but the gate never assumes
    what a field may carry. A report that is not JSON is read as it is.
    """
    if field_name != DOCTOR_REPORT_FIELD:
        return text
    try:
        document = json.loads(text)
    except (ValueError, RecursionError):
        return text
    return "\n".join(_strings_in(document))


def _strings_in(document: object) -> Iterator[str]:
    """Every string — each key, then its value — depth first in document order; iterative, so no
    nesting depth the parser accepted can exhaust the stack here."""
    pending = [document]
    while pending:
        node = pending.pop()
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            pending.extend(reversed([part for item in node.items() for part in item]))
        elif isinstance(node, list):
            pending.extend(reversed(node))


def _rules_for(field_name: str) -> tuple[ValueFreeRule, ...]:
    """Which rules read ``field_name``.

    Every rule reads every field except this one pair, and the exemption is deliberately as narrow
    as it can be: the doctor's report is still read by the other nine, so an email, a home path, a
    credential shape or a rendered call line inside a doctor message is refused exactly as it would
    be anywhere else. What is exempt is one rule whose whole premise — "the marker only appears
    where a value was blanked" — is false for OUR OWN generated text about that marker.
    """
    if field_name != DOCTOR_REPORT_FIELD:
        return ALL_RULES
    return tuple(rule for rule in ALL_RULES if rule != MARKER)
