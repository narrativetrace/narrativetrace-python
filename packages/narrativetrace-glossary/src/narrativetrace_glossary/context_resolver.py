# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Resolves the dotted module path of traced code to the bounded context that owns it.

``ContextResolver``, whose Java package prefixes become dotted module-path prefixes
(``acme.billing``, not ``com.acme.billing``). INTENT: contexts declare their prefixes in the
glossary file itself, so the file stays the single source of truth.
"""

from __future__ import annotations

from collections.abc import Callable

from narrativetrace_glossary.models import Glossary

UNASSIGNED_CONTEXT = "_unassigned"
"""Fallback context for module paths no declared context owns."""


def resolve_context(glossary: Glossary, module_path: str) -> str:
    """Resolves a module path to the name of the context that declares a matching prefix.

    The longest matching prefix wins, so contexts may nest; no match resolves to
    :data:`UNASSIGNED_CONTEXT`, which is what lets harvesting work with zero configuration.
    """
    owners = [
        (len(prefix), name)
        for name in sorted(glossary.contexts)
        for prefix in glossary.contexts[name].packages
        if _owns(prefix, module_path)
    ]
    if not owners:
        return UNASSIGNED_CONTEXT
    # Sorted iteration plus max()'s first-maximal rule makes equal-length ties deterministic:
    # the alphabetically first context name wins.
    return max(owners, key=lambda owner: owner[0])[1]


def package_to_resolve(
    captured_package: str | None, class_name: str, index: Callable[[str], str | None]
) -> str:
    """The module path a call's bounded context is resolved from.

    The one rule harvesting and translation both call, so a term is always looked up in the
    context it was filed under. Identity captured at the site is authoritative: it is the
    declaring class's real module, recorded where the truth was known. The simple-name ``index``
    is the fallback for a capture that predates the captured field, and it is only ever a
    re-derivation -- it answers ``None`` for a class shipped in a wheel the index never scanned
    and for a simple name two modules share, and it can answer for the wrong one of two
    same-named classes.

    Harvesting once resolved through the index alone while translation preferred the captured
    package. The two then disagreed exactly where the index is weakest, and the term landed in
    one context while the render looked in another -- a glossary gap that curating the term
    could not clear, because the lookup was never going to the context it was curated in.

    Args:
        captured_package: module path recorded at the capture site, or ``None`` when it was not.
        class_name: simple class name, for the fallback re-derivation.
        index: maps a simple class name to its module path (``None`` when unknown or ambiguous).

    Returns:
        The module path to resolve, never ``None`` (``""`` when nothing is known).
    """
    if captured_package is not None:
        return captured_package
    derived = index(class_name)
    return derived if derived is not None else ""


def _owns(prefix: str, module_path: str) -> bool:
    """Delimiter-aware prefix test: the module itself, or a child module separated by a dot.

    ``acme.billing`` owns ``acme.billing.overdraft`` but never the sibling ``acme.billingx``.
    """
    return module_path == prefix or module_path.startswith(f"{prefix}.")
