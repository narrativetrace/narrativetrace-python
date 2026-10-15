# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The platform table, rendered for readers (Phase 8, platform pointers): the table at the top of
``documentation/use-with-your-agent.md``. One source — the installer's own platform table — and
this is the drift test for the page.

Named after the Java port's ``PlatformTableDocsTest`` so the two lists diff."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts import snippet_check, snippet_sync
from scripts.platform_table_docs import PAGE, check, splice, sync, table
from scripts.translation_check import REPO_ROOT

from narrativetrace_tooling.platforms.table import ROWS

BEGIN = "<!-- platform-table:begin -->\n"
END = "<!-- platform-table:end -->"


class TestTheTable:
    def test_has_one_row_per_platform_in_table_order_under_one_header(self) -> None:
        rendered = table()

        assert rendered.startswith(
            "| Platform | How a stranger gets the skills | What the agent finds after `init` |"
            " Evidence | Verified |\n|---|---|---|---|---|\n"
        )
        last = -1
        for row in ROWS:
            at = rendered.index(f"| {row.name} |")
            assert at > last, row.id
            last = at
            for cell in (row.install_path, row.agent_finds, row.verified):
                assert cell in rendered
        assert len(rendered.splitlines()) == 2 + len(ROWS)

    def test_a_row_names_its_evidence_lane_or_says_it_is_a_manual_trial(self) -> None:
        rendered = table()

        assert "Tier B lane `cursor`" in rendered
        assert "Tier B lane `antigravity`" in rendered
        assert "manual trial" in rendered

    def test_no_cell_breaks_the_table_with_a_pipe_or_a_newline(self) -> None:
        for line in table().splitlines()[2:]:
            assert len(line.replace("\\|", "").split("|")) == 7, line


class TestSplicing:
    def test_splices_the_table_between_its_markers_and_nowhere_else(self) -> None:
        page = f"before\n{BEGIN}stale\n{END}\nafter\n"

        rendered = splice(page)

        assert rendered.startswith(f"before\n{BEGIN}| Platform |")
        assert rendered.endswith(f"{END}\nafter\n")
        assert "stale" not in rendered
        assert splice(rendered) == rendered

    def test_a_page_without_the_markers_is_refused_naming_the_block(self) -> None:
        with pytest.raises(ValueError, match="platform-table"):
            splice("no markers here")


class TestThePage:
    def test_the_committed_page_carries_a_fresh_render(self) -> None:
        assert check(REPO_ROOT) == []

    def test_check_names_a_drifted_page(self, tmp_path: Path) -> None:
        page = tmp_path / PAGE
        page.parent.mkdir(parents=True)
        page.write_text(f"{BEGIN}stale\n{END}\n", encoding="utf-8")

        assert [message.split(":")[0] for message in check(tmp_path)] == [PAGE]

    def test_sync_rewrites_a_drifted_page_once_and_then_has_nothing_to_do(
        self, tmp_path: Path
    ) -> None:
        page = tmp_path / PAGE
        page.parent.mkdir(parents=True)
        page.write_text(f"# T\n{BEGIN}stale\n{END}\nrest\n", encoding="utf-8")

        assert sync(tmp_path) == [PAGE]
        assert check(tmp_path) == []
        assert sync(tmp_path) == []
        assert page.read_text(encoding="utf-8").endswith(f"{END}\nrest\n")


class TestWiredIntoTheGateAndTheSync:
    """The platform table's drift is `poe snippet-check`'s, and `poe snippet-sync` is its writer."""

    def test_snippet_check_fails_while_the_page_has_drifted(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(snippet_check, "check_platform_table", lambda _root: ["page: drifted"])
        # Wiring only: the real repository check would read build artefacts the sixty-seconds
        # tests write later in the same run (absent in a fresh tree -- the staged snapshot).
        monkeypatch.setattr(snippet_check, "check_framework_table", lambda _root: [])
        monkeypatch.setattr(snippet_check, "check_all", lambda _root: [])

        assert snippet_check.main() == 1
        assert "page: drifted" in capsys.readouterr().out

    def test_snippet_sync_rewrites_the_page_and_says_so(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(snippet_sync, "sync_platform_table", lambda _root: [PAGE])
        monkeypatch.setattr(snippet_sync, "sync_framework_table", lambda _root: [])
        monkeypatch.setattr(snippet_sync, "sync_repository", lambda _root: [])
        monkeypatch.setattr(snippet_sync, "sync_version_literals", lambda _root, _v: [])

        assert snippet_sync.main() == 0
        assert f"{PAGE}: platform table re-rendered" in capsys.readouterr().out
