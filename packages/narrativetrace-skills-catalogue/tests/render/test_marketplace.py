# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
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


class TestRenderMarketplaceJson:
    def test_is_well_formed_json_ending_in_a_newline(self) -> None:
        rendered = render_marketplace_json(_listing())
        assert rendered.endswith("\n")
        json.loads(rendered)

    def test_names_the_marketplace_and_its_owner(self) -> None:
        payload = json.loads(render_marketplace_json(_listing()))
        assert payload["name"] == "narrativetrace-x"
        assert payload["owner"] == {"name": "NarrativeTrace", "url": "https://narrativetrace.ai"}
        assert payload["description"] == "The marketplace description."

    def test_carries_one_plugin_entry_rooted_at_the_rendered_pages(self) -> None:
        payload = json.loads(render_marketplace_json(_listing()))
        assert payload["plugins"] == [
            {
                "name": "narrativetrace-x",
                "source": "./.claude",
                "description": "The plugin description.",
                "license": "Apache-2.0",
                "homepage": "https://narrativetrace.ai",
                "keywords": ["tracing", "agent-skills"],
            }
        ]

    def test_renders_byte_identically_every_time(self) -> None:
        listing = _listing()
        assert render_marketplace_json(listing) == render_marketplace_json(listing)

    def test_carries_no_version_key_anywhere(self) -> None:
        rendered = render_marketplace_json(_listing())
        assert '"version"' not in rendered

    def test_escapes_every_character_json_cannot_carry_raw(self) -> None:
        hostile = _listing(
            description='A "quoted" \\ name\twith\na newline and a \x01 control char.'
        )
        rendered = render_marketplace_json(hostile)
        payload = json.loads(rendered)
        assert payload["description"] == (
            'A "quoted" \\ name\twith\na newline and a \x01 control char.'
        )
