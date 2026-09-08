# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Behaviour of bounded-context resolution from a dotted module path."""

from __future__ import annotations

import pytest
from narrativetrace_glossary import (
    UNASSIGNED_CONTEXT,
    BoundedContext,
    Glossary,
    resolve_context,
)


def glossary_with(*contexts: BoundedContext) -> Glossary:
    return Glossary({context.name: context for context in contexts})


def test_resolves_a_module_path_to_the_context_declaring_its_prefix() -> None:
    glossary = glossary_with(
        BoundedContext("billing", ["acme.billing"]),
        BoundedContext("support", ["acme.support"]),
    )

    assert resolve_context(glossary, "acme.billing") == "billing"
    assert resolve_context(glossary, "acme.billing.overdraft") == "billing"
    assert resolve_context(glossary, "acme.support") == "support"


@pytest.mark.parametrize("module_path", ["other.shop", "", "acme"])
def test_falls_back_to_the_unassigned_context_when_no_prefix_matches(module_path: str) -> None:
    glossary = glossary_with(BoundedContext("billing", ["acme.billing"]))

    assert resolve_context(glossary, module_path) == UNASSIGNED_CONTEXT
    assert UNASSIGNED_CONTEXT == "_unassigned"


def test_the_longest_matching_prefix_wins_so_contexts_can_nest() -> None:
    glossary = glossary_with(
        BoundedContext("billing", ["acme.billing"]),
        BoundedContext("collections", ["acme.billing.collections"]),
    )

    assert resolve_context(glossary, "acme.billing.collections.dunning") == "collections"
    assert resolve_context(glossary, "acme.billing.invoice") == "billing"


def test_a_context_owns_every_prefix_it_declares() -> None:
    glossary = glossary_with(BoundedContext("billing", ["acme.billing", "acme.invoicing"]))

    assert resolve_context(glossary, "acme.billing.overdraft") == "billing"
    assert resolve_context(glossary, "acme.invoicing.dunning") == "billing"


def test_an_equal_length_prefix_tie_resolves_to_the_alphabetically_first_context() -> None:
    zebra = BoundedContext("zebra", ["acme.billing"])
    alpha = BoundedContext("alpha", ["acme.billing"])

    # Declaration order must not decide the winner: both orderings resolve the same way.
    assert resolve_context(glossary_with(zebra, alpha), "acme.billing.core") == "alpha"
    assert resolve_context(glossary_with(alpha, zebra), "acme.billing.core") == "alpha"


@pytest.mark.parametrize(
    "module_path", ["acme.billingx", "acme.billingx.core", "acme.billin", "acme.billing_legacy"]
)
def test_a_sibling_sharing_the_prefix_without_a_dot_is_not_owned(module_path: str) -> None:
    glossary = glossary_with(BoundedContext("billing", ["acme.billing"]))

    assert resolve_context(glossary, module_path) == UNASSIGNED_CONTEXT


def test_a_glossary_without_declared_prefixes_resolves_everything_as_unassigned() -> None:
    glossary = glossary_with(BoundedContext("billing"))

    assert resolve_context(glossary, "acme.billing") == UNASSIGNED_CONTEXT
