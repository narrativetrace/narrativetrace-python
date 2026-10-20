# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The OpenAI plugin directory's own listing fields beside the vendor-neutral
:class:`~narrativetrace_skills.marketplace.MarketplaceListing`: ``display_name`` and
``short_description`` carry the directory's 30-character ceiling, so a longer value never reaches
a render."""

from __future__ import annotations

import pytest
from narrativetrace_skills.marketplace import MarketplaceListing, MarketplaceOwner
from narrativetrace_skills.openai_listing import MAX_LISTING_FIELD_LENGTH, OpenAiListing


def _base() -> MarketplaceListing:
    return MarketplaceListing(
        name="narrativetrace-x",
        owner=MarketplaceOwner(name="NarrativeTrace", url="https://narrativetrace.ai"),
        description="The marketplace description.",
        plugin_description="The plugin description.",
        plugin_source="./.claude",
        license="Apache-2.0",
        homepage="https://narrativetrace.ai",
        keywords=("tracing", "agent-skills"),
    )


def _listing(**overrides: object) -> OpenAiListing:
    fields: dict[str, object] = {
        "base": _base(),
        "display_name": "NarrativeTrace for X",
        "short_description": "NarrativeTrace X skills",
        "category": "Developer Tools",
        "capabilities": ("Read", "Write"),
        "default_prompts": ("add narrative tracing to my service",),
        "brand_color": "#4A4A4A",
        "website_url": "https://narrativetrace.ai",
    }
    fields.update(overrides)
    return OpenAiListing(**fields)  # type: ignore[arg-type]


class TestOpenAiListing:
    def test_carries_the_base_listing_and_the_directory_only_fields(self) -> None:
        listing = _listing()
        assert listing.base == _base()
        assert listing.display_name == "NarrativeTrace for X"
        assert listing.short_description == "NarrativeTrace X skills"
        assert listing.category == "Developer Tools"
        assert listing.capabilities == ("Read", "Write")
        assert listing.default_prompts == ("add narrative tracing to my service",)
        assert listing.brand_color == "#4A4A4A"
        assert listing.website_url == "https://narrativetrace.ai"

    def test_the_ceiling_is_thirty_characters(self) -> None:
        assert MAX_LISTING_FIELD_LENGTH == 30

    @pytest.mark.parametrize("field", ["display_name", "short_description"])
    def test_a_thirty_character_value_is_accepted(self, field: str) -> None:
        assert len(getattr(_listing(**{field: "x" * 30}), field)) == 30

    @pytest.mark.parametrize("field", ["display_name", "short_description"])
    def test_a_thirty_one_character_value_is_rejected_naming_the_field(self, field: str) -> None:
        with pytest.raises(ValueError, match=rf"\A{field} must be at most 30 characters, was 31\Z"):
            _listing(**{field: "x" * 31})

    def test_capabilities_and_prompts_are_tuples_even_when_given_lists(self) -> None:
        listing = _listing(capabilities=["Read"], default_prompts=["prompt"])
        assert listing.capabilities == ("Read",)
        assert listing.default_prompts == ("prompt",)


class TestTheCeilingCountsCharactersNotBytes:
    def test_thirty_multibyte_characters_are_accepted(self) -> None:
        assert len(_listing(display_name="é" * 30).display_name.encode()) == 60
