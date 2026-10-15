# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The Cursor plugin manifest pair (Phase 8, platform pointers), rendered from the SAME listing
that renders the Claude marketplace file. Field names follow Cursor's plugin reference."""

from __future__ import annotations

import json

import pytest
from narrativetrace_skills.marketplace import MarketplaceListing, MarketplaceOwner
from narrativetrace_skills.render.cursor_plugin import (
    RULE_PATH,
    SKILLS_PATH,
    render_cursor_marketplace_json,
    render_cursor_plugin_json,
)
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


class TestThePluginManifest:
    def test_is_well_formed_json_ending_in_a_newline(self) -> None:
        rendered = render_cursor_plugin_json(_listing())

        assert rendered.endswith("}\n")
        json.loads(rendered)

    def test_carries_the_listing_and_points_at_the_skills_and_the_one_rule(self) -> None:
        assert json.loads(render_cursor_plugin_json(_listing())) == {
            "name": "narrativetrace-x",
            "description": "The plugin description.",
            "author": {"name": "NarrativeTrace"},
            "license": "Apache-2.0",
            "homepage": "https://narrativetrace.ai",
            "keywords": ["tracing", "agent-skills"],
            "skills": "./.agents/skills/",
            "rules": "./.cursor/rules/narrativetrace.mdc",
        }

    def test_the_paths_are_the_open_standard_pages_and_the_rule_init_writes(self) -> None:
        assert (SKILLS_PATH, RULE_PATH) == (
            "./.agents/skills/",
            "./.cursor/rules/narrativetrace.mdc",
        )

    def test_carries_no_commands_hooks_agents_or_mcp_servers_and_no_version(self) -> None:
        payload = json.loads(render_cursor_plugin_json(_listing()))

        assert not {"commands", "hooks", "agents", "mcpServers", "version"} & set(payload)

    def test_renders_byte_identically_every_time(self) -> None:
        listing = _listing()

        assert render_cursor_plugin_json(listing) == render_cursor_plugin_json(listing)

    def test_escapes_what_json_cannot_carry_raw(self) -> None:
        hostile = 'A "quoted" \\ name\twith\na newline and a \x01 control char.'

        payload = json.loads(render_cursor_plugin_json(_listing(plugin_description=hostile)))

        assert payload["description"] == hostile


class TestTheMarketplaceManifest:
    def test_names_the_marketplace_its_owner_and_one_plugin_at_the_repository_root(self) -> None:
        assert json.loads(render_cursor_marketplace_json(_listing())) == {
            "name": "narrativetrace-x",
            "owner": {"name": "NarrativeTrace"},
            "metadata": {"description": "The marketplace description."},
            "plugins": [
                {
                    "name": "narrativetrace-x",
                    "source": ".",
                    "description": "The plugin description.",
                    "license": "Apache-2.0",
                    "homepage": "https://narrativetrace.ai",
                    "keywords": ["tracing", "agent-skills"],
                }
            ],
        }

    def test_carries_no_version_key_anywhere(self) -> None:
        assert '"version"' not in render_cursor_marketplace_json(_listing())

    def test_ends_in_a_newline_and_is_stable(self) -> None:
        listing = _listing()

        rendered = render_cursor_marketplace_json(listing)

        assert rendered.endswith("}\n")
        assert rendered == render_cursor_marketplace_json(listing)


class TestOneListingTwoVendors:
    """Parity between the two parallel render paths: every fact of the Claude listing reaches the
    Cursor files, so the two vendors can never describe the repository differently."""

    @pytest.mark.parametrize(
        "field", ["name", "plugin_description", "license", "homepage", "description"]
    )
    def test_a_changed_listing_field_changes_the_cursor_files_too(self, field: str) -> None:
        marker = f"changed-{field}"
        listing = _listing(**{field: marker})

        assert marker in render_marketplace_json(listing)
        assert marker in render_cursor_plugin_json(listing) + render_cursor_marketplace_json(
            listing
        )

    def test_the_keywords_reach_both_cursor_files(self) -> None:
        listing = _listing(keywords=("alpha", "beta"))

        assert json.loads(render_cursor_plugin_json(listing))["keywords"] == ["alpha", "beta"]
        plugin = json.loads(render_cursor_marketplace_json(listing))["plugins"][0]
        assert plugin["keywords"] == ["alpha", "beta"]
