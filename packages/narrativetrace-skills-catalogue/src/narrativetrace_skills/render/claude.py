# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders a :class:`~narrativetrace_skills.skill.Skill` as a Claude Code ``SKILL.md``
(frontmatter + body). Pure: ``resolve_snippet`` is injected so this module never touches disk —
``scripts/skills_render.py`` supplies the real reader, tests supply a fake one. A snippet step
embeds the CURRENT content of its source file through the same ``<!-- snippet: path -->`` marker
``scripts/snippet_check.py`` already enforces for docs — once the generated file is registered
with that tool, drift between this page and the fixture fails the gate the same way a stale doc
page would.

``name:`` is always ``skill.canonical_name`` -- never a shortened "Claude segment". A shortened
name is legitimate only inside a Claude plugin whose own prefix already carries the brand
(ruling, skills design, 2026-09-04, reaffirmed 2026-09-13); this repository ships a plain
``.claude/skills/`` directory, which is itself a flat namespace, not a plugin, so the canonical,
globally self-identifying name is the only one safe to render here.
"""

from __future__ import annotations

import json

from narrativetrace_skills.render._body import (
    ResolveSnippet,
    common_frontmatter_lines,
    render_skill_page,
)
from narrativetrace_skills.skill import Skill


def render_claude_skill(skill: Skill, resolve_snippet: ResolveSnippet) -> str:
    return render_skill_page(skill, resolve_snippet, _render_frontmatter)


def _render_frontmatter(skill: Skill) -> str:
    lines = ["---", *common_frontmatter_lines(skill)]
    if skill.when_to_use:
        lines.append(f"when_to_use: {json.dumps(skill.when_to_use)}")
    lines.append(f"allowed-tools: {', '.join(skill.allowed_tools)}")
    lines.append("---")
    return "\n".join(lines)
