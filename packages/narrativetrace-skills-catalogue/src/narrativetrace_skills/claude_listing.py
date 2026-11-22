# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The Anthropic plugin directory's own listing fields, beside the vendor-neutral
:class:`~narrativetrace_skills.marketplace.MarketplaceListing` every registry shares.

The directory titles a plugin from ``display_name`` (without it, the title is the kebab-case
name) and links its support, privacy and documentation entries from the three URLs; everything
else the manifest needs comes from :attr:`ClaudeListing.base`.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace_skills.marketplace import MarketplaceListing


@dataclass(frozen=True, slots=True)
class ClaudeListing:
    base: MarketplaceListing
    """The vendor-neutral listing this directory entry is drawn from."""
    display_name: str
    """The title shown in the directory."""
    support_url: str
    """Where a user reports a problem."""
    privacy_policy_url: str
    """The privacy policy."""
    documentation_url: str
    """Where the documentation lives."""
