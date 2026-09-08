# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Hypothesis generators shared by the glossary property suites.

Generation is constructive — every sample satisfies the model invariants by design. Term texts are
globally unique, so ``(context, term)`` identity holds; alias texts always end in ``" alias"`` and
canonical texts never do, so alias/term disjointness holds without filtering. Harvest phrases are
drawn from both pools, so a generated run exercises new terms and deprecated-alias hits alike.

Not ``conftest.py``: pytest imports each package's conftest under a rootdir-derived name, and three
of them share that basename across this workspace, so a plain ``from conftest import ...`` would be
ambiguous. This module's basename is unique.
"""

from __future__ import annotations

from hypothesis import strategies as st
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    HarvestCandidate,
    SynonymAlias,
    TermKind,
    TermStatus,
)

CONTEXT_NAMES = ["billing", "support", "shipping", "_unassigned"]

# Texts chosen to exercise escaping in both targets at once: quotes and backslashes break JSON,
# pipes and line breaks break Markdown tables, non-ASCII must survive both unescaped.
TERM_TEXTS = [
    "alpha",
    "overdraft account",
    "café crédit",
    'say "hi" term',
    "back\\slash",
    "pipe | term",
    "multi\nline",
    "tabbed\tterm",
]

CURATED_TEXTS = ["Means something.", "Multi\nline é", 'a "quoted" | pipe', "x"]

ALIAS_TEXTS = [f"{text} alias" for text in TERM_TEXTS]
"""The alias spelling of every term text — a harvest of one of these must be suppressed."""

SITES = ["A.a", "B.b", "C.c", "D.d"]

ABBREVIATIONS = ["fx", "calc", "acc", "pipe|abbr", 'say "hi"']
"""Accepted shorthand, including texts that break JSON and Markdown if they escape unescaped."""


def bounded_context(name: str) -> BoundedContext:
    packages = [] if name.startswith("_") else [f"acme.{name}"]
    return BoundedContext(name, packages, f'Context "{name}"')


@st.composite
def synonyms(draw: st.DrawFn) -> list[SynonymAlias]:
    aliases = draw(st.lists(st.sampled_from(TERM_TEXTS), max_size=2, unique=True))
    notes = [draw(st.one_of(st.none(), st.sampled_from(CURATED_TEXTS))) for _ in aliases]
    return [
        SynonymAlias(f"{alias} alias", note) for alias, note in zip(aliases, notes, strict=True)
    ]


@st.composite
def terms(draw: st.DrawFn, text: str, context_names: list[str]) -> GlossaryTerm:
    return GlossaryTerm(
        text,
        draw(st.sampled_from(context_names)),
        draw(st.sampled_from(list(TermKind))),
        draw(st.sampled_from(list(TermStatus))),
        draw(st.one_of(st.none(), st.sampled_from(CURATED_TEXTS))),
        draw(
            st.dictionaries(
                st.sampled_from(["es", "de", "zh-CN"]), st.sampled_from(CURATED_TEXTS), max_size=2
            )
        ),
        draw(synonyms()),
        draw(st.lists(st.sampled_from(["a.b.c", "d.e.f"]), max_size=2, unique=True)),
        first_seen=draw(st.dates()),
    )


@st.composite
def glossaries(draw: st.DrawFn) -> Glossary:
    names = draw(st.lists(st.sampled_from(CONTEXT_NAMES), min_size=1, max_size=4, unique=True))
    texts = draw(st.lists(st.sampled_from(TERM_TEXTS), max_size=6, unique=True))
    return Glossary(
        {name: bounded_context(name) for name in names},
        [draw(terms(text, names)) for text in texts],
        draw(
            st.dictionaries(
                st.sampled_from(ABBREVIATIONS), st.sampled_from(CURATED_TEXTS), max_size=3
            )
        ),
        schema_version=draw(st.integers(min_value=1, max_value=3)),
    )


@st.composite
def harvest_candidates(draw: st.DrawFn) -> HarvestCandidate:
    return HarvestCandidate(
        draw(st.sampled_from(CONTEXT_NAMES)),
        draw(st.sampled_from(TERM_TEXTS + ALIAS_TEXTS)),
        draw(st.sampled_from(list(TermKind))),
        draw(st.sampled_from(SITES)),
        draw(st.sampled_from(["some_identifier", "otherIdentifier"])),
        draw(st.integers(min_value=1, max_value=5)),
    )


def harvests() -> st.SearchStrategy[list[HarvestCandidate]]:
    """One run's worth of observations, short enough that shrinking stays readable."""
    return st.lists(harvest_candidates(), max_size=8)
