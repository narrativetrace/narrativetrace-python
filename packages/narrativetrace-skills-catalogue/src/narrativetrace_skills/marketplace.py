# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""This runtime's registry identity: everything a Claude Code plugin-marketplace listing needs
that is not a skill page. One listing per runtime repository -- the marketplace and its single
plugin share ``name``, because a marketplace name is unique per user and two runtimes' plugins
carry the same skill names (same canonical names ship in every runtime with different content).

No version anywhere, deliberately: with a relative-path plugin source the installed version IS
the repository's commit, so a version literal here would drift on every release and say nothing
the commit does not (ladder ruling 7).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarketplaceOwner:
    """Who maintains the listing, and where a reader goes to learn about them."""

    name: str
    url: str


@dataclass(frozen=True, slots=True)
class MarketplaceListing:
    name: str
    """The marketplace identifier AND the plugin's -- what a user types after ``@`` when
    installing, and (with no ``plugin.json`` in the tree) the plugin's manifest name too."""
    owner: MarketplaceOwner
    description: str
    """The marketplace's own line, shown when browsing it."""
    plugin_description: str
    """The plugin entry's line, shown in the plugin list and its details."""
    plugin_source: str
    """The plugin's directory, relative to the marketplace root (the repository root, the
    directory holding ``.claude-plugin/``) -- the rendered Claude-flavour pages' own root, so
    the plugin carries the skills and nothing else of the repository."""
    license: str
    """SPDX identifier of the pages the plugin ships, which may differ from the repository
    root's own licence."""
    homepage: str
    keywords: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "keywords", tuple(self.keywords))
