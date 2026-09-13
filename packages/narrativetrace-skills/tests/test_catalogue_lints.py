# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A lints (skill-harness-design.md's schema/vocabulary/budget/index-agreement tier): no LLM,
seconds, per commit — rides ``uv run poe check`` like every other package's own test suite, over
the REAL shipped catalogue (never a synthetic fixture skill, except where noted)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from narrativetrace_skills.catalogue_index import PRO_LISTINGS, SKILLS
from narrativetrace_skills.lints import (
    CATALOGUE_CHAR_BUDGET,
    catalogue_description_chars,
    catalogue_vocabulary_violations,
    citation_violations,
    listings_disagreeing_with_feature_guide,
    unparseable_commands,
)
from narrativetrace_skills.skill import description_fits_budget, steps_without_verify

# Steps a skill's OWN design has explicitly flagged as not carrying a mechanical verify.
_JUDGMENTAL_STEP_TITLES = frozenset(
    {
        "Read the rendered trace before asserting",
        "Approval flow: diff the structural trace, not just values",
    }
)


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


_REPO_ROOT = _repo_root()

_SKIPPED_DIRS = frozenset(
    {"node_modules", "dist", "coverage", ".git", ".venv", "mutants", "__pycache__", "build"}
)


def _repo_markdown_basenames(root: Path) -> frozenset[str]:
    """Every ``.md`` file actually present in the repository, lowercased basename only — the same
    shape :func:`citation_violations` compares a rendered skill's filename mentions against."""
    names: set[str] = set()
    queue = [root]
    while queue:
        directory = queue.pop()
        for entry in directory.iterdir():
            if entry.is_dir():
                if not entry.name.startswith(".") and entry.name not in _SKIPPED_DIRS:
                    queue.append(entry)
            elif entry.name.lower().endswith(".md"):
                names.add(entry.name.lower())
    return frozenset(names)


class TestCatalogueIndex:
    def test_is_non_empty(self) -> None:
        assert len(SKILLS) > 0

    def test_has_no_duplicate_canonical_names(self) -> None:
        names = [skill.canonical_name for skill in SKILLS]
        assert len(set(names)) == len(names)

    def test_every_description_fits_the_per_skill_budget(self) -> None:
        for skill in SKILLS:
            assert description_fits_budget(skill), skill.canonical_name

    def test_catalogue_wide_description_budget_stays_under_the_silent_drop_cliff(self) -> None:
        assert catalogue_description_chars(SKILLS) < CATALOGUE_CHAR_BUDGET

    def test_every_commands_string_parses_to_a_non_empty_first_token(self) -> None:
        assert unparseable_commands(SKILLS) == ()

    def test_every_commands_strings_first_token_is_in_the_closed_vocabulary(self) -> None:
        assert catalogue_vocabulary_violations(SKILLS) == ()

    def test_every_non_judgmental_step_carries_a_verify(self) -> None:
        for skill in SKILLS:
            missing = [
                title
                for title in steps_without_verify(skill)
                if title not in _JUDGMENTAL_STEP_TITLES
            ]
            assert missing == [], skill.canonical_name

    def test_an_unstudied_step_is_flagged_not_silently_unverified(self) -> None:
        for skill in SKILLS:
            for step in skill.steps:
                if step.verify is None and step.title not in _JUDGMENTAL_STEP_TITLES:
                    assert step.flag, (
                        f"{skill.canonical_name}: {step.title} has neither verify nor flag"
                    )

    def test_every_always_never_rule_carries_a_reason(self) -> None:
        for skill in SKILLS:
            for rule in (*skill.always, *skill.never):
                assert len(rule.reason) > 0, skill.canonical_name


class TestNoPlanningNoteCitationSurvives:
    def test_every_skill_is_clean(self) -> None:
        basenames = _repo_markdown_basenames(_REPO_ROOT)
        for skill in SKILLS:
            assert citation_violations(skill, basenames) == (), skill.canonical_name

    def test_still_flags_a_section_mark_and_an_unknown_filename_lint_sanity(self) -> None:
        basenames = _repo_markdown_basenames(_REPO_ROOT)
        base = SKILLS[0]
        skill = dataclasses.replace(
            base, description=f"See agent-skills-2026-09-12.md §7 ruling 3. {base.description}"
        )
        violations = citation_violations(skill, basenames)
        assert len(violations) > 0
        assert any("§" in v for v in violations)
        assert any("agent-skills-2026-09-12.md" in v for v in violations)


class TestProListingsAgreeWithTheFeatureGuide:
    def test_has_at_least_one_listing(self) -> None:
        assert len(PRO_LISTINGS) > 0

    def test_every_listings_status_text_still_appears_in_the_feature_guide(self) -> None:
        feature_guide = (_REPO_ROOT / "documentation" / "feature-guide.md").read_text(
            encoding="utf-8"
        )
        assert listings_disagreeing_with_feature_guide(PRO_LISTINGS, feature_guide) == ()
