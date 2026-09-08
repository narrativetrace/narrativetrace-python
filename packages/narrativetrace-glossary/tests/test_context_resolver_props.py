# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for bounded-context resolution.

Two invariants carry the weight. Ownership is delimiter-aware for *every* prefix, not just the
near-misses an example test happens to name; and the answer never depends on the order contexts
were declared in, so two glossaries holding the same declarations resolve identically.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from narrativetrace_glossary import UNASSIGNED_CONTEXT, BoundedContext, Glossary, resolve_context

CONTEXT_NAMES = ["alpha", "billing", "shipping", "support", "zebra"]

PREFIXES = [
    "acme",
    "acme.billing",
    "acme.billing.collections",
    "acme.billingx",
    "acme.support",
    "other",
]

SEGMENTS = st.sampled_from(["acme", "billing", "billingx", "collections", "support", "other", "x"])
MODULE_PATHS = st.lists(SEGMENTS, min_size=0, max_size=4).map(".".join)

LOWERCASE = st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=6)


@st.composite
def declarations(draw: st.DrawFn) -> list[BoundedContext]:
    names = draw(st.lists(st.sampled_from(CONTEXT_NAMES), min_size=1, max_size=4, unique=True))
    return [
        BoundedContext(name, draw(st.lists(st.sampled_from(PREFIXES), max_size=3, unique=True)))
        for name in names
    ]


def glossary_with(contexts: list[BoundedContext]) -> Glossary:
    return Glossary({context.name: context for context in contexts})


def owns(prefix: str, module_path: str) -> bool:
    return module_path == prefix or module_path.startswith(f"{prefix}.")


@given(contexts=declarations(), module_path=MODULE_PATHS)
def test_the_resolved_context_declares_the_longest_owning_prefix(
    contexts: list[BoundedContext], module_path: str
) -> None:
    resolved = resolve_context(glossary_with(contexts), module_path)

    owning = [
        (len(prefix), context.name)
        for context in contexts
        for prefix in context.packages
        if owns(prefix, module_path)
    ]
    if not owning:
        assert resolved == UNASSIGNED_CONTEXT
    else:
        longest = max(length for length, _ in owning)
        assert resolved == min(name for length, name in owning if length == longest)


@given(contexts=declarations(), module_path=MODULE_PATHS)
def test_resolution_ignores_the_order_contexts_were_declared_in(
    contexts: list[BoundedContext], module_path: str
) -> None:
    forwards = resolve_context(glossary_with(contexts), module_path)

    assert resolve_context(glossary_with(contexts[::-1]), module_path) == forwards


@given(prefix_segments=st.lists(LOWERCASE, min_size=1, max_size=3), extra=LOWERCASE)
def test_a_path_extending_a_prefix_without_a_dot_is_never_owned(
    prefix_segments: list[str], extra: str
) -> None:
    prefix = ".".join(prefix_segments)
    glossary = glossary_with([BoundedContext("billing", [prefix])])

    assert resolve_context(glossary, f"{prefix}{extra}") == UNASSIGNED_CONTEXT
    assert resolve_context(glossary, f"{prefix}.{extra}") == "billing"
