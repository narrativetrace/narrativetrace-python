# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from narrativetrace_skills.render.claude import render_claude_skill
from narrativetrace_skills.skill import (
    CommandStep,
    FailureNote,
    ReasonedRule,
    Skill,
    SkillSection,
    SkillStep,
    SnippetStep,
)


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
        # No "Claude segment" shortening: the frontmatter `name:` is always the catalogue's
        # canonical id, since a repo-level `.claude/skills/` directory is a flat namespace too
        # (ruling, skills design, 2026-09-04, reaffirmed 2026-09-13).
        rendered = render_claude_skill(_skill(canonical_name="narrativetrace-doctor"), _resolve)
        assert "name: narrativetrace-doctor" in rendered

    def test_description_is_json_quoted(self) -> None:
        rendered = render_claude_skill(_skill(description='Say "hi"'), _resolve)
        assert '"Say \\"hi\\""' in rendered

    def test_when_to_use_is_omitted_when_absent(self) -> None:
        rendered = render_claude_skill(_skill(when_to_use=None), _resolve)
        assert "when_to_use" not in rendered

    def test_when_to_use_is_rendered_when_present(self) -> None:
        rendered = render_claude_skill(_skill(when_to_use="use it here"), _resolve)
        assert 'when_to_use: "use it here"' in rendered

    def test_allowed_tools_renders_bash_tool_patterns_not_bare_commands(self) -> None:
        # A bare command name pre-approves nothing in Claude Code's own syntax -- allowed-tools
        # lists TOOLS, not commands (see skill.claude_tool_pattern).
        rendered = render_claude_skill(_skill(allowed_tools=("uv", "git")), _resolve)
        assert "allowed-tools: Bash(uv *), Bash(git *)" in rendered

    def test_no_allowed_tools_omits_the_line_rather_than_emitting_an_empty_value(self) -> None:
        # An empty `allowed-tools:` is not "pre-approve nothing" to every reader of the page, and
        # a skill that can publish must leave the harness asking: the LINE is what is absent.
        rendered = render_claude_skill(_skill(allowed_tools=()), _resolve)
        assert "allowed-tools" not in rendered


class TestBody:
    def test_heading_is_the_canonical_name(self) -> None:
        rendered = render_claude_skill(_skill(canonical_name="narrativetrace-doctor"), _resolve)
        assert "# narrativetrace-doctor" in rendered

    def test_steps_are_numbered_from_one(self) -> None:
        skill = _skill(
            steps=(
                SkillStep(title="First", body=CommandStep(commands=("uv sync",))),
                SkillStep(title="Second", body=CommandStep(commands=("git status",))),
            )
        )
        rendered = render_claude_skill(skill, _resolve)
        assert "## 1. First" in rendered
        assert "## 2. Second" in rendered

    def test_command_step_renders_a_bash_fence(self) -> None:
        skill = _skill(steps=(SkillStep(title="s", body=CommandStep(commands=("uv sync",))),))
        rendered = render_claude_skill(skill, _resolve)
        assert "```bash\nuv sync\n```" in rendered

    def test_command_step_with_no_commands_renders_no_empty_fence(self) -> None:
        # A step that is a decision for the agent (ask, then stop the turn) has nothing to run;
        # an empty ```bash fence under its heading would read as a command that prints nothing.
        skill = _skill(steps=(SkillStep(title="Ask", body=CommandStep(commands=())),))
        rendered = render_claude_skill(skill, _resolve)
        assert rendered.endswith("## 1. Ask")
        assert "```" not in rendered

    def test_snippet_step_renders_the_marker_and_resolved_content(self) -> None:
        skill = _skill(
            steps=(SkillStep(title="s", body=SnippetStep(path="x.py", language="python")),)
        )
        rendered = render_claude_skill(skill, _resolve)
        assert "<!-- snippet: x.py -->" in rendered
        assert "```python\n# content of x.py\n```" in rendered
        assert "<!-- /snippet -->" in rendered

    def test_snippet_step_with_mask_renders_the_mask_attribute(self) -> None:
        skill = _skill(
            steps=(
                SkillStep(
                    title="s", body=SnippetStep(path="x.py", language="python", mask="duration")
                ),
            )
        )
        rendered = render_claude_skill(skill, _resolve)
        assert "<!-- snippet: x.py mask=duration -->" in rendered

    def test_verify_is_rendered_as_inline_code(self) -> None:
        skill = _skill(
            steps=(
                SkillStep(
                    title="s", body=CommandStep(commands=("uv sync",)), verify="uv run pytest"
                ),
            )
        )
        rendered = render_claude_skill(skill, _resolve)
        assert "**verify:** `uv run pytest`" in rendered

    def test_step_with_no_verify_renders_no_verify_line(self) -> None:
        skill = _skill(steps=(SkillStep(title="s", body=CommandStep(commands=("uv sync",))),))
        rendered = render_claude_skill(skill, _resolve)
        assert "**verify:**" not in rendered

    def test_failure_note_is_rendered(self) -> None:
        skill = _skill(
            steps=(
                SkillStep(
                    title="s",
                    body=CommandStep(commands=("uv sync",)),
                    failure=(FailureNote(symptom="it breaks", cause="a bug", fix="patch it"),),
                ),
            )
        )
        rendered = render_claude_skill(skill, _resolve)
        assert "**failure:** it breaks — a bug. Fix: patch it" in rendered

    def test_flagged_step_renders_the_flag(self) -> None:
        skill = _skill(
            steps=(SkillStep(title="s", body=CommandStep(commands=("uv sync",)), flag="unstudied"),)
        )
        rendered = render_claude_skill(skill, _resolve)
        assert "**Flagged:** unstudied" in rendered

    def test_a_step_condition_renders_between_the_heading_and_the_body(self) -> None:
        skill = _skill(
            steps=(
                SkillStep(
                    title="Conditional step",
                    body=CommandStep(commands=("uv sync",)),
                    condition="only when the project has no entry point",
                ),
            )
        )
        rendered = render_claude_skill(skill, _resolve)
        assert (
            "## 1. Conditional step\n\n"
            "**when:** only when the project has no entry point\n\n"
            "```bash\nuv sync\n```"
        ) in rendered

    def test_an_unconditional_step_renders_no_when_line(self) -> None:
        skill = _skill(steps=(SkillStep(title="s", body=CommandStep(commands=("uv sync",))),))
        assert "**when:**" not in render_claude_skill(skill, _resolve)

    def test_always_section_omitted_when_empty(self) -> None:
        rendered = render_claude_skill(_skill(always=()), _resolve)
        assert "## Always" not in rendered

    def test_always_and_never_sections_render_rule_and_reason(self) -> None:
        skill = _skill(
            always=(ReasonedRule(rule="Do X.", reason="because Y."),),
            never=(ReasonedRule(rule="Don't Z.", reason="because W."),),
        )
        rendered = render_claude_skill(skill, _resolve)
        assert "## Always\n\n- Do X. (because Y.)" in rendered
        assert "## Never\n\n- Don't Z. (because W.)" in rendered


class TestReferenceSectionsAndDoneLines:
    def test_sections_render_after_the_steps_and_before_the_rules(self) -> None:
        skill = _skill(
            steps=(SkillStep(title="s", body=CommandStep(commands=("uv sync",))),),
            sections=(
                SkillSection(heading="Flavours", markdown="| a | b |\n|---|---|\n"),
                SkillSection(heading="Shapes", markdown="- twice"),
            ),
            always=(ReasonedRule(rule="Do X.", reason="because Y."),),
        )
        rendered = render_claude_skill(skill, _resolve)
        assert (
            "```bash\nuv sync\n```\n\n"
            "## Flavours\n\n| a | b |\n|---|---|\n\n"
            "## Shapes\n\n- twice\n\n"
            "## Always\n\n- Do X. (because Y.)"
        ) in rendered

    def test_a_skill_with_no_sections_renders_none(self) -> None:
        rendered = render_claude_skill(_skill(steps=()), _resolve)
        assert "\n## " not in rendered

    def test_a_done_condition_renders_after_the_body_and_before_verify(self) -> None:
        skill = _skill(
            steps=(
                SkillStep(
                    title="Write the intent",
                    body=CommandStep(commands=()),
                    done="three to six lines under the word Intent",
                ),
                SkillStep(
                    title="Run",
                    body=CommandStep(commands=("uv run pytest",)),
                    done="the test ran",
                    verify="uv run pytest",
                ),
            )
        )
        rendered = render_claude_skill(skill, _resolve)
        assert (
            "## 1. Write the intent\n\n**done when:** three to six lines under the word Intent"
            in (rendered)
        )
        assert "```bash\nuv run pytest\n```\n\n**done when:** the test ran\n\n**verify:**" in (
            rendered
        )
