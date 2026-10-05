# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from narrativetrace_skills.pro_listing import ProListing
from narrativetrace_skills.render.agents_md import (
    AGENTS_MD_BEGIN,
    AGENTS_MD_END,
    extract_agents_md_section,
    render_agents_md_snippet,
    splice_agents_md_section,
)
from narrativetrace_skills.skill import Skill


def _skill(canonical_name: str, description: str) -> Skill:
    return Skill(
        canonical_name=canonical_name,
        skill_class="mechanical",
        description=description,
        fixture="examples/demo",
        steps=(),
        allowed_tools=("uv",),
    )


_LISTING = ProListing(
    canonical_name="narrativetrace-mcp",
    prompt="p",
    delivers="a stdio MCP server",
    needs="n",
    comes_from="c",
    status="planned",
    feature_guide_status_text="Planned (Pro, gated)",
)


class TestRenderAgentsMdSnippet:
    def test_includes_markers(self) -> None:
        rendered = render_agents_md_snippet((), ())
        assert rendered.startswith(AGENTS_MD_BEGIN)
        assert rendered.endswith(AGENTS_MD_END)

    def test_lists_every_skill_by_name_and_description(self) -> None:
        skills = (_skill("narrativetrace-doctor", "Diagnoses things."),)
        rendered = render_agents_md_snippet(skills, ())
        assert "- `narrativetrace-doctor` — Diagnoses things." in rendered

    def test_lists_a_pro_listing_with_its_status_and_delivers(self) -> None:
        rendered = render_agents_md_snippet((), (_LISTING,))
        assert "- `narrativetrace-mcp` (Pro, planned) — a stdio MCP server" in rendered

    def test_points_at_llms_txt(self) -> None:
        assert "See llms.txt for the full doc index." in render_agents_md_snippet((), ())


class TestSpliceAgentsMdSection:
    def test_appends_when_markers_are_absent(self) -> None:
        result = splice_agents_md_section("# My repo\n", "SECTION")
        assert result == "# My repo\n\nSECTION\n"

    def test_replaces_an_existing_section_in_place(self) -> None:
        content = f"before\n{AGENTS_MD_BEGIN}\nold\n{AGENTS_MD_END}\nafter\n"
        result = splice_agents_md_section(content, "NEW")
        assert result == "before\nNEW\nafter\n"

    def test_leaves_surrounding_content_untouched(self) -> None:
        content = f"## Orientation\n\n{AGENTS_MD_BEGIN}\nold\n{AGENTS_MD_END}\n\n## Next\n"
        result = splice_agents_md_section(content, "NEW")
        assert result.startswith("## Orientation\n\n")
        assert result.endswith("\n\n## Next\n")


class TestExtractAgentsMdSection:
    def test_returns_none_when_markers_are_absent(self) -> None:
        assert extract_agents_md_section("no markers here") is None

    def test_extracts_the_delimited_section_markers_included(self) -> None:
        content = f"before\n{AGENTS_MD_BEGIN}\nbody\n{AGENTS_MD_END}\nafter\n"
        section = extract_agents_md_section(content)
        assert section == f"{AGENTS_MD_BEGIN}\nbody\n{AGENTS_MD_END}"

    def test_round_trips_with_splice(self) -> None:
        rendered = render_agents_md_snippet((_skill("x", "does x"),), ())
        content = splice_agents_md_section("base\n", rendered)
        assert extract_agents_md_section(content) == rendered
