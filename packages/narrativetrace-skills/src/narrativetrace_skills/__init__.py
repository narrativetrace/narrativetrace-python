# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""narrativetrace-skills — typed catalogue source for NarrativeTrace's agent skills.

See the package README for the shape; ``documentation/agent-skills.md`` for what the two shipped
skills (``narrativetrace-doctor``, ``add-narrative-tracing``) do and how they're built.
"""

from __future__ import annotations

from narrativetrace_skills.catalogue_index import (
    PRO_LISTINGS,
    SKILLS,
    find_pro_listing,
    find_skill,
)
from narrativetrace_skills.lints import (
    CATALOGUE_CHAR_BUDGET,
    catalogue_description_chars,
    catalogue_vocabulary_violations,
    citation_violations,
    listings_disagreeing_with_feature_guide,
    unparseable_commands,
)
from narrativetrace_skills.pro_listing import ProListing, ProListingStatus
from narrativetrace_skills.render.agents_md import (
    AGENTS_MD_BEGIN,
    AGENTS_MD_END,
    extract_agents_md_section,
    render_agents_md_snippet,
    splice_agents_md_section,
)
from narrativetrace_skills.render.claude import render_claude_skill
from narrativetrace_skills.render.codex import render_codex_skill
from narrativetrace_skills.replay import StepReplayResult, replay_skill, run_replay_command
from narrativetrace_skills.skill import (
    COMMAND_VOCABULARY,
    CommandStep,
    FailureNote,
    ReasonedRule,
    Skill,
    SkillClass,
    SkillStep,
    SnippetStep,
    StepBody,
    command_strings,
    description_fits_budget,
    first_token,
    steps_without_verify,
    vocabulary_violations,
)

__version__ = "0.1.2"

__all__ = [
    "AGENTS_MD_BEGIN",
    "AGENTS_MD_END",
    "CATALOGUE_CHAR_BUDGET",
    "COMMAND_VOCABULARY",
    "PRO_LISTINGS",
    "SKILLS",
    "CommandStep",
    "FailureNote",
    "ProListing",
    "ProListingStatus",
    "ReasonedRule",
    "Skill",
    "SkillClass",
    "SkillStep",
    "SnippetStep",
    "StepBody",
    "StepReplayResult",
    "__version__",
    "catalogue_description_chars",
    "catalogue_vocabulary_violations",
    "citation_violations",
    "command_strings",
    "description_fits_budget",
    "extract_agents_md_section",
    "find_pro_listing",
    "find_skill",
    "first_token",
    "listings_disagreeing_with_feature_guide",
    "render_agents_md_snippet",
    "render_claude_skill",
    "render_codex_skill",
    "replay_skill",
    "run_replay_command",
    "splice_agents_md_section",
    "steps_without_verify",
    "unparseable_commands",
    "vocabulary_violations",
]
