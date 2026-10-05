# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from narrativetrace_skills.pro_listing import ProListing


class TestProListing:
    def test_carries_every_field(self) -> None:
        listing = ProListing(
            canonical_name="x",
            prompt="p",
            delivers="d",
            needs="n",
            comes_from="c",
            status="in development",
            feature_guide_status_text="In development (Pro)",
        )
        assert listing.canonical_name == "x"
        assert listing.status == "in development"
        assert listing.feature_guide_status_text == "In development (Pro)"
