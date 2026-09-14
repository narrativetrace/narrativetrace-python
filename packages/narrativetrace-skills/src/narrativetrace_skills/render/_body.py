# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The page BODY every rendered ``SKILL.md`` shares -- platform-agnostic, so :mod:`claude` and
:mod:`codex` differ only in their frontmatter, never in the numbered steps, snippets, verify
lines, failure notes or always/never rules a skill documents. Extracted from :mod:`claude` (its
original, and still only Claude-specific, home) once a second platform needed the identical
content: two independent copies of this walk would have been the same drift risk this catalogue
exists to remove everywhere else.

:func:`render_skill_page` and :func:`common_frontmatter_lines` factor out the two platform
renderers' remaining shared shape (the frontmatter/blank-line/body assembly, and the two fields
-- ``name``, ``description`` -- both frontmatters carry) so :mod:`claude` and :mod:`codex` are
left with only their genuinely different lines, not a second copy of the wrapper around them.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from narrativetrace_skills.skill import CommandStep, ReasonedRule, Skill, SkillStep, StepBody

ResolveSnippet = Callable[[str], str]
RenderFrontmatter = Callable[[Skill], str]


def render_skill_page(
    skill: Skill, resolve_snippet: ResolveSnippet, render_frontmatter: RenderFrontmatter
) -> str:
    return "\n".join([render_frontmatter(skill), "", render_skill_body(skill, resolve_snippet)])


def common_frontmatter_lines(skill: Skill) -> list[str]:
    """``name``/``description`` -- the two fields every platform's frontmatter carries, in order,
    without the surrounding ``---`` fence a platform module adds itself."""
    return [f"name: {skill.canonical_name}", f"description: {json.dumps(skill.description)}"]


def render_skill_body(skill: Skill, resolve_snippet: ResolveSnippet) -> str:
    sections = [
        f"# {skill.canonical_name}",
        "",
        "\n\n".join(
            _render_step(step, index + 1, resolve_snippet) for index, step in enumerate(skill.steps)
        ),
    ]
    if skill.always:
        sections.extend(["", _render_rules("Always", skill.always)])
    if skill.never:
        sections.extend(["", _render_rules("Never", skill.never)])
    return "\n".join(sections)


def _render_step_body(body: StepBody, resolve_snippet: ResolveSnippet) -> str:
    if isinstance(body, CommandStep):
        return "\n".join(["```bash", *body.commands, "```"])
    mask_attr = f" mask={body.mask}" if body.mask else ""
    return "\n".join(
        [
            f"<!-- snippet: {body.path}{mask_attr} -->",
            f"```{body.language}",
            resolve_snippet(body.path),
            "```",
            "<!-- /snippet -->",
        ]
    )


def _render_step(step: SkillStep, index: int, resolve_snippet: ResolveSnippet) -> str:
    lines = [f"## {index}. {step.title}", ""]
    if step.flag:
        lines.extend([f"**Flagged:** {step.flag}", ""])
    lines.append(_render_step_body(step.body, resolve_snippet))
    if step.verify:
        lines.extend(["", f"**verify:** `{step.verify}`"])
    for note in step.failure:
        lines.extend(["", f"**failure:** {note.symptom} — {note.cause}. Fix: {note.fix}"])
    return "\n".join(lines)


def _render_rules(heading: str, rules: tuple[ReasonedRule, ...]) -> str:
    items = [f"- {rule.rule} ({rule.reason})" for rule in rules]
    return "\n".join([f"## {heading}", "", *items])
