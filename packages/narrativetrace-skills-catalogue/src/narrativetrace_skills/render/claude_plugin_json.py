# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders ``.claude/.claude-plugin/plugin.json``: the manifest of the plugin the root marketplace
file lists, kept INSIDE the plugin folder where Claude Code and Anthropic's plugin directory read
it. Without a manifest the plugin is named after its folder, ``.claude``, a reserved name the
directory refuses.

Keys are the ones the manifest reference documents (``name``, ``description``, ``author``,
``homepage``, ``repository``, ``license``, ``keywords``) plus the directory listing fields the
vendor reads from the manifest only (``displayName``, ``supportUrl``, ``privacyPolicyUrl``,
``documentationUrl``, ``icon``). Every shared value comes from the same
:class:`~narrativetrace_skills.marketplace.MarketplaceListing` that
:func:`~narrativetrace_skills.render.marketplace.render_marketplace_json` renders, so the manifest
and the marketplace entry cannot disagree about the plugin (the entry's ``strict`` defaults to
true, so both are read and the manifest's metadata is the plugin's own).

No ``version`` key, deliberately: a relative-path plugin's version is the commit, and a version
literal here would make every release rewrite a folder whose skills did not change. Committed
BUILD OUTPUT, pinned by ``scripts/skills_render.py --check``. Built line by line, like the
marketplace file, so a flat ``keywords`` list renders on ONE line.
"""

from __future__ import annotations

import json

from narrativetrace_skills.claude_listing import ClaudeListing

CLAUDE_PLUGIN_ICON_PATH = "./.claude-plugin/icon.png"
"""Where the manifest finds its icon, relative to the plugin root (the ``.claude/`` folder)."""


def render_claude_plugin_json(directory: ClaudeListing) -> str:
    listing = directory.base
    keywords = ", ".join(json.dumps(keyword) for keyword in listing.keywords)
    lines = [
        "{",
        f'  "name": {_quote(listing.name)},',
        f'  "description": {_quote(listing.plugin_description)},',
        '  "author": {',
        f'    "name": {_quote(listing.owner.name)}',
        "  },",
        f'  "homepage": {_quote(listing.homepage)},',
        f'  "repository": {_quote(listing.repository)},',
        f'  "license": {_quote(listing.license)},',
        f'  "keywords": [{keywords}],',
        f'  "displayName": {_quote(directory.display_name)},',
        f'  "supportUrl": {_quote(directory.support_url)},',
        f'  "privacyPolicyUrl": {_quote(directory.privacy_policy_url)},',
        f'  "documentationUrl": {_quote(directory.documentation_url)},',
        f'  "icon": {_quote(CLAUDE_PLUGIN_ICON_PATH)}',
        "}",
    ]
    return "\n".join(lines) + "\n"


def _quote(text: str) -> str:
    return json.dumps(text)
