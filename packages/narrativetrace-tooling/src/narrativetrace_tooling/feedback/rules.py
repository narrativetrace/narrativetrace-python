# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The hard gate between a problem report and a leaked secret: one named rule per shape of runtime
value that must never reach a public issue.

Ports Java ``ValueFreeRule``. INTENT: a report drafted by an agent is PUBLIC from the first second —
there is no private inbox to triage it first — so the only thing standing between a pasted trace and
somebody's credential is a check the verb runs before it will build a URL or a body file. Each rule
carries a stable ``vf.*`` id because a refusal has to name what to fix, not just say no.

**@llmNote** Data here, code in :mod:`narrativetrace_tooling.feedback.matchers`: a rule is an id, a
reason a person reads, and a reference to the predicate that decides. Adding a rule means adding an
entry to :data:`ALL_RULES` and a predicate there, never an ``if`` inside a caller — the gate walks
this table and cannot know about a rule that is not in it.

**@llmNote** These rules are deliberately STRICTER than the runtime's own redaction
(``narrativetrace.redaction.RedactionPolicy``, which this library never links against). The renderer
refuses an entropy heuristic because a false positive there silently blanks a user's data; here a
false positive is a refusal that names its rule and a false negative is a public leak, so the
tradeoff inverts. ``narrativetrace-security-tests`` asserts the implication that matters — every
value the renderer redacts is also refused here — and asserts it in that direction ONLY.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from narrativetrace_tooling.feedback import matchers


@dataclass(frozen=True, slots=True)
class ValueFreeRule:
    """One rule: its stable id, the reason a refusal prints, and the predicate that decides.

    :param reason: why this shape may not be filed, in the words the refusal prints — it names
        what to do about it, because "this report cannot be filed" sends a person looking through
        every field
    :param refuses: the predicate from :mod:`narrativetrace_tooling.feedback.matchers`
    """

    id: str
    reason: str
    refuses: Callable[[str], bool]

    def rejects(self, text: str) -> bool:
        """Whether this rule refuses ``text``.

        :raises TypeError: when ``text`` is ``None`` — an absent field is ``""`` to every caller in
            this package, so ``None`` is a programming error rather than empty input, and reading
            it as empty would let a rule pass silently on a field nobody filled in
        """
        if text is None:
            raise TypeError('a value-free rule reads text, never None — an absent field is ""')
        return self.refuses(text)

    def __str__(self) -> str:
        return self.id


RENDERED_CALL: Final = ValueFreeRule(
    "vf.rendered-call",
    "a call line carries a parameter's VALUE — attach the structural trace (.nt) instead, which"
    " carries the same shape without any value",
    matchers.rendered_call,
)

RENDERED_OUTCOME: Final = ValueFreeRule(
    "vf.rendered-outcome",
    "an outcome arrow carries a RETURNED VALUE — the structural trace writes a bare → value, an"
    " exception TYPE after !!, or ?? incomplete, and never a value",
    matchers.rendered_outcome,
)

DURATION: Final = ValueFreeRule(
    "vf.duration",
    "an elapsed time is a runtime measurement, which means this text came from a rendered"
    " narrative rather than from the structural trace",
    matchers.duration,
)

MARKER: Final = ValueFreeRule(
    "vf.marker",
    "the redaction marker only appears where a value was redacted, so this text is a rendered"
    " narrative — the structural trace has nothing to redact and never carries it",
    matchers.marker,
)

NAMED_SECRET: Final = ValueFreeRule(
    "vf.named-secret",
    "a field whose NAME says it holds a credential is shown with a value beside it — remove the"
    " value; the name alone is shape and may stay",
    matchers.named_secret,
)

VALUE_SHAPE: Final = ValueFreeRule(
    "vf.value-shape",
    "a value here is shaped like a credential, a key, a national id or a card number — remove it;"
    " a report never needs the value, only what happened",
    matchers.value_shape,
)

ENTROPY: Final = ValueFreeRule(
    "vf.entropy",
    "a long encoded run here looks like a key, a hash or an opaque identifier — remove it; if it is"
    " genuinely not a secret, describe it in words instead of pasting it",
    matchers.entropy,
)

EMAIL: Final = ValueFreeRule(
    "vf.email",
    "an email address is personal data and a public issue is public forever — remove it; the report"
    " does not need to say who",
    matchers.email,
)

HOME_PATH: Final = ValueFreeRule(
    "vf.home-path",
    "an absolute home directory names the account it belongs to — the draft rewrites these to ~ on"
    " its own, so one here means the text was edited by hand afterwards",
    matchers.home_path,
)

CONTROL: Final = ValueFreeRule(
    "vf.control",
    "a control character is not text a reader needs and is how a payload hides in one — only a line"
    " feed and a tab belong in a report",
    matchers.control,
)

ALL_RULES: Final[tuple[ValueFreeRule, ...]] = (
    RENDERED_CALL,
    RENDERED_OUTCOME,
    DURATION,
    MARKER,
    NAMED_SECRET,
    VALUE_SHAPE,
    ENTROPY,
    EMAIL,
    HOME_PATH,
    CONTROL,
)
"""Every rule, in the order a refusal lists them. A tuple, so the same report always refuses in the
same words — which is what lets a test and a corpus row assert on them."""
