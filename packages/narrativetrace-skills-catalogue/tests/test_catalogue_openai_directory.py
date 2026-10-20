# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""How this repository presents its catalogue to the OpenAI plugin directory."""

from __future__ import annotations

from narrativetrace_skills.catalogue_index import MARKETPLACE, OPENAI_DIRECTORY, SKILLS
from narrativetrace_skills.openai_listing import MAX_LISTING_FIELD_LENGTH


class TestCatalogueOpenAiDirectory:
    def test_is_composed_from_the_same_marketplace_listing(self) -> None:
        assert OPENAI_DIRECTORY.base is MARKETPLACE

    def test_the_plugin_is_named_after_the_runtimes_marketplace_listing(self) -> None:
        assert OPENAI_DIRECTORY.base.name == "narrativetrace-python"

    def test_the_display_name_names_the_runtime(self) -> None:
        assert OPENAI_DIRECTORY.display_name == "NarrativeTrace for Python"

    def test_the_short_description_fits_the_directorys_ceiling(self) -> None:
        assert len(OPENAI_DIRECTORY.short_description) <= MAX_LISTING_FIELD_LENGTH

    def test_the_default_prompts_are_three_trigger_phrases_of_the_catalogues_own_skills(
        self,
    ) -> None:
        assert len(OPENAI_DIRECTORY.default_prompts) == 3
        for prompt in OPENAI_DIRECTORY.default_prompts:
            assert any(f"'{prompt}'" in skill.description for skill in SKILLS), prompt

    def test_the_website_is_the_base_listings_homepage(self) -> None:
        assert OPENAI_DIRECTORY.website_url == MARKETPLACE.homepage

    def test_the_listing_values_are_the_ones_the_design_record_fixes(self) -> None:
        assert OPENAI_DIRECTORY.category == "Developer Tools"
        assert OPENAI_DIRECTORY.capabilities == ("Read", "Write")
        assert OPENAI_DIRECTORY.brand_color == "#00845a"
