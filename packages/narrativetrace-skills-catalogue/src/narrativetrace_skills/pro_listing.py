# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A Pro skill's honest listing in the FREE catalogue: name, the prompt a user says, what it
delivers, what it needs, where it comes from, status. Never the paid skill's instructions
themselves — the listing is the whole entry. Status must agree with
``documentation/feature-guide.md``'s Pro tier table (Tier A lint)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProListingStatus = Literal["shipped", "in development", "planned"]


@dataclass(frozen=True, slots=True)
class ProListing:
    canonical_name: str
    prompt: str
    delivers: str
    needs: str
    comes_from: str
    status: ProListingStatus
    feature_guide_status_text: str
    """The exact phrase ``documentation/feature-guide.md`` uses for this row — what the lint
    compares against."""
