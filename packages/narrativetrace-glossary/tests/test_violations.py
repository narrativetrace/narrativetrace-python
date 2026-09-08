# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Aggregating suppressed alias observations into reportable vocabulary violations."""

from __future__ import annotations

from datetime import date

import pytest
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    HarvestCandidate,
    SynonymAlias,
    TermKind,
    TermStatus,
    VocabularyViolation,
    aggregate_violations,
    build_alias_index,
    merge_harvest,
)

_CANONICAL = GlossaryTerm(
    "open overdraft account",
    "billing",
    TermKind.VERB_PHRASE,
    TermStatus.CURATED,
    synonyms=[SynonymAlias("open account with overdraft")],
    first_seen=date(2020, 1, 1),
)

_GLOSSARY = Glossary({"billing": BoundedContext("billing", ["acme.billing"])}, [_CANONICAL])


def _candidate(identifier: str, site: str, occurrences: int = 1) -> HarvestCandidate:
    return HarvestCandidate(
        "billing",
        "open account with overdraft",
        TermKind.VERB_PHRASE,
        site,
        identifier,
        occurrences,
    )


def test_aggregates_a_suppressed_observation_into_a_violation_with_a_rename_suggestion() -> None:
    candidate = _candidate("open_account_with_overdraft", "OverdraftService.open", occurrences=3)
    aliases = build_alias_index(_GLOSSARY)

    violations = aggregate_violations([candidate], aliases)

    assert violations == (
        VocabularyViolation(
            context="billing",
            alias="open account with overdraft",
            canonical_term="open overdraft account",
            kind=TermKind.VERB_PHRASE,
            site="OverdraftService.open",
            identifier="open_account_with_overdraft",
            occurrences=3,
            suggested_rename="open_overdraft_account",
        ),
    )


def test_orders_violations_by_context_then_alias_then_site_then_identifier() -> None:
    aliases = build_alias_index(_GLOSSARY)
    first = _candidate("b_identifier", "A.a")
    second = _candidate("a_identifier", "A.a")

    violations = aggregate_violations([first, second], aliases)

    assert [v.identifier for v in violations] == ["a_identifier", "b_identifier"]


def test_empty_input_yields_no_violations() -> None:
    assert aggregate_violations([], build_alias_index(_GLOSSARY)) == ()


def test_raises_when_a_candidate_is_not_actually_an_alias_of_the_given_index() -> None:
    stray = HarvestCandidate("billing", "unrelated phrase", TermKind.WORD, "A.a", "unrelated")
    with pytest.raises(KeyError):
        aggregate_violations([stray], build_alias_index(_GLOSSARY))


def test_end_to_end_through_a_real_merge() -> None:
    candidate = _candidate("open_account_with_overdraft", "OverdraftService.open")
    result = merge_harvest(_GLOSSARY, [candidate], clock=lambda: date(2026, 8, 11))

    violations = aggregate_violations(result.suppressed_alias_uses, build_alias_index(_GLOSSARY))

    assert len(violations) == 1
    assert violations[0].canonical_term == "open overdraft account"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("context", ""),
        ("alias", ""),
        ("canonical_term", ""),
        ("site", ""),
        ("identifier", ""),
    ],
)
def test_rejects_a_blank_field(field: str, value: str) -> None:
    fields: dict[str, object] = {
        "context": "billing",
        "alias": "account with overdraft",
        "canonical_term": "overdraft account",
        "kind": TermKind.NOUN_PHRASE,
        "site": "A.a",
        "identifier": "id",
        "occurrences": 1,
        "suggested_rename": "overdraft_account",
    }
    fields[field] = value
    with pytest.raises(ValueError, match=rf"\A{field} must not be blank\Z"):
        VocabularyViolation(**fields)  # type: ignore[arg-type]


def test_rejects_non_positive_occurrences() -> None:
    with pytest.raises(ValueError, match=r"occurrences must be at least 1: 0"):
        VocabularyViolation("billing", "alias", "term", TermKind.WORD, "A.a", "id", 0, "term")
