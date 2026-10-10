# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from narrativetrace_skills.marketplace import MarketplaceListing, MarketplaceOwner


def _listing(**overrides: object) -> MarketplaceListing:
    base: dict[str, object] = {
        "name": "narrativetrace-x",
        "owner": MarketplaceOwner(name="NarrativeTrace", url="https://narrativetrace.ai"),
        "description": "The marketplace description.",
        "plugin_description": "The plugin description.",
        "plugin_source": "./.claude",
        "license": "Apache-2.0",
        "homepage": "https://narrativetrace.ai",
        "keywords": ("tracing", "agent-skills"),
    }
    base.update(overrides)
    return MarketplaceListing(**base)  # type: ignore[arg-type]


class TestMarketplaceOwner:
    def test_carries_name_and_url(self) -> None:
        owner = MarketplaceOwner(name="NarrativeTrace", url="https://narrativetrace.ai")
        assert owner.name == "NarrativeTrace"
        assert owner.url == "https://narrativetrace.ai"


class TestMarketplaceListing:
    def test_carries_every_field(self) -> None:
        listing = _listing()
        assert listing.name == "narrativetrace-x"
        assert listing.owner.name == "NarrativeTrace"
        assert listing.description == "The marketplace description."
        assert listing.plugin_description == "The plugin description."
        assert listing.plugin_source == "./.claude"
        assert listing.license == "Apache-2.0"
        assert listing.homepage == "https://narrativetrace.ai"
        assert listing.keywords == ("tracing", "agent-skills")

    def test_keywords_is_a_tuple_even_when_given_a_list(self) -> None:
        # Rendered frontmatter-adjacent output must be byte-stable across renders; a list field
        # would let a caller mutate it after construction (mirrors Skill.steps' own tuple fields).
        listing = _listing(keywords=["tracing", "agent-skills"])
        assert listing.keywords == ("tracing", "agent-skills")
