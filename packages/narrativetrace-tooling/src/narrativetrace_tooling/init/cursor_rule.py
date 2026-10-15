# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders the one Cursor rule file — ``.cursor/rules/narrativetrace.mdc`` — that points Cursor's
agent at the installed skills.

INTENT: the Cursor row's pointer. The rule is a SENTENCE, never a copy of a skill page: Cursor
already loads the pages from ``.agents/skills``, and a second copy would be a third page flavour to
keep in step. The same text is the plugin's rule, so a project that installed the plugin and one
that ran ``init`` read the same words.

**@llmNote** The file is frontmatter plus one managed section: Cursor needs the ``---`` block
first, so the ``narrativetrace:created`` note a markdown home carries cannot go on line 1.
:data:`FRONTMATTER` is therefore also what an uninstall compares against — a rule file that is
nothing but the frontmatter once our section is removed is a file we made, and is deleted. With an
empty coordinate the opening marker carries no stamp, which is how the plugin ships it and why
``init`` can adopt it.

**@sideEffects** None. A pure rendering; renders with ``\\n`` throughout.
"""

from __future__ import annotations

from typing import Final

from narrativetrace_tooling.init import marked_block

FRONTMATTER: Final = (
    "---\ndescription: Where the NarrativeTrace agent skills live in this project\n"
    "alwaysApply: true\n---\n"
)
"""The ``.mdc`` frontmatter: always applied, because the pointer must be seen every turn."""


def render_cursor_rule(text: str, coordinate: str) -> str:
    """The whole rule file for one pointer sentence.

    :param text: the pointer sentence, from the platform table's Cursor row
    :param coordinate: the carrier coordinate stamped on the opening marker, or ``""`` for the
        unstamped plugin copy
    :raises TypeError: when the text or the coordinate is missing
    :raises ValueError: when the sentence is blank
    """
    if not isinstance(text, str) or not isinstance(coordinate, str):
        raise TypeError('a rule needs its text and a coordinate (or "")')
    if not text.strip():
        raise ValueError("a rule needs its text")
    stamp = f" {coordinate}" if coordinate else ""
    rule = f"{FRONTMATTER}{marked_block.START}{stamp} -->\n{text}\n{marked_block.END}\n"
    assert marked_block.scan(rule).has_exactly_one_region(), "the rule must be one region"
    return rule
