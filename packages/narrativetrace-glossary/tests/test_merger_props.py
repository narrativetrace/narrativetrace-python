# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for the merge safety properties.

Plan section 10 makes two of them binding for any glossary and any harvest: the merge is
**additive-only** — it never removes or rewrites an entry a human may have curated — and it is
**idempotent**, so a second run over unchanged code leaves the committed file byte-identical.
"""

from __future__ import annotations

from datetime import date

from glossary_strategies import glossaries, harvests
from hypothesis import given
from narrativetrace_glossary import (
    Glossary,
    HarvestCandidate,
    TermKey,
    TermStatus,
    build_alias_index,
    merge_harvest,
    write_glossary_json,
)
from narrativetrace_glossary.merger import _SOURCE_LIMIT
from narrativetrace_glossary.models import _invariant

TODAY = date(2026, 8, 11)


def _clock() -> date:
    return TODAY


@given(glossaries(), harvests())
def test_merging_never_removes_or_rewrites_an_existing_entry(
    existing: Glossary, harvest: list[HarvestCandidate]
) -> None:
    merged = merge_harvest(existing, harvest, clock=_clock).glossary

    assert set(existing.terms) <= set(merged.terms)
    assert dict(existing.contexts).items() <= dict(merged.contexts).items()
    assert merged.schema_version == existing.schema_version


@given(glossaries(), harvests())
def test_merging_the_same_harvest_twice_reproduces_the_bytes(
    existing: Glossary, harvest: list[HarvestCandidate]
) -> None:
    once = merge_harvest(existing, harvest, clock=_clock)
    twice = merge_harvest(once.glossary, harvest, clock=_clock)

    assert twice.glossary == once.glossary
    assert twice.new_terms == ()
    assert write_glossary_json(twice.glossary) == write_glossary_json(once.glossary)


@given(glossaries(), harvests())
def test_the_merged_glossary_is_always_structurally_consistent(
    existing: Glossary, harvest: list[HarvestCandidate]
) -> None:
    assert _invariant(merge_harvest(existing, harvest, clock=_clock).glossary)


@given(glossaries(), harvests())
def test_every_term_a_merge_adds_is_harvested_dated_and_bounded_in_sources(
    existing: Glossary, harvest: list[HarvestCandidate]
) -> None:
    result = merge_harvest(existing, harvest, clock=_clock)

    for term in result.new_terms:
        assert term.status is TermStatus.HARVESTED
        assert term.first_seen == TODAY
        assert len(term.sources) <= _SOURCE_LIMIT
        assert len(set(term.sources)) == len(term.sources)


@given(glossaries(), harvests())
def test_a_suppressed_alias_use_is_an_alias_and_never_becomes_a_term(
    existing: Glossary, harvest: list[HarvestCandidate]
) -> None:
    aliases = build_alias_index(existing)
    result = merge_harvest(existing, harvest, clock=_clock)

    added = {TermKey.of(term) for term in result.new_terms}
    for suppressed in result.suppressed_alias_uses:
        key = TermKey(suppressed.context, suppressed.phrase)
        assert key in aliases
        assert key not in added


@given(glossaries(), harvests())
def test_every_observation_is_either_suppressed_known_or_newly_added(
    existing: Glossary, harvest: list[HarvestCandidate]
) -> None:
    known = {TermKey.of(term) for term in existing.terms}
    result = merge_harvest(existing, harvest, clock=_clock)

    added = {TermKey.of(term) for term in result.new_terms}
    suppressed = {TermKey(use.context, use.phrase) for use in result.suppressed_alias_uses}
    for candidate in harvest:
        key = TermKey(candidate.context, candidate.phrase)
        assert key in known or key in added or key in suppressed
