# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from narrativetrace_skills.catalogue_index import PRO_LISTINGS, SKILLS, find_pro_listing, find_skill


class TestFindSkill:
    def test_finds_a_skill_by_its_canonical_name(self) -> None:
        assert find_skill("narrativetrace-doctor") is SKILLS[0]

    def test_returns_none_for_an_unknown_name(self) -> None:
        assert find_skill("not-a-real-skill") is None


class TestFindProListing:
    def test_finds_a_listing_by_its_canonical_name(self) -> None:
        assert find_pro_listing("narrativetrace-mcp") is PRO_LISTINGS[1]

    def test_returns_none_for_an_unknown_name(self) -> None:
        assert find_pro_listing("not-a-real-listing") is None
