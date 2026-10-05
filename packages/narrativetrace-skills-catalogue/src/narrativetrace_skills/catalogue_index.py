# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Every skill in the free Python catalogue, appended to as skills ship."""

from __future__ import annotations

from narrativetrace_skills.catalogue.add_narrative_tracing import ADD_NARRATIVE_TRACING
from narrativetrace_skills.catalogue.narrativetrace_doctor import NARRATIVETRACE_DOCTOR
from narrativetrace_skills.catalogue.pro_listings import PRO_LISTINGS
from narrativetrace_skills.pro_listing import ProListing
from narrativetrace_skills.skill import Skill

SKILLS: tuple[Skill, ...] = (NARRATIVETRACE_DOCTOR, ADD_NARRATIVE_TRACING)


def find_skill(canonical_name: str) -> Skill | None:
    return next((skill for skill in SKILLS if skill.canonical_name == canonical_name), None)


def find_pro_listing(canonical_name: str) -> ProListing | None:
    return next(
        (listing for listing in PRO_LISTINGS if listing.canonical_name == canonical_name), None
    )


__all__ = ["PRO_LISTINGS", "SKILLS", "find_pro_listing", "find_skill"]
