# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The platform table (Phase 8, platform pointers): one registry of the agent platforms
NarrativeTrace is used from, how a project proves it is on one, which pointer ``init`` writes for
it, how a stranger installs the skills and which evidence lane exercises it. Row ids are a
cross-port contract."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from narrativetrace_tooling.platforms.table import (
    MANUAL,
    ROWS,
    ManagedSection,
    NoPointer,
    PlatformRow,
    Rule,
    row,
)


def _row(
    row_id: str = "some-platform", markers: tuple[str, ...] = (".some",), **kw: str
) -> PlatformRow:
    fields = {
        "name": "Name",
        "install_path": "install",
        "agent_finds": "finds",
        "evidence_lane": MANUAL,
        "verified": "2026-10-10",
        **kw,
    }
    return PlatformRow(
        row_id,
        fields["name"],
        markers,
        NoPointer(),
        fields["install_path"],
        fields["agent_finds"],
        fields["evidence_lane"],
        fields["verified"],
    )


class TestTheRows:
    def test_the_five_platforms_in_their_published_order(self) -> None:
        assert [r.id for r in ROWS] == [
            "cursor",
            "replit",
            "antigravity",
            "github-copilot",
            "claude-code",
        ]

    def test_cursor_is_detected_by_its_directory_and_pointed_at_by_one_rule(self) -> None:
        cursor = row("cursor")
        assert cursor.marker_paths == (".cursor",)
        assert isinstance(cursor.pointer, Rule)
        assert cursor.pointer.path == ".cursor/rules/narrativetrace.mdc"
        assert ".agents/skills" in cursor.pointer.text
        assert "doctor" in cursor.pointer.text
        assert cursor.evidence_lane == "cursor"

    def test_replit_is_detected_by_either_file_and_carries_the_section_in_its_memory(self) -> None:
        replit = row("replit")
        assert replit.marker_paths == ("replit.md", ".replit")
        assert replit.pointer == ManagedSection("replit.md")
        assert "GitHub" in replit.install_path
        assert replit.evidence_lane == MANUAL

    def test_antigravity_and_copilot_need_no_pointer(self) -> None:
        """Antigravity's markers are its OWN project layout (``.agents/rules``,
        ``.agents/workflows``, legacy ``.agent/``), never ``.agents/skills``, which ``init`` itself
        writes. No registry install path: ``agy plugin install`` reads only a plugin's top-level
        ``skills/`` directory, which this repository does not ship."""
        antigravity = row("antigravity")
        assert antigravity.name == "Antigravity"
        assert antigravity.pointer == NoPointer()
        assert antigravity.marker_paths == (".agents/rules", ".agents/workflows", ".agent")
        assert antigravity.evidence_lane == "antigravity"
        assert "narrativetrace init" in antigravity.install_path
        assert "plugin install" not in antigravity.install_path
        assert all(path in antigravity.agent_finds for path in (".agents/skills", "AGENTS.md"))
        assert row("github-copilot").pointer == NoPointer()
        assert row("github-copilot").marker_paths == (".github/copilot-instructions.md",)

    def test_claude_code_is_the_native_platform_with_the_claude_lane(self) -> None:
        claude = row("claude-code")
        assert (claude.marker_paths, claude.pointer, claude.evidence_lane) == (
            (".claude",),
            NoPointer(),
            "claude",
        )

    def test_every_row_carries_the_date_its_facts_were_verified(self) -> None:
        assert {r.verified for r in ROWS} == {"2026-10-10"}

    def test_an_unknown_id_is_a_key_error_naming_it(self) -> None:
        with pytest.raises(KeyError) as raised:
            row("cursorx")
        assert raised.value.args == ("no platform row cursorx",)


class TestARowIsChecked:
    def test_a_well_formed_row_is_built(self) -> None:
        assert _row().id == "some-platform"

    @pytest.mark.parametrize("bad", ["Some_Platform", "", "-x", "x-"])
    def test_the_id_must_be_kebab_case(self, bad: str) -> None:
        with pytest.raises(ValueError, match="kebab-case"):
            _row(bad)

    def test_a_row_with_no_marker_path_could_never_be_detected(self) -> None:
        with pytest.raises(ValueError, match="no marker path"):
            _row(markers=())

    @pytest.mark.parametrize("bad", ["last week", "", "2026-1-1", "2026-10-10 "])
    def test_the_verification_date_must_be_a_date(self, bad: str) -> None:
        with pytest.raises(ValueError, match="yyyy-mm-dd"):
            _row(verified=bad)

    @pytest.mark.parametrize(
        ("column", "words"),
        [("name", "name"), ("install_path", "install path"), ("agent_finds", "agent-finds")],
    )
    def test_every_text_column_must_be_filled(self, column: str, words: str) -> None:
        changes: dict[str, Any] = {column: " "}
        with pytest.raises(ValueError, match=words):
            dataclasses.replace(_row(), **changes)

    def test_the_lane_is_a_lane_id_or_manual(self) -> None:
        with pytest.raises(ValueError, match="lane"):
            _row(evidence_lane="Not A Lane")

    @pytest.mark.parametrize("path", ["/etc/replit.md", "../replit.md", " ", "a/../../b"])
    def test_a_pointer_path_stays_inside_the_project(self, path: str) -> None:
        with pytest.raises(ValueError, match="project-relative"):
            ManagedSection(path)
        with pytest.raises(ValueError, match="project-relative"):
            Rule(path, "text")

    def test_a_rule_pointer_carries_text(self) -> None:
        with pytest.raises(ValueError, match="carries text"):
            Rule(".cursor/rules/x.mdc", " ")

    def test_no_pointer_points_at_no_file(self) -> None:
        assert NoPointer().path == ""
