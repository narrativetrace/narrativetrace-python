# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The OpenAI plugin directory's own listing fields, beside the vendor-neutral
:class:`~narrativetrace_skills.marketplace.MarketplaceListing` every registry shares.

``display_name`` and ``short_description`` carry the directory's own 30-character ceiling;
everything else the directory's manifest needs -- ``name``, ``description``, ``author.name``,
``homepage``, ``license``, ``keywords`` -- comes from :attr:`OpenAiListing.base`, so this type
never repeats a fact the vendor-neutral listing already states.

There is no privacy-policy or terms-of-service field: both URLs are optional for a skills-only
submission, narrativetrace.ai carries neither page yet, and a field the renderer would never read
is dead weight. Add both back together with the rendering they would drive once the two pages
exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace_skills.marketplace import MarketplaceListing

MAX_LISTING_FIELD_LENGTH = 30
"""The directory's own ceiling on ``display_name`` and ``short_description``."""


@dataclass(frozen=True, slots=True)
class OpenAiListing:
    base: MarketplaceListing
    """The vendor-neutral listing this directory entry is drawn from."""
    display_name: str
    """Shown in the directory, at most :data:`MAX_LISTING_FIELD_LENGTH` characters."""
    short_description: str
    """The one-line pitch, at most :data:`MAX_LISTING_FIELD_LENGTH` characters."""
    category: str
    """The directory's own grouping for the listing (allowed values unverified)."""
    capabilities: tuple[str, ...]
    """What the plugin declares it can do (allowed values unverified)."""
    default_prompts: tuple[str, ...]
    """Example prompts shown to a user before they have typed anything."""
    brand_color: str
    """The listing's accent colour, a hex string."""
    website_url: str
    """Where a reader goes to learn more."""

    def __post_init__(self) -> None:
        _require_at_most(self.display_name, "display_name")
        _require_at_most(self.short_description, "short_description")
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "default_prompts", tuple(self.default_prompts))


def _require_at_most(value: str, field: str) -> None:
    if len(value) > MAX_LISTING_FIELD_LENGTH:
        raise ValueError(
            f"{field} must be at most {MAX_LISTING_FIELD_LENGTH} characters, was {len(value)}"
        )
