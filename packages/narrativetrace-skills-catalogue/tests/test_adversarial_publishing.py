# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial tests for the publishing lint and the body/frontmatter renderers.

Each test pins behaviour the existing suites do not reach. The one-line comment above each test
states what we believe the correct behaviour is; exact strings are asserted, never substrings.
"""

from __future__ import annotations

from narrativetrace_skills.lints import publishing_not_pre_approved
from narrativetrace_skills.render.claude import render_claude_skill
from narrativetrace_skills.render.codex import render_codex_skill
from narrativetrace_skills.skill import (
    CommandStep,
    FailureNote,
    ReasonedRule,
    Skill,
    SkillStep,
    SnippetStep,
)

_FEEDBACK = "uv run narrativetrace feedback url --category library --step s"


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


def _reporter(*steps: SkillStep, allowed_tools: tuple[str, ...] = ("uv",)) -> Skill:
    return _skill(canonical_name="reporter", steps=steps, allowed_tools=allowed_tools)


def _cmd(title: str, *commands: str) -> SkillStep:
    return SkillStep(title=title, body=CommandStep(commands=commands))


def _violation(command: str, tool: str = "uv", name: str = "reporter") -> str:
    return (
        f'{name}: declares allowed tool "{tool}", which pre-approves its own publishing command '
        f'"{command}" -- a skill that files something public must let the harness ask'
    )


_FRONTMATTER_FENCE = "\n---\n\n"


class TestPublishingLintAdversarial:
    def test_leading_whitespace_before_the_publishing_command_is_still_flagged(self) -> None:
        # Believed correct: first_token strips leading blanks, so padding cannot hide a publisher.
        command = f"   {_FEEDBACK}"
        skill = _reporter(_cmd("file", command))
        assert publishing_not_pre_approved((skill,)) == (_violation(command),)

    def test_a_tab_separating_the_tool_from_the_verb_is_still_flagged(self) -> None:
        # Believed correct: a tab is whitespace, so the first token is still the tool "uv".
        command = "uv\trun narrativetrace feedback url"
        skill = _reporter(_cmd("file", command))
        assert publishing_not_pre_approved((skill,)) == (_violation(command),)

    def test_an_uppercase_verb_is_not_flagged_because_the_cli_verb_is_lowercase(self) -> None:
        # Believed correct: the CLI subcommand is spelled lowercase, so "Feedback" does not publish
        # and the lint keys on the real verb. (`cli_bin` compares the verb with ==.)
        skill = _reporter(_cmd("look", "uv run narrativetrace Feedback url"))
        assert publishing_not_pre_approved((skill,)) == ()

    def test_a_publishing_verb_inside_a_verify_is_flagged(self) -> None:
        # A verify is run by the agent in the same turn, so one that invokes the publishing verb
        # publishes exactly like a command does -- and the skill's own URL check is such a verify.
        verify = "uv run narrativetrace feedback url --category library --step s"
        skill = _reporter(
            SkillStep(title="s", body=CommandStep(commands=("uv sync",)), verify=verify)
        )
        assert publishing_not_pre_approved((skill,)) == (_violation(verify),)

    def test_a_verify_equal_to_its_command_is_reported_once_per_place_it_runs(self) -> None:
        # Both run, so both are reported; the message names the same command twice.
        skill = _reporter(
            SkillStep(title="s", body=CommandStep(commands=(_FEEDBACK,)), verify=_FEEDBACK)
        )
        assert publishing_not_pre_approved((skill,)) == (_violation(_FEEDBACK),) * 2

    def test_a_publishing_command_later_in_a_multi_command_step_names_only_that_command(
        self,
    ) -> None:
        # Believed correct: each publishing command is reported; harmless siblings are not named.
        skill = _reporter(_cmd("s", "uv sync", _FEEDBACK, "git status"))
        assert publishing_not_pre_approved((skill,)) == (_violation(_FEEDBACK),)

    def test_a_decision_only_step_beside_a_publishing_step_does_not_add_a_violation(self) -> None:
        # Believed correct: an empty step carries no command, so only the real publisher counts.
        skill = _reporter(_cmd("ask"), _cmd("file", _FEEDBACK))
        assert publishing_not_pre_approved((skill,)) == (_violation(_FEEDBACK),)

    def test_a_duplicated_allowed_tool_yields_one_violation_per_command_not_per_tool(self) -> None:
        # Believed correct: the violation is per publishing command, so a repeated tool
        # must not double-report it.
        skill = _reporter(_cmd("file", _FEEDBACK), allowed_tools=("uv", "uv"))
        assert publishing_not_pre_approved((skill,)) == (_violation(_FEEDBACK),)

    def test_a_snippet_step_showing_feedback_source_is_not_a_publishing_command(self) -> None:
        # Believed correct: a snippet is file content shown to the reader, never executed.
        skill = _reporter(
            SkillStep(title="show", body=SnippetStep(path="x.py", language="python")),
            allowed_tools=("uv",),
        )
        assert publishing_not_pre_approved((skill,)) == ()

    def test_a_near_miss_tool_that_shares_the_prefix_does_not_pre_approve(self) -> None:
        # Believed correct: uvx is a different tool from uv, so allowing "uv" must not match it.
        command = "uvx narrativetrace feedback url"
        skill = _reporter(_cmd("file", command), allowed_tools=("uv",))
        assert publishing_not_pre_approved((skill,)) == ()


_VENDOR_FRONTMATTER = '---\nname: demo-skill\ndescription: "A demo skill."\n'


class TestRenderBodyAdversarial:
    def test_decision_only_step_keeps_verify_flag_and_failure_without_an_empty_fence(self) -> None:
        # Believed correct: a decision step has no fence, but its flag, verify and failure notes
        # still render, in that order, and the body never contains a ``` line.
        skill = _skill(
            steps=(
                SkillStep(
                    title="Ask the user",
                    body=CommandStep(commands=()),
                    verify="uv run pytest",
                    flag="unstudied",
                    failure=(FailureNote(symptom="s", cause="c", fix="f"),),
                ),
            )
        )
        rendered = render_claude_skill(skill, _resolve)
        assert rendered == (
            _VENDOR_FRONTMATTER
            + "allowed-tools: Bash(uv *), Bash(git *)\n---\n\n"
            + "# demo-skill\n\n"
            + "## 1. Ask the user\n\n"
            + "**Flagged:** unstudied\n\n"
            + "**verify:** `uv run pytest`\n\n"
            + "**failure:** s — c. Fix: f"
        )

    def test_decision_only_first_and_last_steps_render_headings_around_a_command_step(
        self,
    ) -> None:
        # Believed correct: each step is separated by one blank line; decision steps stay bare.
        skill = _skill(
            steps=(
                SkillStep(title="Decide", body=CommandStep(commands=())),
                SkillStep(title="Sync", body=CommandStep(commands=("uv sync",))),
                SkillStep(title="Confirm", body=CommandStep(commands=())),
            )
        )
        rendered = render_claude_skill(skill, _resolve)
        assert rendered.split(_FRONTMATTER_FENCE, 1)[1] == (
            "# demo-skill\n\n## 1. Decide\n\n## 2. Sync\n\n```bash\nuv sync\n```\n\n## 3. Confirm"
        )

    def test_a_trailing_decision_step_is_followed_by_always_and_never_sections(self) -> None:
        # Believed correct: rules attach after the last step with exactly one blank line each side.
        skill = _skill(
            steps=(SkillStep(title="Ask", body=CommandStep(commands=())),),
            always=(ReasonedRule(rule="Ask first.", reason="it is public."),),
            never=(ReasonedRule(rule="Never guess.", reason="guesses publish."),),
        )
        rendered = render_claude_skill(skill, _resolve)
        assert rendered.split(_FRONTMATTER_FENCE, 1)[1] == (
            "# demo-skill\n\n"
            "## 1. Ask\n\n"
            "## Always\n\n- Ask first. (it is public.)\n"
            "\n"
            "## Never\n\n- Never guess. (guesses publish.)"
        )

    def test_twelve_steps_are_numbered_in_order_with_two_digit_headings(self) -> None:
        # Believed correct: numbering is 1-based and sequential, two-digit headings included.
        skill = _skill(steps=tuple(_cmd(f"S{i}", "uv sync") for i in range(1, 13)))
        rendered = render_claude_skill(skill, _resolve)
        headings = [line for line in rendered.splitlines() if line.startswith("## ")]
        assert headings == [f"## {i}. S{i}" for i in range(1, 13)]

    def test_a_snippet_only_skill_renders_marker_and_resolved_source_exactly(self) -> None:
        # Believed correct: a snippet step is never a decision, so it always shows its fence.
        skill = _skill(
            steps=(
                SkillStep(
                    title="Show",
                    body=SnippetStep(path="x.py", language="python", mask="duration"),
                ),
            )
        )
        rendered = render_claude_skill(skill, _resolve)
        assert rendered.split(_FRONTMATTER_FENCE, 1)[1] == (
            "# demo-skill\n\n"
            "## 1. Show\n\n"
            "<!-- snippet: x.py mask=duration -->\n"
            "```python\n# content of x.py\n```\n"
            "<!-- /snippet -->"
        )

    def test_claude_and_codex_bodies_match_for_a_decision_step_with_verify_and_flag(self) -> None:
        # Believed correct: the two flavours differ only in frontmatter, never in the body.
        skill = _skill(
            steps=(
                SkillStep(
                    title="Ask",
                    body=CommandStep(commands=()),
                    verify="uv run pytest",
                    flag="unstudied",
                ),
                _cmd("Sync", "uv sync"),
            )
        )
        claude = render_claude_skill(skill, _resolve)
        codex = render_codex_skill(skill, _resolve)
        assert claude.split(_FRONTMATTER_FENCE, 1)[1] == codex.split(_FRONTMATTER_FENCE, 1)[1]


class TestAllowedToolsOmissionAdversarial:
    def test_empty_allowed_tools_yields_exactly_name_description_and_when_to_use(self) -> None:
        # Believed correct: with no tools the line is absent; other fields stay in order.
        skill = _skill(allowed_tools=(), when_to_use="use it", steps=())
        rendered = render_claude_skill(skill, _resolve)
        assert rendered.split("\n---\n", 1)[0] + "\n---" == (
            '---\nname: demo-skill\ndescription: "A demo skill."\nwhen_to_use: "use it"\n---'
        )

    def test_a_description_containing_the_allowed_tools_key_does_not_fake_the_line(self) -> None:
        # Believed correct: the description is JSON-quoted on its own line, so the literal text
        # inside it never starts a frontmatter line named allowed-tools.
        skill = _skill(allowed_tools=(), description="allowed-tools: Bash(uv *) is a trap")
        frontmatter = render_claude_skill(skill, _resolve).split("\n---\n", 1)[0]
        assert not [line for line in frontmatter.splitlines() if line.startswith("allowed-tools:")]

    def test_a_step_titled_allowed_tools_does_not_satisfy_the_absence_check(self) -> None:
        # Believed correct: the omission is about the frontmatter line only; a body heading that
        # happens to say "allowed-tools" is not an allowed-tools line.
        skill = _skill(
            allowed_tools=(),
            steps=(SkillStep(title="allowed-tools policy", body=CommandStep(commands=())),),
        )
        frontmatter = render_claude_skill(skill, _resolve).split("\n---\n", 1)[0]
        assert "allowed-tools" not in frontmatter
        assert "## 1. allowed-tools policy" in render_claude_skill(skill, _resolve)
