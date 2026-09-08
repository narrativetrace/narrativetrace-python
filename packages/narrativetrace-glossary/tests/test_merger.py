# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Behaviour of merging a harvest into an existing glossary.

The merge rules of ADR-012: existing entries are never removed or rewritten, unseen
``(context, phrase)`` pairs join as harvested terms, and phrases matching a deprecated alias are
suppressed and reported instead of re-added.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime

import pytest
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    HarvestCandidate,
    MergeResult,
    SynonymAlias,
    TermKind,
    TermStatus,
    merge_harvest,
)
from narrativetrace_glossary.merger import _invariant as _merge_invariant

TODAY = date(2026, 8, 11)

EMPTY_BILLING = Glossary({"billing": BoundedContext("billing", ["acme.billing"])})


def _clock() -> date:
    return TODAY


def _candidate(context: str, phrase: str, site: str) -> HarvestCandidate:
    return HarvestCandidate(context, phrase, TermKind.NOUN_PHRASE, site, "some_identifier")


def _canonical_with_alias() -> GlossaryTerm:
    """A curated term that deprecates one phrasing, so harvests of that phrasing are suppressed."""
    return GlossaryTerm(
        "overdraft account",
        "billing",
        TermKind.NOUN_PHRASE,
        TermStatus.CURATED,
        synonyms=[SynonymAlias("account with overdraft")],
        first_seen=date(2020, 1, 1),
    )


def test_adds_an_unseen_phrase_as_a_harvested_term_dated_by_the_clock() -> None:
    harvest = [_candidate("billing", "overdraft account", "OverdraftService.open")]

    result = merge_harvest(EMPTY_BILLING, harvest, clock=_clock)

    assert result.new_terms == (
        GlossaryTerm(
            "overdraft account",
            "billing",
            TermKind.NOUN_PHRASE,
            TermStatus.HARVESTED,
            sources=["OverdraftService.open"],
            first_seen=TODAY,
        ),
    )
    assert result.glossary.terms == result.new_terms
    assert result.suppressed_alias_uses == ()


def test_stamps_today_in_utc_when_no_clock_is_injected() -> None:
    harvest = [_candidate("billing", "overdraft account", "OverdraftService.open")]

    before = datetime.now(UTC).date()
    result = merge_harvest(EMPTY_BILLING, harvest)
    after = datetime.now(UTC).date()

    assert result.new_terms[0].first_seen in {before, after}


def test_records_at_most_three_distinct_sites_for_a_new_term() -> None:
    harvest = [
        _candidate("billing", "overdraft account", site) for site in ("A.a", "B.b", "C.c", "D.d")
    ]

    result = merge_harvest(EMPTY_BILLING, harvest, clock=_clock)

    assert len(result.new_terms) == 1
    assert result.new_terms[0].sources == ("A.a", "B.b", "C.c")


def test_records_a_repeated_site_once() -> None:
    harvest = [_candidate("billing", "overdraft account", site) for site in ("A.a", "A.a", "B.b")]

    result = merge_harvest(EMPTY_BILLING, harvest, clock=_clock)

    assert result.new_terms[0].sources == ("A.a", "B.b")


def test_the_kind_of_the_first_observation_names_the_new_term() -> None:
    site = "OverdraftService.open"
    harvest = [
        HarvestCandidate("billing", "charge", TermKind.VERB_PHRASE, site, "charge"),
        HarvestCandidate("billing", "charge", TermKind.WORD, site, "charge"),
    ]

    result = merge_harvest(EMPTY_BILLING, harvest, clock=_clock)

    assert result.new_terms[0].kind is TermKind.VERB_PHRASE


def test_leaves_a_term_the_glossary_already_carries_completely_untouched() -> None:
    curated = GlossaryTerm(
        "overdraft account",
        "billing",
        TermKind.NOUN_PHRASE,
        TermStatus.CURATED,
        "Human definition.",
        {"es": "cuenta con descubierto"},
        sources=["Old.site"],
        first_seen=date(2020, 1, 1),
    )
    existing = Glossary(EMPTY_BILLING.contexts, [curated])
    harvest = [_candidate("billing", "overdraft account", "New.site")]

    result = merge_harvest(existing, harvest, clock=_clock)

    assert result.new_terms == ()
    assert result.glossary == existing
    assert result.glossary.terms[0] is curated


def test_declares_a_context_the_harvest_referenced_but_the_file_did_not() -> None:
    harvest = [_candidate("_unassigned", "ticket", "TicketDesk.open")]

    contexts = merge_harvest(EMPTY_BILLING, harvest, clock=_clock).glossary.contexts

    assert set(contexts) == {"billing", "_unassigned"}
    assert contexts["_unassigned"].packages == ()
    assert contexts["_unassigned"].description == "Harvested terms not yet mapped to a context"


def test_declares_any_other_missing_context_without_a_description() -> None:
    harvest = [_candidate("warehouse", "pallet", "Depot.store")]

    contexts = merge_harvest(EMPTY_BILLING, harvest, clock=_clock).glossary.contexts

    assert contexts["warehouse"].description is None


def test_keeps_the_schema_version_of_the_glossary_it_merged_into() -> None:
    existing = Glossary(EMPTY_BILLING.contexts, schema_version=7)
    harvest = [_candidate("billing", "overdraft account", "OverdraftService.open")]

    assert merge_harvest(existing, harvest, clock=_clock).glossary.schema_version == 7


def test_carries_the_accepted_abbreviations_through_a_harvest_untouched() -> None:
    """Accepted shorthand is human-owned, like a definition — a run never adds to or edits it."""
    existing = Glossary(EMPTY_BILLING.contexts, abbreviations={"fx": "foreign exchange"})
    harvest = [_candidate("billing", "overdraft account", "OverdraftService.open")]

    merged = merge_harvest(existing, harvest, clock=_clock).glossary

    assert dict(merged.abbreviations) == {"fx": "foreign exchange"}
    assert merged.schema_version == 2
    assert len(merged.terms) == 1


def test_suppresses_a_deprecated_alias_instead_of_adding_it_back() -> None:
    existing = Glossary(EMPTY_BILLING.contexts, [_canonical_with_alias()])
    alias_use = _candidate("billing", "account with overdraft", "AccountService.open")

    result = merge_harvest(existing, [alias_use], clock=_clock)

    assert result.new_terms == ()
    assert result.glossary == existing
    assert result.suppressed_alias_uses == (alias_use,)


def test_suppression_applies_only_in_the_context_that_deprecated_the_alias() -> None:
    contexts = {**EMPTY_BILLING.contexts, "support": BoundedContext("support", ["acme.support"])}
    existing = Glossary(contexts, [_canonical_with_alias()])
    billing_use = _candidate("billing", "account with overdraft", "AccountService.open")
    support_use = _candidate("support", "account with overdraft", "HelpDesk.describe")

    result = merge_harvest(existing, [billing_use, support_use], clock=_clock)

    assert result.suppressed_alias_uses == (billing_use,)
    assert [(term.term, term.context, term.status) for term in result.new_terms] == [
        ("account with overdraft", "support", TermStatus.HARVESTED)
    ]


def test_merging_nothing_leaves_the_glossary_as_it_was() -> None:
    result = merge_harvest(EMPTY_BILLING, [], clock=_clock)

    assert result.glossary == EMPTY_BILLING
    assert result.new_terms == ()
    assert result.suppressed_alias_uses == ()


def test_rejects_a_glossary_that_is_not_one() -> None:
    with pytest.raises(TypeError, match=r"\Aexisting must be a Glossary\Z"):
        merge_harvest([], [], clock=_clock)  # type: ignore[arg-type]


def test_rejects_a_clock_that_cannot_be_called() -> None:
    with pytest.raises(TypeError, match=r"\Aclock must be callable\Z"):
        merge_harvest(EMPTY_BILLING, [], clock=TODAY)  # type: ignore[arg-type]


@pytest.fixture
def local_timezone(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Runs the test under a named local timezone, restoring the process default afterwards."""
    monkeypatch.setenv("TZ", request.param)
    time.tzset()
    request.addfinalizer(time.tzset)


# UTC+14 and UTC-11: for any instant at least one of them is on a different calendar day than UTC,
# so a default clock reading local time instead of UTC fails one of these two runs.
@pytest.mark.parametrize(
    "local_timezone", ["Pacific/Kiritimati", "Pacific/Pago_Pago"], indirect=True
)
@pytest.mark.usefixtures("local_timezone")
def test_the_default_clock_dates_a_term_in_utc_not_in_local_time() -> None:
    harvest = [_candidate("billing", "overdraft account", "OverdraftService.open")]

    before = datetime.now(UTC).date()
    result = merge_harvest(EMPTY_BILLING, harvest)
    after = datetime.now(UTC).date()

    assert result.new_terms[0].first_seen in {before, after}


_TERM = GlossaryTerm(
    "overdraft account", "billing", TermKind.NOUN_PHRASE, TermStatus.HARVESTED, first_seen=TODAY
)
_MERGED = Glossary(EMPTY_BILLING.contexts, [_TERM])


def test_a_merge_that_kept_everything_and_added_one_new_term_is_consistent() -> None:
    assert _merge_invariant(MergeResult(_MERGED, [_TERM]), EMPTY_BILLING)


def test_a_merge_that_dropped_an_existing_term_or_context_is_inconsistent() -> None:
    had_term = Glossary(EMPTY_BILLING.contexts, [_TERM])
    assert not _merge_invariant(MergeResult(EMPTY_BILLING), had_term)

    had_context = Glossary({**EMPTY_BILLING.contexts, "support": BoundedContext("support")})
    assert not _merge_invariant(MergeResult(EMPTY_BILLING), had_context)


def test_a_merge_that_changed_the_schema_version_is_inconsistent() -> None:
    rewritten = Glossary(EMPTY_BILLING.contexts, schema_version=2)

    assert not _merge_invariant(MergeResult(rewritten), EMPTY_BILLING)


def test_a_merge_that_wrote_into_the_abbreviations_section_is_inconsistent() -> None:
    rewritten = Glossary(EMPTY_BILLING.contexts, abbreviations={"fx": "foreign exchange"})

    assert not _merge_invariant(MergeResult(rewritten), EMPTY_BILLING)


def test_a_merge_that_dropped_the_abbreviations_section_is_inconsistent() -> None:
    had_abbreviations = Glossary(EMPTY_BILLING.contexts, abbreviations={"fx": "foreign exchange"})

    assert not _merge_invariant(MergeResult(EMPTY_BILLING), had_abbreviations)


def test_a_merge_reporting_a_term_the_glossary_does_not_carry_is_inconsistent() -> None:
    assert not _merge_invariant(MergeResult(EMPTY_BILLING, [_TERM]), EMPTY_BILLING)


def test_a_merge_reporting_an_already_known_term_as_new_is_inconsistent() -> None:
    assert not _merge_invariant(MergeResult(_MERGED, [_TERM]), _MERGED)


def test_a_merge_that_both_suppressed_and_added_one_phrase_is_inconsistent() -> None:
    suppressed = _candidate("billing", "overdraft account", "AccountService.open")

    assert not _merge_invariant(MergeResult(_MERGED, [_TERM], [suppressed]), EMPTY_BILLING)
