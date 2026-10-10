# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import pytest
from narrativetrace_skills.lints import (
    CATALOGUE_CHAR_BUDGET,
    allowed_tools_violations,
    catalogue_description_chars,
    catalogue_vocabulary_violations,
    citation_violations,
    listings_disagreeing_with_feature_guide,
    promotion_not_pre_approved,
    publishing_not_pre_approved,
    unparseable_commands,
)
from narrativetrace_skills.pro_listing import ProListing
from narrativetrace_skills.skill import CommandStep, FailureNote, ReasonedRule, Skill, SkillStep


def _skill(**overrides: object) -> Skill:
    base: dict[str, object] = {
        "canonical_name": "demo-skill",
        "skill_class": "mechanical",
        "description": "A demo skill.",
        "fixture": "examples/demo",
        "steps": (),
        "allowed_tools": ("uv",),
    }
    base.update(overrides)
    return Skill(**base)  # type: ignore[arg-type]


class TestCatalogueDescriptionChars:
    def test_sums_across_the_catalogue(self) -> None:
        skills = (_skill(description="abc"), _skill(description="de"))
        assert catalogue_description_chars(skills) == 5

    def test_budget_is_well_under_the_estimated_token_cliff(self) -> None:
        assert CATALOGUE_CHAR_BUDGET == 40_000


class TestCatalogueVocabularyViolations:
    def test_flags_across_multiple_skills(self) -> None:
        skills = (
            _skill(
                canonical_name="a",
                steps=(SkillStep(title="s", body=CommandStep(commands=("npm i",))),),
            ),
            _skill(
                canonical_name="b",
                steps=(SkillStep(title="s", body=CommandStep(commands=("uv sync",))),),
            ),
        )
        assert catalogue_vocabulary_violations(skills) == ("a: npm i",)


class TestAllowedToolsViolations:
    def test_no_violations_for_vocabulary_commands(self) -> None:
        skill = _skill(allowed_tools=("uv", "git"))
        assert allowed_tools_violations((skill,)) == ()

    def test_rejects_a_pre_spelled_claude_tool_pattern(self) -> None:
        skill = _skill(allowed_tools=("Bash(git *)",))
        violations = allowed_tools_violations((skill,))
        assert len(violations) == 1
        assert "rendered platform spelling" in violations[0]
        assert "demo-skill" in violations[0]

    def test_rejects_a_command_outside_the_closed_vocabulary(self) -> None:
        skill = _skill(allowed_tools=("npm",))
        violations = allowed_tools_violations((skill,))
        assert len(violations) == 1
        assert "outside the vocabulary" in violations[0]

    def test_flags_across_multiple_skills(self) -> None:
        skills = (
            _skill(canonical_name="a", allowed_tools=("npm",)),
            _skill(canonical_name="b", allowed_tools=("uv",)),
        )
        violations = allowed_tools_violations(skills)
        assert len(violations) == 1
        assert violations[0].startswith("a:")


class TestUnparseableCommands:
    def test_empty_command_is_unparseable(self) -> None:
        skill = _skill(steps=(SkillStep(title="s", body=CommandStep(commands=("   ",))),))
        violations = unparseable_commands((skill,))
        assert violations == ("demo-skill: '   '",)

    def test_a_normal_command_is_not_flagged(self) -> None:
        skill = _skill(steps=(SkillStep(title="s", body=CommandStep(commands=("uv sync",))),))
        assert unparseable_commands((skill,)) == ()


class TestListingsDisagreeingWithFeatureGuide:
    def test_agreement_when_the_status_text_appears_verbatim(self) -> None:
        listing = ProListing(
            canonical_name="x",
            prompt="p",
            delivers="d",
            needs="n",
            comes_from="c",
            status="shipped",
            feature_guide_status_text="Pro",
        )
        assert (
            listings_disagreeing_with_feature_guide((listing,), "| Feature | Pro | Notes |") == ()
        )

    def test_flags_a_listing_whose_status_text_is_absent(self) -> None:
        listing = ProListing(
            canonical_name="x",
            prompt="p",
            delivers="d",
            needs="n",
            comes_from="c",
            status="planned",
            feature_guide_status_text="Planned (Pro, gated)",
        )
        assert listings_disagreeing_with_feature_guide((listing,), "nothing relevant here") == (
            "x",
        )


class TestCitationViolations:
    def test_no_violation_in_ordinary_prose(self) -> None:
        skill = _skill(description="Diagnoses a project.")
        assert citation_violations(skill) == ()

    def test_flags_a_section_mark(self) -> None:
        skill = _skill(description="See §2 for details.")
        violations = citation_violations(skill)
        assert len(violations) == 1
        assert "section-mark citation" in violations[0]

    def test_flags_an_unknown_markdown_filename(self) -> None:
        skill = _skill(description="See skill-design.md for the rationale.")
        violations = citation_violations(skill)
        assert any("skill-design.md" in v for v in violations)

    def test_a_known_repo_markdown_file_is_not_flagged(self) -> None:
        skill = _skill(description="See troubleshooting.md for common issues.")
        violations = citation_violations(skill, frozenset({"troubleshooting.md"}))
        assert violations == ()

    def test_checks_failure_notes_and_rules_too(self) -> None:
        skill = _skill(
            steps=(
                SkillStep(
                    title="s",
                    body=CommandStep(commands=("uv sync",)),
                    failure=(FailureNote(symptom="§3 fails", cause="c", fix="f"),),
                ),
            ),
            always=(ReasonedRule(rule="see §4", reason="r"),),
        )
        violations = citation_violations(skill)
        assert len(violations) == 2

    def test_checks_a_step_condition_too(self) -> None:
        skill = _skill(
            steps=(
                SkillStep(
                    title="s",
                    body=CommandStep(commands=("uv sync",)),
                    condition="only when §5 says so",
                ),
            )
        )
        violations = citation_violations(skill)
        assert len(violations) == 1
        assert "section-mark citation" in violations[0]

    def test_never_flags_the_canonical_name_itself(self) -> None:
        skill = _skill(canonical_name="narrativetrace-doctor", description="ok")
        assert citation_violations(skill) == ()


_FILES_AN_ISSUE = "uv run narrativetrace feedback url --category library --step s"


def _reporting_skill(
    *commands: str, allowed_tools: tuple[str, ...], name: str = "reporter"
) -> Skill:
    return _skill(
        canonical_name=name,
        allowed_tools=allowed_tools,
        steps=tuple(SkillStep(title="s", body=CommandStep(commands=(c,))) for c in commands),
    )


class TestPublishingNotPreApproved:
    """The violation branch is never reached by the real catalogue (it declares nothing), so every
    branch is exercised here over synthetic skills."""

    def test_flags_a_skill_that_pre_approves_its_own_publishing_command(self) -> None:
        skill = _reporting_skill(_FILES_AN_ISSUE, allowed_tools=("uv",))
        assert publishing_not_pre_approved((skill,)) == (
            f'reporter: declares allowed tool "uv", which pre-approves its own publishing command '
            f'"{_FILES_AN_ISSUE}" -- a skill that files something public must let the harness ask',
        )

    def test_accepts_the_same_skill_declaring_no_allowed_tool(self) -> None:
        skill = _reporting_skill(_FILES_AN_ISSUE, allowed_tools=())
        assert publishing_not_pre_approved((skill,)) == ()

    def test_ignores_a_skill_whose_commands_publish_nothing(self) -> None:
        skill = _reporting_skill("uv run narrativetrace doctor", allowed_tools=("uv", "git"))
        assert publishing_not_pre_approved((skill,)) == ()

    def test_a_pre_approved_tool_that_is_not_the_publishing_commands_is_not_a_violation(
        self,
    ) -> None:
        skill = _reporting_skill(_FILES_AN_ISSUE, allowed_tools=("git",))
        assert publishing_not_pre_approved((skill,)) == ()

    def test_matches_on_the_word_not_on_a_longer_word_that_contains_it(self) -> None:
        skill = _reporting_skill("uv run narrativetrace feedbacks", allowed_tools=("uv",))
        assert publishing_not_pre_approved((skill,)) == ()

    def test_names_every_publishing_command_and_every_offending_skill(self) -> None:
        draft = "uv run narrativetrace feedback draft --category doctor"
        skills = (
            _reporting_skill(draft, _FILES_AN_ISSUE, allowed_tools=("uv",), name="a"),
            _reporting_skill(_FILES_AN_ISSUE, allowed_tools=("uv",), name="b"),
            _reporting_skill(_FILES_AN_ISSUE, allowed_tools=(), name="c"),
        )
        violations = publishing_not_pre_approved(skills)
        assert [v.split(":")[0] for v in violations] == ["a", "a", "b"]


_PROMOTES = "uv run narrativetrace-approve"


class TestPromotionNotPreApproved:
    """A skill that promotes a reviewed ``.received.nt`` to a committed ``.approved.nt`` must
    declare no allowed tool that pre-approves the promotion: the gate says the turn that asked
    stops, and a pre-approved tool would let the promotion run in it anyway."""

    def test_flags_a_skill_that_pre_approves_its_own_promotion(self) -> None:
        skill = _reporting_skill(_PROMOTES, allowed_tools=("uv",), name="pinner")
        assert promotion_not_pre_approved((skill,)) == (
            'pinner: declares allowed tool "uv", which pre-approves its own promotion '
            f'"{_PROMOTES}" -- a skill that pins a baseline must let the harness ask',
        )

    def test_a_skill_declaring_nothing_is_clean(self) -> None:
        skill = _reporting_skill(_PROMOTES, allowed_tools=())
        assert promotion_not_pre_approved((skill,)) == ()

    def test_a_promotion_in_a_verify_line_counts_too(self) -> None:
        skill = _skill(
            canonical_name="pinner",
            allowed_tools=("uv",),
            steps=(
                SkillStep(title="s", body=CommandStep(commands=("uv sync",)), verify=_PROMOTES),
            ),
        )
        assert len(promotion_not_pre_approved((skill,))) == 1

    @pytest.mark.parametrize(
        "command",
        ["uv run poe approve", "uv run narrativetrace-approve --approved-dir test-narratives"],
    )
    def test_every_spelling_of_the_approve_verb_is_a_promotion(self, command: str) -> None:
        skill = _reporting_skill(command, allowed_tools=("uv",))
        assert len(promotion_not_pre_approved((skill,))) == 1

    @pytest.mark.parametrize(
        "command",
        [
            "uv run narrativetrace-approved",
            "uv run narrativetrace-approves",
            "uv run poe approve-all",
            "uv run poe approved",
            "uv run pytest",
        ],
    )
    def test_a_near_miss_is_not_a_promotion(self, command: str) -> None:
        skill = _reporting_skill(command, allowed_tools=("uv",))
        assert promotion_not_pre_approved((skill,)) == ()

    def test_a_pre_approved_tool_other_than_the_promotions_is_not_a_violation(self) -> None:
        skill = _reporting_skill(_PROMOTES, allowed_tools=("git",))
        assert promotion_not_pre_approved((skill,)) == ()
