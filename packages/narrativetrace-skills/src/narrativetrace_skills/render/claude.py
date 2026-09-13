# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders a :class:`~narrativetrace_skills.skill.Skill` as a Claude plugin ``SKILL.md``
(frontmatter + body). Pure: ``resolve_snippet`` is injected so this module never touches disk —
``scripts/skills_render.py`` supplies the real reader, tests supply a fake one. A snippet step
embeds the CURRENT content of its source file through the same ``<!-- snippet: path -->`` marker
``scripts/snippet_check.py`` already enforces for docs — once the generated file is registered
with that tool, drift between this page and the fixture fails the gate the same way a stale doc
page would.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from narrativetrace_skills.skill import CommandStep, ReasonedRule, Skill, SkillStep, StepBody

ResolveSnippet = Callable[[str], str]


def render_claude_skill(skill: Skill, resolve_snippet: ResolveSnippet) -> str:
    return "\n".join([_render_frontmatter(skill), "", _render_body(skill, resolve_snippet)])


def _render_frontmatter(skill: Skill) -> str:
    lines = [
        "---",
        f"name: {skill.claude_segment}",
        f"description: {json.dumps(skill.description)}",
    ]
    if skill.when_to_use:
        lines.append(f"when_to_use: {json.dumps(skill.when_to_use)}")
    lines.append(f"allowed-tools: {', '.join(skill.allowed_tools)}")
    lines.append("---")
    return "\n".join(lines)


def _render_body(skill: Skill, resolve_snippet: ResolveSnippet) -> str:
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
