# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for the harvest safety properties.

Plan section 10 makes harvest idempotence binding: the same code observed twice must yield the
same observations, or a second run re-keys terms the first run wrote and merges stop being no-ops.
Determinism is the stronger form tested here — output depends on *what* was traced, never on the
order trees or children were walked in.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    HarvestCandidate,
    TermKind,
    harvest_traces,
)
from narrativetrace_glossary.harvester import _order

from narrativetrace import MethodSignature, ParameterCapture, Returned, Threw, TraceNode, TraceTree

BILLING = Glossary({"billing": BoundedContext("billing", ["acme.billing"])})

WORDS = ["account", "overdraft", "charge", "open", "payment", "entries", "funds", "limit", "with"]

# Names that must be skipped sit beside harvestable ones, so every run mixes both paths.
CLASS_NAMES = st.sampled_from(["OverdraftService", "Ledger", "Service", "<launcher>", ""])
METHOD_NAMES = st.sampled_from(
    ["open_account", "charge", "fire-and-forget", "chargeAccount", "account", ""]
)
PARAMETER_NAMES = st.lists(st.sampled_from([*WORDS, "id", "account_id", "not-a-name"]), max_size=2)
EXCEPTION_NAMES = st.sampled_from([None, "InsufficientFundsError", "TimeoutError", "bad-name"])


def _module_of(class_name: str) -> str:
    return "acme.billing" if class_name.startswith("Overdraft") else "acme.support"


def _leaf(
    class_name: str, method_name: str, parameter_names: list[str], exception_name: str | None
) -> TraceNode:
    parameters = [ParameterCapture(name, '"v"') for name in parameter_names]
    outcome = (
        Threw(type(exception_name, (Exception,), {})())
        if exception_name is not None
        else Returned("null")
    )
    return TraceNode(MethodSignature(class_name, method_name, parameters), outcome=outcome)


def _parent(class_name: str, method_name: str, children: list[TraceNode]) -> TraceNode:
    return TraceNode(MethodSignature(class_name, method_name), children=children)


# Kept deliberately small: the walk is plain recursion, so breadth and depth of 2 already exercise
# every branch, and `test_doubling_a_run...` harvests twice this much. Larger runs only spend time
# — enough of it to trip Hypothesis' per-example deadline under mutmut's instrumented copy.
LEAVES = st.builds(_leaf, CLASS_NAMES, METHOD_NAMES, PARAMETER_NAMES, EXCEPTION_NAMES)
NODES = st.recursive(
    LEAVES,
    lambda children: st.builds(_parent, CLASS_NAMES, METHOD_NAMES, st.lists(children, max_size=2)),
    max_leaves=3,
)
TREES = st.lists(NODES, max_size=2).map(TraceTree)
RUNS = st.lists(TREES, max_size=2)


def _harvest(trees: list[TraceTree]) -> tuple[HarvestCandidate, ...]:
    return harvest_traces(trees, glossary=BILLING, module_of=_module_of)


@given(RUNS)
def test_harvesting_the_same_run_twice_observes_exactly_the_same_thing(
    trees: list[TraceTree],
) -> None:
    assert _harvest(trees) == _harvest(trees)


@given(RUNS)
def test_the_result_does_not_depend_on_the_order_the_trees_were_walked_in(
    trees: list[TraceTree],
) -> None:
    assert _harvest(list(reversed(trees))) == _harvest(trees)


@given(RUNS)
def test_observations_come_back_in_a_total_order_with_no_repeated_key(
    trees: list[TraceTree],
) -> None:
    candidates = _harvest(trees)

    keys = [_order(candidate) for candidate in candidates]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)


@given(RUNS)
def test_every_observed_phrase_stays_canonical_and_was_seen_at_least_once(
    trees: list[TraceTree],
) -> None:
    for candidate in _harvest(trees):
        assert candidate.phrase == candidate.phrase.lower()
        assert candidate.phrase == " ".join(candidate.phrase.split())
        assert candidate.occurrences >= 1
        assert candidate.identifier.isidentifier()


@given(RUNS)
def test_no_phrase_is_ever_harvested_as_a_template_from_a_live_trace(
    trees: list[TraceTree],
) -> None:
    # A traced narration holds interpolated *values*; harvesting one would write runtime data into
    # the committed glossary. Templates are a static-scan source only (phase 5).
    assert all(candidate.kind is not TermKind.TEMPLATE for candidate in _harvest(trees))


@given(RUNS)
def test_doubling_a_run_doubles_every_count_and_changes_nothing_else(
    trees: list[TraceTree],
) -> None:
    once = _harvest(trees)
    twice = _harvest(trees + trees)

    assert [_order(candidate) for candidate in twice] == [_order(candidate) for candidate in once]
    assert [candidate.occurrences for candidate in twice] == [
        candidate.occurrences * 2 for candidate in once
    ]
