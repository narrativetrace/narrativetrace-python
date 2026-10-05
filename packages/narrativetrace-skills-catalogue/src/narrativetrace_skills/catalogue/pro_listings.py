# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Sourced verbatim from ``documentation/feature-guide.md``'s Pro tier table (2026-09-13 snapshot).
Never "paid", never a price — a status plus what it does."""

from __future__ import annotations

from narrativetrace_skills.pro_listing import ProListing

PRO_LISTINGS: tuple[ProListing, ...] = (
    ProListing(
        canonical_name="narrativetrace-pro-aggregate",
        prompt="summarize hotspots and error rates across a captured trace stream",
        delivers=(
            "aggregated trees, hotspots, and method/error frequencies via the Pro "
            "EventAggregator, fed EventStore.events()"
        ),
        needs="a NarrativeTrace Pro license and the Pro aggregation distribution",
        comes_from=(
            "the Java Pro line (relocated from this repo's free core 2026-07-12, Phase 31a Stage 2)"
        ),
        status="shipped",
        feature_guide_status_text="Pro",
    ),
    ProListing(
        canonical_name="narrativetrace-mcp",
        prompt="let an agent ask for trace data as a tool call instead of reading a rendered file",
        delivers="a stdio MCP server, connecting Claude Code / Cursor directly to captured traces",
        needs="a NarrativeTrace Pro license and the MCP server package",
        comes_from="the Java Pro line (an Enterprise-plan phase, E5)",
        status="planned",
        feature_guide_status_text="Planned (Pro, gated)",
    ),
)
