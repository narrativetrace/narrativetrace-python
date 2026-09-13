# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The always-on ``AGENTS.md`` snippet: a compressed catalogue index plus the ``llms.txt``
pointer, so an agent that never thinks to look for a skill still sees one line naming it.
Delimited so an installer (or this repo's own render step) can replace the section without
touching anything else in the file.
"""

from __future__ import annotations

from narrativetrace_skills.pro_listing import ProListing
from narrativetrace_skills.skill import Skill

AGENTS_MD_BEGIN = "<!-- narrativetrace:skills:start -->"
AGENTS_MD_END = "<!-- narrativetrace:skills:end -->"


def render_agents_md_snippet(skills: tuple[Skill, ...], listings: tuple[ProListing, ...]) -> str:
    lines = [AGENTS_MD_BEGIN, "## NarrativeTrace agent skills", ""]
    for skill in skills:
        lines.append(f"- `{skill.canonical_name}` — {skill.description}")
    for listing in listings:
        lines.append(f"- `{listing.canonical_name}` (Pro, {listing.status}) — {listing.delivers}")
    lines.extend(["", "See llms.txt for the full doc index.", AGENTS_MD_END])
    return "\n".join(lines)


def splice_agents_md_section(content: str, section: str) -> str:
    """Replaces the delimited section in ``content``, or appends it if the markers are not
    present yet."""
    begin = content.find(AGENTS_MD_BEGIN)
    end = content.find(AGENTS_MD_END)
    if begin == -1 or end == -1:
        return f"{content.rstrip()}\n\n{section}\n"
    return content[:begin] + section + content[end + len(AGENTS_MD_END) :]


def extract_agents_md_section(content: str) -> str | None:
    """The delimited section of ``content``, markers included, or ``None`` when either marker is
    missing. The read-side inverse of :func:`splice_agents_md_section`'s write."""
    begin = content.find(AGENTS_MD_BEGIN)
    end = content.find(AGENTS_MD_END)
    if begin == -1 or end == -1:
        return None
    return content[begin : end + len(AGENTS_MD_END)]
