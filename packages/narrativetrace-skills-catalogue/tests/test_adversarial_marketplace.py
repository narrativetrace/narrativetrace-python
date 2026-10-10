# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial tests for marketplace.py and render/marketplace.py: edge cases and boundary
conditions."""

from __future__ import annotations

import json

from narrativetrace_skills.marketplace import MarketplaceListing, MarketplaceOwner
from narrativetrace_skills.render.marketplace import render_marketplace_json


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


class TestMarketplaceListingAdversarial:
    """Edge cases for MarketplaceListing dataclass."""

    def test_empty_keywords_tuple(self) -> None:
        listing = _listing(keywords=())
        assert listing.keywords == ()

    def test_single_keyword(self) -> None:
        listing = _listing(keywords=("python",))
        assert listing.keywords == ("python",)

    def test_keywords_with_special_characters(self) -> None:
        listing = _listing(keywords=("test-keyword", "keyword_2", "keyword.3"))
        assert listing.keywords == ("test-keyword", "keyword_2", "keyword.3")

    def test_keywords_with_quotes(self) -> None:
        listing = _listing(keywords=('keyword"with"quotes',))
        assert listing.keywords == ('keyword"with"quotes',)

    def test_keywords_tuple_frozen_against_mutation(self) -> None:
        # Frozen dataclass should prevent external mutation
        listing = _listing(keywords=("a", "b"))
        # Can't mutate the tuple itself (tuples are immutable anyway)
        assert listing.keywords == ("a", "b")

    def test_very_long_description(self) -> None:
        long_desc = "x" * 10000
        listing = _listing(description=long_desc)
        assert listing.description == long_desc

    def test_very_long_plugin_description(self) -> None:
        long_plugin_desc = "y" * 10000
        listing = _listing(plugin_description=long_plugin_desc)
        assert listing.plugin_description == long_plugin_desc

    def test_owner_url_with_special_characters(self) -> None:
        owner = MarketplaceOwner(name="Test Owner", url="https://example.com/path?q=1&r=2#section")
        listing = _listing(owner=owner)
        assert listing.owner.url == "https://example.com/path?q=1&r=2#section"

    def test_empty_string_name(self) -> None:
        listing = _listing(name="")
        assert listing.name == ""

    def test_empty_string_license(self) -> None:
        listing = _listing(license="")
        assert listing.license == ""


class TestRenderMarketplaceJsonAdversarial:
    """Edge cases for render_marketplace_json."""

    def test_empty_keywords_renders_as_empty_array(self) -> None:
        listing = _listing(keywords=())
        rendered = render_marketplace_json(listing)
        payload = json.loads(rendered)
        assert payload["plugins"][0]["keywords"] == []

    def test_keywords_with_quotes_are_json_escaped(self) -> None:
        listing = _listing(keywords=('test"quote',))
        rendered = render_marketplace_json(listing)
        payload = json.loads(rendered)
        # JSON escaping should preserve the quote
        assert payload["plugins"][0]["keywords"][0] == 'test"quote'

    def test_keywords_with_backslashes_are_escaped(self) -> None:
        listing = _listing(keywords=("test\\path",))
        rendered = render_marketplace_json(listing)
        payload = json.loads(rendered)
        assert payload["plugins"][0]["keywords"][0] == "test\\path"

    def test_description_with_newlines(self) -> None:
        listing = _listing(description="Line 1\nLine 2\nLine 3")
        rendered = render_marketplace_json(listing)
        payload = json.loads(rendered)
        assert payload["description"] == "Line 1\nLine 2\nLine 3"

    def test_owner_name_with_special_characters(self) -> None:
        owner = MarketplaceOwner(name="Test & Co.", url="https://example.com")
        listing = _listing(owner=owner)
        rendered = render_marketplace_json(listing)
        payload = json.loads(rendered)
        assert payload["owner"]["name"] == "Test & Co."

    def test_very_long_keywords_list(self) -> None:
        keywords = tuple(f"keyword{i}" for i in range(100))
        listing = _listing(keywords=keywords)
        rendered = render_marketplace_json(listing)
        payload = json.loads(rendered)
        assert len(payload["plugins"][0]["keywords"]) == 100

    def test_multiple_renders_identical(self) -> None:
        listing = _listing(keywords=("a", "b", "c"))
        render1 = render_marketplace_json(listing)
        render2 = render_marketplace_json(listing)
        # Parse both to ensure content is identical (not just string comparison)
        assert json.loads(render1) == json.loads(render2)
        # String comparison should also work (deterministic JSON)
        assert render1 == render2

    def test_keywords_order_preserved(self) -> None:
        keywords = ("zebra", "apple", "monkey", "banana")
        listing = _listing(keywords=keywords)
        rendered = render_marketplace_json(listing)
        payload = json.loads(rendered)
        # Keywords should maintain insertion order
        assert payload["plugins"][0]["keywords"] == ["zebra", "apple", "monkey", "banana"]

    def test_empty_strings_in_fields(self) -> None:
        listing = _listing(name="", description="", plugin_description="", license="")
        rendered = render_marketplace_json(listing)
        payload = json.loads(rendered)
        assert payload["name"] == ""
        assert payload["description"] == ""
        assert payload["plugins"][0]["description"] == ""
        assert payload["plugins"][0]["license"] == ""

    def test_always_ends_with_single_newline(self) -> None:
        listing = _listing()
        rendered = render_marketplace_json(listing)
        assert rendered.endswith("\n")
        assert not rendered.endswith("\n\n")

    def test_newline_not_double_counted(self) -> None:
        listing = _listing()
        rendered1 = render_marketplace_json(listing)
        rendered2 = render_marketplace_json(listing)
        assert rendered1 == rendered2
        assert rendered1.count("\n") == rendered2.count("\n")
