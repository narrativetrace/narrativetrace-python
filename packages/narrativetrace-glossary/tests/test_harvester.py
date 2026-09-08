# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Behaviour of harvesting glossary candidates from captured trace trees.

The harvester is the bridge between traces and the glossary: it observes, aggregates, and orders
— it makes no merge decisions.
"""

from __future__ import annotations

import pytest
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    HarvestCandidate,
    TermKind,
    harvest_traces,
)
from narrativetrace_glossary.harvester import _invariant

from narrativetrace import (
    MethodSignature,
    ParameterCapture,
    Returned,
    Threw,
    TraceNode,
    TraceTree,
)

BILLING = Glossary({"billing": BoundedContext("billing", ["acme.billing"])})
"""One declared context, so a candidate's resolved context is visible in every assertion."""


def _module_of(class_name: str) -> str:
    """Files the overdraft classes in the billing context and everything else outside it."""
    return "acme.billing" if class_name.startswith("Overdraft") else "acme.support"


def _node(class_name: str, method_name: str, *parameter_names: str) -> TraceNode:
    parameters = [ParameterCapture(name, '"v"') for name in parameter_names]
    return TraceNode(MethodSignature(class_name, method_name, parameters))


def _harvest(*roots: TraceNode) -> tuple[HarvestCandidate, ...]:
    return harvest_traces([TraceTree(list(roots))], glossary=BILLING, module_of=_module_of)


class InsufficientFundsError(Exception):
    """Domain failure whose type name carries vocabulary worth harvesting."""


_BLANK_FIELDS = ["context", "phrase", "site", "identifier"]


def _candidate(**overrides: object) -> HarvestCandidate:
    fields: dict[str, object] = {
        "context": "billing",
        "phrase": "overdraft account",
        "kind": TermKind.NOUN_PHRASE,
        "site": "OverdraftService.open_account",
        "identifier": "overdraft_account_id",
    }
    fields.update(overrides)
    return HarvestCandidate(**fields)  # type: ignore[arg-type]


def test_candidate_records_where_and_how_often_a_phrase_was_observed() -> None:
    candidate = HarvestCandidate(
        "billing",
        "overdraft account",
        TermKind.NOUN_PHRASE,
        "OverdraftService.open_account",
        "overdraft_account_id",
    )

    assert candidate.context == "billing"
    assert candidate.phrase == "overdraft account"
    assert candidate.kind is TermKind.NOUN_PHRASE
    assert candidate.site == "OverdraftService.open_account"
    assert candidate.identifier == "overdraft_account_id"
    assert candidate.occurrences == 1


@pytest.mark.parametrize("field", _BLANK_FIELDS)
@pytest.mark.parametrize("blank", ["", "   "])
def test_rejects_a_blank_identity_field(field: str, blank: str) -> None:
    with pytest.raises(ValueError, match=rf"\A{field} must not be blank\Z"):
        _candidate(**{field: blank})


@pytest.mark.parametrize("occurrences", [0, -1])
def test_rejects_an_observation_that_never_happened(occurrences: int) -> None:
    with pytest.raises(ValueError, match=rf"\Aoccurrences must be at least 1: {occurrences}\Z"):
        _candidate(occurrences=occurrences)


def test_harvests_class_method_and_parameter_candidates_with_context_and_site() -> None:
    candidates = _harvest(
        _node("OverdraftService", "open_account_with_overdraft", "overdraft_account_id")
    )

    site = "OverdraftService.open_account_with_overdraft"
    assert candidates == (
        HarvestCandidate(
            "billing",
            "account with overdraft",
            TermKind.NOUN_PHRASE,
            site,
            "open_account_with_overdraft",
        ),
        HarvestCandidate(
            "billing",
            "open account with overdraft",
            TermKind.VERB_PHRASE,
            site,
            "open_account_with_overdraft",
        ),
        HarvestCandidate(
            "billing", "overdraft", TermKind.WORD, "OverdraftService", "OverdraftService"
        ),
        HarvestCandidate(
            "billing",
            "overdraft account",
            TermKind.NOUN_PHRASE,
            site,
            "overdraft_account_id",
        ),
    )


def test_harvests_the_exception_type_of_a_failed_node() -> None:
    failed = TraceNode(
        MethodSignature("OverdraftService", "charge"),
        outcome=Threw(InsufficientFundsError("boom")),
    )

    assert HarvestCandidate(
        "billing",
        "insufficient fund",
        TermKind.NOUN_PHRASE,
        "OverdraftService.charge",
        "InsufficientFundsError",
    ) in _harvest(failed)


def test_takes_no_exception_vocabulary_from_a_node_that_succeeded() -> None:
    succeeded = TraceNode(MethodSignature("OverdraftService", "charge"), outcome=Returned("null"))

    identifiers = {candidate.identifier for candidate in _harvest(succeeded)}
    assert identifiers == {"OverdraftService", "charge"}


def test_walks_children_and_counts_a_repeated_observation_once_per_sighting() -> None:
    leaf = _node("OverdraftService", "charge")
    parent = TraceNode(MethodSignature("OverdraftService", "charge"), children=[leaf])

    candidates = _harvest(parent)

    assert (
        HarvestCandidate(
            "billing", "charge", TermKind.VERB_PHRASE, "OverdraftService.charge", "charge", 2
        )
        in candidates
    )


def test_aggregates_the_same_phrase_across_separate_trees() -> None:
    tree = TraceTree([_node("OverdraftService", "charge")])

    candidates = harvest_traces([tree, tree], glossary=BILLING, module_of=_module_of)

    assert {candidate.occurrences for candidate in candidates} == {2}


def test_harvests_nothing_from_a_fully_synthetic_node() -> None:
    assert _harvest(_node("<launcher>", "<fork>")) == ()
    assert _harvest(_node("", "")) == ()
    assert _harvest(_node("Foo-Bar", "bad-name")) == ()


def test_still_harvests_the_class_of_a_node_whose_method_name_is_synthetic() -> None:
    # The real fire-and-forget launcher node: a genuine class, a method name that is no identifier.
    candidates = _harvest(_node("OverdraftService", "fire-and-forget"))

    assert candidates == (
        HarvestCandidate(
            "billing", "overdraft", TermKind.WORD, "OverdraftService", "OverdraftService"
        ),
    )


def test_still_harvests_the_method_of_a_node_whose_class_name_is_synthetic() -> None:
    candidates = _harvest(_node("<launcher>", "charge"))

    assert candidates == (
        HarvestCandidate(
            "_unassigned", "charge", TermKind.VERB_PHRASE, "<launcher>.charge", "charge"
        ),
    )


def test_skips_a_parameter_whose_name_is_not_an_identifier() -> None:
    candidates = _harvest(_node("OverdraftService", "charge", "not-a-name"))

    assert all(candidate.identifier != "not-a-name" for candidate in candidates)


def test_skips_an_exception_whose_type_name_is_not_an_identifier() -> None:
    synthetic_type = type("not-an-identifier", (Exception,), {})
    failed = TraceNode(
        MethodSignature("OverdraftService", "charge"), outcome=Threw(synthetic_type())
    )

    assert {candidate.identifier for candidate in _harvest(failed)} == {
        "OverdraftService",
        "charge",
    }


def test_contributes_nothing_for_an_identifier_that_is_only_a_role_token() -> None:
    assert _harvest(_node("Service", "charge", "id")) == (
        HarvestCandidate("_unassigned", "charge", TermKind.VERB_PHRASE, "Service.charge", "charge"),
    )


def test_files_a_class_no_context_claims_under_the_unassigned_context() -> None:
    candidates = _harvest(_node("TicketDesk", "escalate"))

    assert candidates
    assert {candidate.context for candidate in candidates} == {"_unassigned"}


def test_files_a_class_of_unknown_module_under_the_unassigned_context() -> None:
    candidates = harvest_traces(
        [TraceTree([_node("TicketDesk", "escalate")])],
        glossary=BILLING,
        module_of=lambda _: None,
    )

    assert candidates
    assert {candidate.context for candidate in candidates} == {"_unassigned"}


def test_harvesting_no_trees_observes_nothing() -> None:
    assert harvest_traces([], glossary=BILLING, module_of=_module_of) == ()
    assert _harvest() == ()


def test_orders_candidates_that_agree_on_everything_but_the_identifier() -> None:
    # A method's object noun and a parameter can produce the same phrase, kind and site: only the
    # identifier they came from tells them apart, so it has to settle the order.
    candidates = _harvest(_node("OverdraftLedger", "charge_account", "account"))

    tied = [candidate for candidate in candidates if candidate.phrase == "account"]
    assert [candidate.identifier for candidate in tied] == ["account", "charge_account"]


def test_rejects_a_glossary_that_is_not_one() -> None:
    with pytest.raises(TypeError, match=r"\Aglossary must be a Glossary\Z"):
        harvest_traces([], glossary={"billing": None}, module_of=_module_of)  # type: ignore[arg-type]


def test_rejects_a_module_resolver_that_cannot_be_called() -> None:
    with pytest.raises(TypeError, match=r"\Amodule_of must be callable\Z"):
        harvest_traces([], glossary=BILLING, module_of="acme.billing")  # type: ignore[arg-type]


def test_a_harvest_is_inconsistent_when_its_keys_repeat_or_fall_out_of_order() -> None:
    first = HarvestCandidate("billing", "account", TermKind.WORD, "A.a", "account")
    second = HarvestCandidate("billing", "overdraft", TermKind.WORD, "A.a", "overdraft")

    assert _invariant((first, second))
    assert not _invariant((second, first)), "observations must come back sorted"
    assert not _invariant((first, first)), "one sighting must not be counted under two entries"


def test_a_self_referential_node_does_not_crash_harvesting() -> None:
    """Security-suite mirror (2026-09-04): walking used unbounded native recursion with no depth
    bound or cycle guard -- both a cycle and a pathologically deep chain crashed with an
    uncaught RecursionError."""
    node = _node("OverdraftService", "run")
    node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
    assert _harvest(node) != ()


def test_a_ten_thousand_deep_chain_does_not_overflow_the_stack() -> None:
    node = _node("OverdraftService", "leaf")
    for _ in range(10_000):
        node = TraceNode(MethodSignature("OverdraftService", "wrap", []), [node])
    assert _harvest(node) != ()
