# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders the Cursor plugin manifest pair — ``.cursor-plugin/plugin.json`` and
``.cursor-plugin/marketplace.json`` — from the SAME
:class:`~narrativetrace_skills.marketplace.MarketplaceListing` that renders
``.claude-plugin/marketplace.json``.

INTENT: one catalogue, one listing, two vendors' files. The plugin is the repository root and
carries the skills as the open-standard ``.agents/skills`` directory Cursor reads natively plus
the one rule file that points at them — no commands, hooks, agents or MCP servers (Phase 8,
platform pointers). Committed BUILD OUTPUT like every render target;
``scripts/skills_render.py``'s drift check pins both files against a fresh render.

**@llmNote** Field names follow Cursor's plugin reference (verified 2026-10-10): ``name`` is
required, ``author`` takes ``name``/``email`` only, a ``skills`` or ``rules`` path replaces folder
discovery, and a marketplace entry's ``source`` is the plugin directory relative to the repository
root — ``.`` for a repository that is itself the one plugin. No ``version`` key, for the reason
:class:`~narrativetrace_skills.marketplace.MarketplaceListing` states.
"""

from __future__ import annotations

import json
from typing import Final

from narrativetrace_skills.marketplace import MarketplaceListing

SKILLS_PATH: Final = "./.agents/skills/"
"""The skills directory the plugin points at: the open-standard flavour Cursor reads natively."""

RULE_PATH: Final = "./.cursor/rules/narrativetrace.mdc"
"""The one rule the plugin carries, the same file ``init`` writes into a Cursor project."""


def render_cursor_plugin_json(listing: MarketplaceListing) -> str:
    """``.cursor-plugin/plugin.json``."""
    payload = {
        "name": listing.name,
        "description": listing.plugin_description,
        "author": {"name": listing.owner.name},
        "license": listing.license,
        "homepage": listing.homepage,
        "keywords": list(listing.keywords),
        "skills": SKILLS_PATH,
        "rules": RULE_PATH,
    }
    return f"{json.dumps(payload, indent=2)}\n"


def render_cursor_marketplace_json(listing: MarketplaceListing) -> str:
    """``.cursor-plugin/marketplace.json``: this repository as a marketplace of one plugin, the
    repository root itself."""
    payload = {
        "name": listing.name,
        "owner": {"name": listing.owner.name},
        "metadata": {"description": listing.description},
        "plugins": [
            {
                "name": listing.name,
                "source": ".",
                "description": listing.plugin_description,
                "license": listing.license,
                "homepage": listing.homepage,
                "keywords": list(listing.keywords),
            }
        ],
    }
    return f"{json.dumps(payload, indent=2)}\n"
