# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from narrativetrace_skills.lints import (
    CATALOGUE_CHAR_BUDGET,
    catalogue_description_chars,
    catalogue_vocabulary_violations,
    citation_violations,
    listings_disagreeing_with_feature_guide,
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

    def test_never_flags_the_canonical_name_itself(self) -> None:
        skill = _skill(canonical_name="narrativetrace-doctor", description="ok")
        assert citation_violations(skill) == ()
