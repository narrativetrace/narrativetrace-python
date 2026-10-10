# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The deciding half of :mod:`narrativetrace_tooling.feedback.rules`: one predicate per rule, each
testable on its own without building a report around it.

Ports Java ``ValueFreeMatchers``. Every pattern is compiled once, at import — a rule runs over every
field of every report the verb drafts, and this is the one path that must never be the slow one
somebody skips.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Final

from narrativetrace_tooling.feedback.vocabulary import contains_a_secret_shape, names_a_secret

RENDERED_CALL: Final = re.compile(r"\w+\.\w+[*_]{0,2}\([^)]*\b\w+:\s*\S")
r"""``Name.method(param: value`` — an identifier, a colon and something after it, inside a call
line's parentheses. The colon is what separates a rendered call from a structural one: the ``.nt``
form writes ``Name.method(param, param)`` and never a value.

The QUALIFYING type is required, which is a decided limit rather than an oversight: the rendered
artifact always writes ``Type.method(...)``, so a hand-typed ``place_order(id: "C-1")`` fragment is
reached only by its key's name, through the named-secret rule. Corpus row
``accepted-unqualified-rendered-call`` is that decision, and widening ``\w+\.`` to ``\w+`` would
flip it.

**@edgeCase** Every runtime's Markdown renderer bolds the qualified name (``- **Name.method**(param:
value)``), so one optional emphasis marker (``**``, ``__``, ``*``, ``_``) may sit between the method
and the parenthesis — written as a bounded class (``[*_]{0,2}``), never as the alternation
``(?:\*\*|__|\*|_)?``: overlapping alternatives are the shape a ReDoS gate rejects (Java's SpotBugs
does), and the stray mixed pair the class also admits only makes this deny rule stricter.
"""

RENDERED_OUTCOME: Final = re.compile(r"→\s*(?!value\b)\S")
"""An outcome arrow followed by something other than the structural literal ``value``. The other
two structural outcomes carry no arrow at all (``!! TypeName``, ``?? incomplete``), so they cannot
reach this pattern; a rendered return always does."""

DURATION: Final = re.compile(r"—\s*\d+(\.\d+)?\s?(ns|µs|ms|s)\b")
"""The rendered narrative's own duration suffix: an em dash, a number and a time unit. Anchored on
the em dash rather than on the number alone, so a version coordinate and a finding count — the two
numbers a legitimate report is full of — are not durations."""

REDACTION_MARKER: Final = "[REDACTED]"
"""The runtime's redaction marker, written out rather than imported: this library declares zero
dependencies and never links against the runtime it diagnoses (see
:mod:`narrativetrace_tooling.feedback`). ``narrativetrace-security-tests`` is the one package that
may see both, and it asserts this literal equals ``narrativetrace.redaction.REDACTED_MARKER``, so
the two cannot drift."""

KEYED_ASSIGNMENT: Final = re.compile(r"[\"']?([^\s\"':=]{1,80})[\"']?\s*[:=]\s*(?=\S)")
r"""One ``key: value`` or ``key=value`` binding, capturing the key. The key is bounded in length so
a pathological line cannot make this quadratic.

Three ADJACENCY bugs live here, and all three are the same class: something between the key and its
value made the scan read a key that is not the key. Each has a corpus row.

**@llmNote** The value is a LOOKAHEAD, not a consumed character. Consuming it ate the first letter
of the next key, so in an indented YAML paste the scan matched ``datasource:``, resumed inside
``password``, read the key as ``assword`` and let the credential through. Corpus row
``named-secret-yaml-indented``.

**@llmNote** The quotes are OPTIONAL rather than absent. A JSON key is ``"password": "hunter2"`` and
the closing quote sits between the key and the colon — so without them the one attachment every
report carries, the doctor's own JSON, was the one format the deny-list could not read at all.
Corpus row ``named-secret-json-quoted``.

**@llmNote** The key is "anything that is not a separator", NOT ``[\w.\-]`` as Java spells it, and
this is a REASONED PORT DIVERGENCE rather than a liberty. Java's ``UNICODE_CHARACTER_CLASS`` makes
``\w`` include the combining-mark categories (``Mn``/``Me``/``Mc``); Python's Unicode ``\w`` is
``str.isalnum()``-shaped and does not. So the decomposed spelling of ``contraseña`` — ``contrasen``
+ U+0303, which is what a Mac filesystem hands back — truncated at the mark, and the scan then read
the key as ``a``, which is in nobody's deny-list. Corpus row ``named-secret-spanish-decomposed``.
Defining the key by its SEPARATORS instead closes the whole class rather than that one mark: no
character can truncate a key when every non-separator belongs to it. It is also strictly wider than
Java's class, which is the safe direction for this gate — a near miss costs a sentence (see
:mod:`narrativetrace_tooling.feedback.vocabulary`)."""

BASE64_RUN: Final = re.compile(r"[A-Za-z0-9+=_]{32,}")
"""A run of base64 (and base64url ``_``) characters long enough to be an encoded secret.

**Neither SEPARATOR is a run character**, and both exclusions are the same decision: a character
ordinary text uses to join words is not part of one token, and admitting it makes every long piece
of ordinary text a secret.

**@llmNote** The HYPHEN is excluded though base64url uses it: it is what prose and this project's
own doc anchors separate words with, and ``the-quick-brown-fox-jumps-over-the-lazy`` measures 4.33
bits per character — above the ceiling. Corpus row ``accepted-hyphenated-prose``.

**@llmNote** The SLASH is excluded for the same reason, and this port is where that was found. Java
measures a path as one run and gets away with it because its doc URLs are short
(``narrativetrace.ai/docs/<slug>``); this runtime's are GitHub blob links, so one segment of the
doctor's own ``doc_url`` — ``python/blob/main/documentation/guides/configuration``, 51 characters at
**4.0303** bits per character — sat just over the ceiling. Every doctor report this port can
generate was refused, and so was any report whose prose quoted a doc URL. A path is several tokens,
not one; measuring it as one made the gate's tightest margin
(``accepted-structural-artifact-path``, 3.958) a hair's breadth rather than a decision.

**@edgeCase** The price, stated: a STANDARD-base64 secret whose own bytes happen to contain a slash
is split, and each half may fall under the length floor. That is the identical, already-accepted
price of excluding the hyphen — Java's own note says a hyphenated base64url token "is still reached
by its halves". Every credential whose SHAPE is known is caught by
:mod:`narrativetrace_tooling.feedback.vocabulary` regardless, and the four corpus rows this rule
exists for contain no slash."""

HEX_RUN: Final = re.compile(r"\b[0-9a-fA-F]{32,}\b")
"""A run of nothing but hex digits, long enough to be a hash, an HMAC or an opaque id.

**@llmNote** Entropy is not the discriminator for hex and cannot be: sixteen symbols cap Shannon
entropy at 4.0 bits per character, so :data:`ENTROPY_CEILING` can never fire on hex — which is half
of what the rule is for. Length alone carries the hex half: no word is 32 hex digits. Corpus row
``entropy-hex-run-32`` says so in its own description, so deleting this clause is a decision."""

ENTROPY_CEILING: Final = 4.0
"""Bits per character above which an encoded run is treated as a secret rather than a word."""

EMAIL: Final = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z]{2,}")
"""An email address. The local part must be non-empty, which is what keeps a decorator reference
(``@not_traced``) and a dependency extra (``narrativetrace[otel]``) off this rule."""

HOME_PATH: Final = re.compile(r"(/Users/|/home/)[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+", re.IGNORECASE)
"""The three platforms' home directories. Matched with a non-empty account segment — and, on the
POSIX spellings, a trailing separator — so ``/home`` alone, ``/usr/share/ada`` and a relative
``build/`` path are not home directories. A rewrite that was eager here would turn an ordinary path
into ``~`` and make a report wrong instead of safe."""

CONTROL: Final = re.compile(
    "[\\x00-\\x08\\x0b-\\x1f\\x7f-\\x9f\\u202a-\\u202e\\u2066-\\u2069\\ufeff]"
)
"""Every C0 and C1 control character except the line feed and the tab a report legitimately has,
plus Unicode's own bidirectional controls and the byte-order mark. Written as ESCAPES, never as the
characters themselves: a source file carrying a raw right-to-left override is the trojan-source
hazard this very rule exists to catch.

**@llmNote** The bidi characters are in scope because they are the attack the rule is for: a
right-to-left override in an issue title reorders what the person triaging it SEES without changing
a byte of what was filed. They carry the ``Bidi_Control`` property, so "control character" is their
own name for themselves, not a widening.

**@edgeCase** Deliberately NOT all of the ``Cf`` category. The zero-width joiner and non-joiner are
format characters too, and they are load-bearing letters in Devanagari, Bengali and emoji sequences
— refusing them would refuse a report written in Hindi, and reports may be in any language."""


def rendered_call(text: str) -> bool:
    return RENDERED_CALL.search(text) is not None


def rendered_outcome(text: str) -> bool:
    return RENDERED_OUTCOME.search(text) is not None


def duration(text: str) -> bool:
    return DURATION.search(text) is not None


def marker(text: str) -> bool:
    return REDACTION_MARKER in text


def named_secret(text: str) -> bool:
    """Whether a deny-listed name is immediately followed by a value.

    Anchored on the key being ASSIGNED, not on the word appearing anywhere: a report that says "the
    authorization header never arrived" is the report we want, and the key there is ``header``.
    """
    return any(names_a_secret(found.group(1)) for found in KEYED_ASSIGNMENT.finditer(text))


def value_shape(text: str) -> bool:
    return contains_a_secret_shape(text)


def entropy(text: str) -> bool:
    """Whether ``text`` carries an encoded run dense enough to be a key: the hex half decided by
    LENGTH, the base64 half by the density of its own alphabet (see :data:`HEX_RUN`)."""
    if HEX_RUN.search(text) is not None:
        return True
    return any(
        shannon_bits_per_character(run.group()) > ENTROPY_CEILING
        for run in BASE64_RUN.finditer(text)
    )


def email(text: str) -> bool:
    return EMAIL.search(text) is not None


def home_path(text: str) -> bool:
    return HOME_PATH.search(text) is not None


def control(text: str) -> bool:
    return CONTROL.search(text) is not None


def shannon_bits_per_character(run: str) -> float:
    """Shannon entropy of ``run``'s own character distribution, in bits per character.

    Part of this module's surface rather than private, because the margin it measures is the gate's
    tightest: a real structural-artifact path sits four hundredths of a bit under
    :data:`ENTROPY_CEILING`, and a test that could not read the number could only assert the
    verdict, never how close it came to flipping.

    An empty run has no entropy — the one input that would otherwise divide by zero.
    """
    length = len(run)
    if length == 0:
        return 0.0
    bits = 0.0
    for count in Counter(run).values():
        share = count / length
        bits -= share * math.log2(share)
    return bits
