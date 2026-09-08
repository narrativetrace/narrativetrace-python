# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Reads a repository's committed glossary as the vocabulary clarity scores with.

``GlossaryVocabulary``. One file, one review workflow: the glossary a team already
curates (ADR-012) is the only place a project declares domain vocabulary — there is no second
clarity dictionary file to keep in sync.

Three rules make the mapping trustworthy. **Only the committed file counts** — nothing harvested
during the run itself is consulted; the commit is the human approval, and a self-expanding
vocabulary would make scores non-deterministic and self-certifying. **Deprecated synonyms are not
vocabulary** — an alias exists to be flagged, so promoting it would silence the very issue the
glossary declares it for. **``STALE`` terms are not vocabulary** — marking a term stale is an
explicit human statement that the word left the domain.

Bounded contexts are flattened: clarity scores identifiers, which carry no module path, so every
context's vocabulary applies everywhere. ``TEMPLATE`` entries are skipped — their text is raw
narration, not a word.

Accepted shorthand is read from the glossary's own ``abbreviations`` section (schema 2, Java item
43), never inferred from the tokens of a canonical term.
"""

from __future__ import annotations

from pathlib import Path

from narrativetrace_clarity import EMPTY, DomainVocabulary

from narrativetrace_glossary.json_reader import read_glossary_json
from narrativetrace_glossary.models import Glossary, GlossaryTerm, TermKind, TermStatus

GLOSSARY_FILE = "glossary.json"
"""Name of the committed glossary file, as the harvest writes it."""


def _collect(term: GlossaryTerm, verbs: set[str], nouns: set[str]) -> None:
    if term.status is TermStatus.STALE or term.kind is TermKind.TEMPLATE:
        return
    tokens = term.term.split(" ")
    if term.kind is TermKind.VERB_PHRASE:
        verbs.add(tokens[0])
        nouns.update(tokens[1:])
        return
    nouns.update(tokens)


def glossary_vocabulary(glossary: Glossary) -> DomainVocabulary:
    """Maps a glossary onto the vocabulary the clarity scorers consult.

    A verb phrase contributes its leading verb as a domain verb and the rest as domain nouns
    (``settle trade`` → verb ``settle``, noun ``trade``); words and noun phrases contribute every
    token as a domain noun. Multi-word terms therefore still teach, one token at a time, which is
    the granularity identifiers are scored at.

    Accepted shorthand comes from the glossary's ``abbreviations`` section and from nowhere else —
    the terms teach vocabulary, the section accepts abbreviations, and the two questions stay
    separate. The section is human-owned, so no status or kind filter applies to it.
    """
    verbs: set[str] = set()
    nouns: set[str] = set()
    for term in glossary.terms:
        _collect(term, verbs, nouns)
    return DomainVocabulary.of(verbs, nouns, glossary.abbreviations)


def read_project_vocabulary(glossary_dir: str | Path | None) -> DomainVocabulary:
    """Reads the committed glossary from the directory holding it.

    A ``None`` directory, a missing directory, and a directory with no ``glossary.json`` all mean
    the same thing — the project has declared no vocabulary — and yield the empty vocabulary. A
    glossary that exists but cannot be parsed is a different matter and raises, mirroring
    :func:`read_glossary_json`'s fail-loudly contract: a committed file with a typo is a defect,
    not an absence.
    """
    if glossary_dir is None:
        return EMPTY
    path = Path(glossary_dir) / GLOSSARY_FILE
    if not path.is_file():
        return EMPTY
    return glossary_vocabulary(read_glossary_json(path.read_text(encoding="utf-8")))
