# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The framework table, rendered for readers (Phase 6 D2): ``llms-full.md``'s framework table with
every source-wired row's snippet, and ``llms.txt``'s covered-frameworks line. One source — the
doctor's own table — three surfaces; this is the drift test for the two documents."""

from __future__ import annotations

import pytest
from scripts.framework_table_docs import (
    LLMS_FULL,
    LLMS_TXT,
    check,
    covered_frameworks_line,
    framework_table_section,
    splice,
    sync,
)
from scripts.translation_check import REPO_ROOT
from scripts.version_literals import read_version

from narrativetrace_tooling.frameworks.table import ROWS, NoCheck, Snippet, WiringCheck
from narrativetrace_tooling.frameworks.wiring_snippets import text


class TestTheSection:
    def test_one_table_row_per_framework_row_in_order(self) -> None:
        section = framework_table_section("9.9.9")
        rows = [
            line for line in section.splitlines() if line.startswith("| ") and "---" not in line
        ]
        assert [line.split(" | ")[0].removeprefix("| ") for line in rows] == [
            "Framework",
            *(row.name for row in ROWS),
        ]

    def test_the_asgi_row_reads_marker_add_wiring_and_check(self) -> None:
        assert (
            "| FastAPI / Starlette (ASGI) | a fastapi or starlette dependency | "
            '`uv add "narrativetrace-asgi==9.9.9"` | NarrativeTraceMiddleware on the ASGI app, '
            "with an exporter | `config.asgi-middleware` |"
        ) in framework_table_section("9.9.9").splitlines()

    def test_a_row_no_check_watches_says_why(self) -> None:
        line = next(
            line
            for line in framework_table_section("9.9.9").splitlines()
            if "stdlib logging" in line
        )
        reason = next(r.check.reason for r in ROWS if isinstance(r.check, NoCheck))
        assert line.endswith(f"| none — {reason} |")

    def test_a_framework_with_no_integration_shipped_adds_nothing_and_says_so(self) -> None:
        line = next(
            line for line in framework_table_section("9.9.9").splitlines() if "| Flask" in line
        )
        assert line == (
            "| Flask | a flask dependency | — | no integration shipped — trace its services with "
            "trace_object | `config.flask-integration` (reports it) |"
        )

    def test_every_snippet_row_carries_its_lines_inside_snippet_markers(self) -> None:
        section = framework_table_section("9.9.9")
        for row in ROWS:
            if isinstance(row.wiring, Snippet):
                block = (
                    f"#### {row.name} — wiring\n\n"
                    f"<!-- snippet: {row.wiring.fixture} region={row.wiring.region} -->\n"
                    f"```python\n{text(row.id)}```\n<!-- /snippet -->\n"
                )
                assert block in section, row.id


class TestTheCoveredLine:
    def test_names_every_row_and_how_the_doctor_watches_it(self) -> None:
        assert covered_frameworks_line() == (
            "Covered frameworks (each row of the doctor's framework table): pytest "
            "(`config.pytest-fixture`); FastAPI / Starlette (ASGI) (`config.asgi-middleware`); "
            "OpenTelemetry (`config.otel-listener`); structlog (`config.structlog-processor`); "
            "stdlib logging (runtime-only); Flask (no integration shipped); Django (no "
            "integration shipped)."
        )

    def test_every_wiring_check_is_named(self) -> None:
        line = covered_frameworks_line()
        for row in ROWS:
            if isinstance(row.check, WiringCheck) and isinstance(row.wiring, Snippet):
                assert f"`{row.check.id}`" in line


class TestSplice:
    def test_replaces_only_what_sits_between_the_markers(self) -> None:
        document = "a\n<!-- x:begin -->\nold\n<!-- x:end -->\nb\n"
        assert splice(document, "x", "new\n") == "a\n<!-- x:begin -->\nnew\n<!-- x:end -->\nb\n"

    @pytest.mark.parametrize(
        "document", ["no markers\n", "<!-- x:end -->\n<!-- x:begin -->\n", "<!-- x:begin -->\n"]
    )
    def test_a_document_without_an_ordered_marker_pair_is_an_authoring_error(
        self, document: str
    ) -> None:
        with pytest.raises(
            ValueError, match=r"\Athe document has no x:begin / x:end marker pair\Z"
        ):
            splice(document, "x", "new\n")


class TestTheRepository:
    def test_both_documents_are_rendered_from_the_table_now(self) -> None:
        assert check(REPO_ROOT) == []

    def test_a_drifted_document_is_named_and_sync_repairs_it(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        for relative in (LLMS_FULL, LLMS_TXT):
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            original = (REPO_ROOT / relative).read_text(encoding="utf-8")
            target.write_text(original.replace("config.asgi-middleware", "config.stale"), "utf-8")
        (tmp_path / "pyproject.toml").write_text(
            f'[project]\nversion = "{read_version(REPO_ROOT)}"\n', encoding="utf-8"
        )

        assert check(tmp_path) == [
            f"{LLMS_FULL}: the framework table has drifted from the doctor's — run "
            "'poe snippet-sync'",
            f"{LLMS_TXT}: the framework table has drifted from the doctor's — run "
            "'poe snippet-sync'",
        ]
        assert sync(tmp_path) == [LLMS_FULL, LLMS_TXT]
        assert check(tmp_path) == []
