# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Codex CLI's ``SKILL.md`` frontmatter is a strict subset of Claude's (``name`` + ``description``
only, per Codex's own current skill-discovery documentation, verified 2026-09-14) -- the BODY is
the exact same rendering :mod:`claude` already produces and already tests exhaustively, so this
module only pins the frontmatter difference and a parity check against Claude's body, rather than
re-testing every step/snippet/rule case a second time."""

from __future__ import annotations

from narrativetrace_skills.render.claude import render_claude_skill
from narrativetrace_skills.render.codex import render_codex_skill
from narrativetrace_skills.skill import CommandStep, ReasonedRule, Skill, SkillStep


def _resolve(path: str) -> str:
    return f"# content of {path}"


def _skill(**overrides: object) -> Skill:
    base: dict[str, object] = {
        "canonical_name": "demo-skill",
        "skill_class": "mechanical",
        "description": "A demo skill.",
        "fixture": "examples/demo",
        "steps": (),
        "allowed_tools": ("uv", "git"),
    }
    base.update(overrides)
    return Skill(**base)  # type: ignore[arg-type]


class TestFrontmatter:
    def test_name_is_the_canonical_name(self) -> None:
        rendered = render_codex_skill(_skill(canonical_name="narrativetrace-doctor"), _resolve)
        assert "name: narrativetrace-doctor" in rendered

    def test_description_is_json_quoted(self) -> None:
        rendered = render_codex_skill(_skill(description='Say "hi"'), _resolve)
        assert '"Say \\"hi\\""' in rendered

    def test_frontmatter_carries_no_when_to_use_field(self) -> None:
        # Codex's documented frontmatter has no `when_to_use` key -- unlike Claude's page, this
        # must never leak even when the catalogue entry declares one.
        rendered = render_codex_skill(_skill(when_to_use="use it here"), _resolve)
        assert "when_to_use" not in rendered

    def test_frontmatter_carries_no_allowed_tools_field(self) -> None:
        # Same story for `allowed-tools`: Codex's documented frontmatter is exactly `name` +
        # `description`, nothing else.
        rendered = render_codex_skill(_skill(allowed_tools=("uv", "git")), _resolve)
        assert "allowed-tools" not in rendered

    def test_frontmatter_is_exactly_two_fields(self) -> None:
        rendered = render_codex_skill(_skill(), _resolve)
        frontmatter = rendered.split("---")[1].strip().splitlines()
        assert len(frontmatter) == 2
        assert frontmatter[0].startswith("name: ")
        assert frontmatter[1].startswith("description: ")


class TestBodyParityWithClaude:
    def test_codex_and_claude_render_the_identical_body(self) -> None:
        skill = _skill(
            when_to_use="use it here",
            steps=(
                SkillStep(
                    title="First", body=CommandStep(commands=("uv sync",)), verify="uv run x"
                ),
            ),
            always=(ReasonedRule(rule="Do X.", reason="because Y."),),
        )
        claude_body = render_claude_skill(skill, _resolve).split("\n\n", 1)[1]
        codex_body = render_codex_skill(skill, _resolve).split("\n\n", 1)[1]
        assert codex_body == claude_body
