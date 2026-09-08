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


def _owns(prefix: str, module_path: str) -> bool:
    """Delimiter-aware prefix test: the module itself, or a child module separated by a dot.

    ``acme.billing`` owns ``acme.billing.overdraft`` but never the sibling ``acme.billingx``.
    """
    return module_path == prefix or module_path.startswith(f"{prefix}.")
