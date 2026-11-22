# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

import json

from narrativetrace_skills.claude_listing import ClaudeListing
from narrativetrace_skills.marketplace import MarketplaceListing, MarketplaceOwner
from narrativetrace_skills.render.claude_plugin_json import (
    CLAUDE_PLUGIN_ICON_PATH,
    render_claude_plugin_json,
)


def _base(**overrides: object) -> MarketplaceListing:
    base: dict[str, object] = {
        "name": "narrativetrace-x",
        "owner": MarketplaceOwner(name="NarrativeTrace", url="https://narrativetrace.ai"),
        "description": "The marketplace description.",
        "plugin_description": "The plugin description.",
        "plugin_source": "./.claude",
        "license": "Apache-2.0",
        "homepage": "https://narrativetrace.ai",
        "repository": "https://github.com/narrativetrace/narrativetrace-x",
        "keywords": ("tracing", "agent-skills"),
    }
    base.update(overrides)
    return MarketplaceListing(**base)  # type: ignore[arg-type]


def _listing(**overrides: object) -> ClaudeListing:
    return ClaudeListing(
        base=_base(**overrides),
        display_name="NarrativeTrace for X",
        support_url="https://github.com/narrativetrace/narrativetrace-x/issues",
        privacy_policy_url="https://narrativetrace.ai/privacy",
        documentation_url="https://github.com/narrativetrace/narrativetrace-x/tree/main/documentation",
    )


class TestRenderClaudePluginJson:
    def test_is_well_formed_json_ending_in_a_newline(self) -> None:
        rendered = render_claude_plugin_json(_listing())
        assert rendered.endswith("}\n")
        json.loads(rendered)

    def test_carries_the_manifest_keys_in_the_documented_order(self) -> None:
        payload = json.loads(render_claude_plugin_json(_listing()))
        assert list(payload) == [
            "name",
            "description",
            "author",
            "homepage",
            "repository",
            "license",
            "keywords",
            "displayName",
            "supportUrl",
            "privacyPolicyUrl",
            "documentationUrl",
            "icon",
        ]

    def test_takes_every_value_from_the_listing(self) -> None:
        payload = json.loads(render_claude_plugin_json(_listing()))
        assert payload == {
            "name": "narrativetrace-x",
            "description": "The plugin description.",
            "author": {"name": "NarrativeTrace"},
            "homepage": "https://narrativetrace.ai",
            "repository": "https://github.com/narrativetrace/narrativetrace-x",
            "license": "Apache-2.0",
            "keywords": ["tracing", "agent-skills"],
            "displayName": "NarrativeTrace for X",
            "supportUrl": "https://github.com/narrativetrace/narrativetrace-x/issues",
            "privacyPolicyUrl": "https://narrativetrace.ai/privacy",
            "documentationUrl": (
                "https://github.com/narrativetrace/narrativetrace-x/tree/main/documentation"
            ),
            "icon": "./.claude-plugin/icon.png",
        }

    def test_the_icon_path_is_relative_to_the_plugin_root(self) -> None:
        assert CLAUDE_PLUGIN_ICON_PATH == "./.claude-plugin/icon.png"

    def test_carries_no_version_key_so_a_release_leaves_the_folder_unchanged(self) -> None:
        assert '"version"' not in render_claude_plugin_json(_listing())

    def test_keywords_render_on_one_line_like_the_marketplace_file_style(self) -> None:
        assert '  "keywords": ["tracing", "agent-skills"],\n' in render_claude_plugin_json(
            _listing()
        )

    def test_renders_byte_identically_every_time(self) -> None:
        assert render_claude_plugin_json(_listing()) == render_claude_plugin_json(_listing())

    def test_escapes_every_character_json_cannot_carry_raw(self) -> None:
        hostile = _listing(plugin_description='A "quoted" \\ name\twith\na newline and a \x01.')
        payload = json.loads(render_claude_plugin_json(hostile))
        assert payload["description"] == 'A "quoted" \\ name\twith\na newline and a \x01.'
