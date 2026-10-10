# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The wiring lines every source-wired row carries, read from ``wiring-snippets.md`` inside this
library — the text the doctor's fix prints wherever it runs, with no repository in sight. The
resource's blocks are held to the fixtures by ``poe snippet-check``."""

from __future__ import annotations

import pytest

from narrativetrace_tooling.frameworks import wiring_snippets
from narrativetrace_tooling.frameworks.table import ROWS, Snippet
from narrativetrace_tooling.frameworks.wiring_snippets import Entry, entries, parse, text


class TestTheResource:
    def test_every_snippet_row_has_its_section_and_no_section_is_orphaned(self) -> None:
        snippet_rows = [r for r in ROWS if isinstance(r.wiring, Snippet)]
        assert list(entries()) == [r.id for r in snippet_rows]

    def test_every_section_names_its_rows_own_fixture_and_region(self) -> None:
        for r in ROWS:
            if isinstance(r.wiring, Snippet):
                entry = entries()[r.id]
                assert (entry.fixture, entry.region) == (r.wiring.fixture, r.wiring.region)

    def test_the_asgi_lines_add_the_middleware(self) -> None:
        assert "app.add_middleware(NarrativeTraceMiddleware" in text("asgi")

    def test_a_row_without_a_section_is_a_build_defect_named_as_such(self) -> None:
        with pytest.raises(
            LookupError, match=r"\Awiring-snippets\.md has no section for row flask\Z"
        ):
            text("flask")

    def test_the_resource_is_read_once(self) -> None:
        assert wiring_snippets.entries() is wiring_snippets.entries()


class TestParse:
    def test_reads_each_section_marker_and_block(self) -> None:
        markdown = (
            "# Title\n\nprose\n\n## asgi\n\n"
            "<!-- snippet: a/b.py region=wiring -->\n```python\nline 1\nline 2\n```\n"
            "<!-- /snippet -->\n"
        )
        assert parse(markdown) == {"asgi": Entry("a/b.py", "wiring", "line 1\nline 2\n")}

    def test_a_whole_file_marker_has_no_region(self) -> None:
        markdown = "## x\n<!-- snippet: a/b.py -->\n```python\nbody\n```\n<!-- /snippet -->\n"
        assert parse(markdown)["x"].region is None

    def test_a_heading_inside_a_fenced_block_is_body_not_a_section(self) -> None:
        markdown = (
            "## x\n<!-- snippet: a.md -->\n```markdown\n## not-a-section\n```\n<!-- /snippet -->\n"
        )
        assert list(parse(markdown)) == ["x"]
        assert parse(markdown)["x"].body == "## not-a-section\n"

    def test_an_unterminated_block_is_no_entry(self) -> None:
        assert parse("## x\n<!-- snippet: a.py -->\n```python\nbody\n") == {}

    def test_a_section_without_a_marker_is_no_entry(self) -> None:
        assert parse("## x\n\nprose only\n\n## y\n") == {}

    def test_a_fence_before_any_marker_ends_the_section_scan(self) -> None:
        markdown = "## x\n```python\nunmarked\n```\n<!-- snippet: a.py -->\n```\nb\n```\n"
        assert parse(markdown) == {}
