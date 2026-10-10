# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Whether a page nobody stamped is nevertheless ours.

INTENT: a project can get these skills from a registry before it ever runs ``init`` — a registry
installs THIS repository's own rendered pages, out of the public git tree, with no provenance line.
Such a page is not a foreign page at all; it is ours, unstamped. Recognising that is what lets
``init`` adopt it instead of refusing it, and it is the one place the distinction is decided.

**@llmNote** The comparison is the rendered bytes with ONLY the line ending normalised. A trailing
space, a reordered frontmatter key, a missing final newline, another release's wording, or the other
flavour's page is NOT adoptable — it is either somebody's edit or another release, and both of those
are exactly what the refusal exists to protect.

**@sideEffects** None. A pure comparison of two strings.

Internal to :mod:`narrativetrace_tooling.init`.
"""

from __future__ import annotations


def is_adoptable(installed: str, rendered: str) -> bool:
    """Whether ``installed`` is the carrier's own ``rendered`` page for some flavour.

    An empty installed page is never adoptable: a skill directory with no page at all is a directory
    somebody else made, not a copy of ours.

    :raises TypeError: when either page is missing altogether; a comparison against nothing is a
        caller's mistake, never a project's state
    """
    for page in (installed, rendered):
        if not isinstance(page, str):
            raise TypeError("adoption compares two pages, never None")
    return bool(installed) and _with_one_line_ending(installed) == _with_one_line_ending(rendered)


def _with_one_line_ending(page: str) -> str:
    """Both spellings of a line ending read as one, and nothing else about the page is touched."""
    return page.replace("\r\n", "\n").replace("\r", "\n")
