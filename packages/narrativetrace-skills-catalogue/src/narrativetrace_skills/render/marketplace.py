# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders ``.claude-plugin/marketplace.json``: the file that makes this repository a Claude
Code plugin marketplace carrying one plugin -- the rendered Claude-flavour skill pages, rooted
at the ``.claude/`` directory they already sit in.

Committed BUILD OUTPUT, like every other render target: the typed
:class:`~narrativetrace_skills.marketplace.MarketplaceListing` is the only place this text is
written, and ``scripts/skills_render.py``'s drift check is what the committed file is pinned
against.
"""

from __future__ import annotations

import json

from narrativetrace_skills.marketplace import MarketplaceListing


def render_marketplace_json(listing: MarketplaceListing) -> str:
    payload = {
        "name": listing.name,
        "owner": {"name": listing.owner.name, "url": listing.owner.url},
        "description": listing.description,
        "plugins": [
            {
                "name": listing.name,
                "source": listing.plugin_source,
                "description": listing.plugin_description,
                "license": listing.license,
                "homepage": listing.homepage,
                "keywords": list(listing.keywords),
            }
        ],
    }
    return f"{json.dumps(payload, indent=2)}\n"
