# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Every skill in the free Python catalogue, appended to as skills ship."""

from __future__ import annotations

from narrativetrace_skills.catalogue.add_narrative_tracing import ADD_NARRATIVE_TRACING
from narrativetrace_skills.catalogue.add_narrativetrace_clarity import (
    ADD_NARRATIVETRACE_CLARITY,
)
from narrativetrace_skills.catalogue.narrativetrace_debug import NARRATIVETRACE_DEBUG
from narrativetrace_skills.catalogue.narrativetrace_doctor import NARRATIVETRACE_DOCTOR
from narrativetrace_skills.catalogue.narrativetrace_feedback import NARRATIVETRACE_FEEDBACK
from narrativetrace_skills.catalogue.narrativetrace_verify import NARRATIVETRACE_VERIFY
from narrativetrace_skills.catalogue.pro_listings import PRO_LISTINGS
from narrativetrace_skills.marketplace import MarketplaceListing, MarketplaceOwner
from narrativetrace_skills.pro_listing import ProListing
from narrativetrace_skills.skill import Skill

SKILLS: tuple[Skill, ...] = (
    NARRATIVETRACE_DOCTOR,
    ADD_NARRATIVE_TRACING,
    NARRATIVETRACE_FEEDBACK,
    ADD_NARRATIVETRACE_CLARITY,
    NARRATIVETRACE_VERIFY,
    NARRATIVETRACE_DEBUG,
)

# How this repository presents SKILLS to a Claude Code plugin marketplace. One listing, whose
# name is the repository's own runtime slug: marketplace name and plugin name are the same
# string because a marketplace name is unique per user, and every runtime in the family ships
# skills under the same canonical names. The plugin's source is the rendered Claude-flavour
# pages' own directory, so the plugin carries exactly those pages and nothing else of this repo.
MARKETPLACE: MarketplaceListing = MarketplaceListing(
    name="narrativetrace-python",
    owner=MarketplaceOwner(name="NarrativeTrace", url="https://narrativetrace.ai"),
    description="The NarrativeTrace agent skills for Python.",
    plugin_description=(
        "Install NarrativeTrace in a Python project and reach a first trace, diagnose an "
        "install that traces nothing, add a naming-clarity report and gate, report a defect in "
        "NarrativeTrace itself, verify a change by reading what the code actually did, and debug "
        "a wrong result by the span where its value diverged."
    ),
    plugin_source="./.claude",
    license="Apache-2.0",
    homepage="https://narrativetrace.ai",
    keywords=("narrativetrace", "python", "tracing", "observability", "agent-skills"),
)


def find_skill(canonical_name: str) -> Skill | None:
    return next((skill for skill in SKILLS if skill.canonical_name == canonical_name), None)


def find_pro_listing(canonical_name: str) -> ProListing | None:
    return next(
        (listing for listing in PRO_LISTINGS if listing.canonical_name == canonical_name), None
    )


__all__ = ["PRO_LISTINGS", "SKILLS", "find_pro_listing", "find_skill"]
