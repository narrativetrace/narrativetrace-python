# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The docs-as-tests gate (`scripts/snippet_check.py` / `scripts/snippet_sync.py`).

`main()`'s stdout/exit-code glue is exercised for real by `poe check` running the check against
this repository (and by `TestRealRepository` below); these tests drive `parse_spans`,
`expected_content` and the repository-level `check_repository`/`sync_repository` functions in
isolation against synthetic `tmp_path` trees, the same split `test_translation_check.py` uses.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from examples.import_and_use import write_artifact as write_import_and_use_artifact
from examples.not_traced_fields import write_artifact as write_not_traced_fields_artifact
from examples.sixty_seconds.tutorial_artifacts import write_artifacts
from scripts.snippet_check import (
    _english_markdown_files,
    _strip_license_header,
    check_repository,
    expected_content,
    parse_spans,
    pending_sync,
    sync_repository,
)
from scripts.translation_check import REPO_ROOT

_SIMPLE_PAGE = """# Title

<!-- snippet: src/thing.py -->
```python
old content
```
<!-- /snippet -->
"""


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestParseSpans:
    def test_a_plain_block_carries_its_path_and_no_options(self) -> None:
        (span,) = parse_spans(_SIMPLE_PAGE)
        assert span.source_path == "src/thing.py"
        assert span.options == {}

    def test_content_lines_are_the_lines_between_the_fences(self) -> None:
        (span,) = parse_spans(_SIMPLE_PAGE)
        lines = _SIMPLE_PAGE.split("\n")
        assert lines[span.content_start : span.content_end] == ["old content"]

    def test_options_are_parsed_as_key_value_pairs(self) -> None:
        page = "<!-- snippet: a.py region=NAME mask=duration -->\n```\nx\n```\n<!-- /snippet -->\n"
        (span,) = parse_spans(page)
        assert span.options == {"region": "NAME", "mask": "duration"}

    def test_two_blocks_in_one_page_are_both_found_in_order(self) -> None:
        page = _SIMPLE_PAGE + "\n" + _SIMPLE_PAGE.replace("src/thing.py", "src/other.py")
        first, second = parse_spans(page)
        assert (first.source_path, second.source_path) == ("src/thing.py", "src/other.py")
        assert first.open_line < second.open_line

    def test_a_page_with_no_markers_yields_nothing(self) -> None:
        assert parse_spans("# Title\n\nNo snippets here.\n") == []

    def test_a_marker_not_followed_by_a_fence_raises(self) -> None:
        with pytest.raises(ValueError, match="not followed by a fence"):
            parse_spans("<!-- snippet: a.py -->\nnot a fence\n<!-- /snippet -->\n")

    def test_a_fence_that_never_closes_raises(self) -> None:
        with pytest.raises(ValueError, match="never closes"):
            parse_spans("<!-- snippet: a.py -->\n```\nunterminated\n")

    def test_a_missing_close_marker_raises(self) -> None:
        with pytest.raises(ValueError, match="no matching '/snippet'"):
            parse_spans("<!-- snippet: a.py -->\n```\nx\n```\nNot the close marker\n")


class TestExpectedContentWholeFile:
    def test_matches_the_source_file_with_its_trailing_newline_stripped(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "src/thing.py", "line one\nline two\n")
        (span,) = parse_spans(_SIMPLE_PAGE)
        assert expected_content(tmp_path, span) == "line one\nline two"


class TestExpectedContentRegion:
    def test_extracts_the_window_between_begin_and_end_markers(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "src/thing.py",
            "before\n# snippet:begin CORE\nkept line one\nkept line two\n"
            "# snippet:end CORE\nafter\n",
        )
        page = "<!-- snippet: src/thing.py region=CORE -->\n```\nx\n```\n<!-- /snippet -->\n"
        (span,) = parse_spans(page)
        assert expected_content(tmp_path, span) == "kept line one\nkept line two"

    def test_a_double_slash_begin_end_pair_also_works(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.ts", "// snippet:begin X\nkept\n// snippet:end X\n")
        page = "<!-- snippet: src/thing.ts region=X -->\n```\nx\n```\n<!-- /snippet -->\n"
        (span,) = parse_spans(page)
        assert expected_content(tmp_path, span) == "kept"

    def test_a_missing_begin_marker_raises(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.py", "nothing here\n")
        page = "<!-- snippet: src/thing.py region=CORE -->\n```\nx\n```\n<!-- /snippet -->\n"
        (span,) = parse_spans(page)
        with pytest.raises(ValueError, match="no 'snippet:begin CORE' marker"):
            expected_content(tmp_path, span)

    def test_a_missing_end_marker_raises(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.py", "# snippet:begin CORE\nkept\n")
        page = "<!-- snippet: src/thing.py region=CORE -->\n```\nx\n```\n<!-- /snippet -->\n"
        (span,) = parse_spans(page)
        with pytest.raises(ValueError, match="no matching 'snippet:end CORE'"):
            expected_content(tmp_path, span)


class TestExpectedContentDiff:
    def test_is_a_headerless_unified_diff_from_the_marker_path_to_the_diff_option(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "src/before.py", "a\nb\nc\n")
        _write(tmp_path, "src/after.py", "a\nB\nc\n")
        page = (
            "<!-- snippet: src/before.py diff=src/after.py -->\n"
            "```diff\nx\n```\n<!-- /snippet -->\n"
        )
        (span,) = parse_spans(page)
        assert expected_content(tmp_path, span) == " a\n-b\n+B\n c"


class TestLicenseHeaderStripping:
    """The (private) publish pipeline stamps every tracked source with a license header
    (`# SPDX-License-Identifier: ...` / `# Licensed under ...` lines, then a blank line) that
    never appears in the private tree and never appears in a page's fenced block -- a snippeted
    source must have it stripped before comparison, in the public snapshot's cold `poe check`."""

    _HEADER = (
        "# SPDX-License-Identifier: BUSL-1.1\n# Licensed under the Business Source License 1.1\n"
    )

    def test_expected_content_strips_a_stamped_header_before_the_blank_line(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "src/thing.py", self._HEADER + "\nreal content\n")
        (span,) = parse_spans(_SIMPLE_PAGE.replace("old content", "real content"))
        assert expected_content(tmp_path, span) == "real content"

    def test_check_repository_matches_a_headerless_page_against_a_headered_source(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "src/thing.py", self._HEADER + "\nreal content\n")
        _write(
            tmp_path,
            "documentation/page.md",
            _SIMPLE_PAGE.replace("old content", "real content"),
        )
        assert check_repository(tmp_path) == []

    def test_a_leading_comment_with_no_license_marker_is_left_alone(self, tmp_path: Path) -> None:
        """`main.py`'s own first line, `# main.py`, must survive: it is a `#` comment but names
        no SPDX identifier or license grant, so it is not this header."""
        _write(tmp_path, "src/thing.py", "# main.py\nreal content\n")
        (span,) = parse_spans(_SIMPLE_PAGE.replace("old content", "# main.py\nreal content"))
        assert expected_content(tmp_path, span) == "# main.py\nreal content"

    def test_a_file_with_no_header_at_all_is_unaffected(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.py", "real content\n")
        (span,) = parse_spans(_SIMPLE_PAGE.replace("old content", "real content"))
        assert expected_content(tmp_path, span) == "real content"

    def test_diff_content_strips_the_header_from_both_sides(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/before.py", self._HEADER + "\na\nb\nc\n")
        _write(tmp_path, "src/after.py", self._HEADER + "\na\nB\nc\n")
        page = (
            "<!-- snippet: src/before.py diff=src/after.py -->\n"
            "```diff\nx\n```\n<!-- /snippet -->\n"
        )
        (span,) = parse_spans(page)
        assert expected_content(tmp_path, span) == " a\n-b\n+B\n c"


class TestDurationMasking:
    def test_check_repository_ignores_a_real_duration_difference(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.txt", 'says "hi" — 8ms\n')
        _write(
            tmp_path,
            "documentation/page.md",
            "<!-- snippet: src/thing.txt mask=duration -->\n"
            "```text\n"
            'says "hi" — 3ms\n'
            "```\n"
            "<!-- /snippet -->\n",
        )
        assert check_repository(tmp_path) == []

    def test_check_repository_still_catches_a_real_drift_under_masking(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "src/thing.txt", 'says "bye" — 8ms\n')
        _write(
            tmp_path,
            "documentation/page.md",
            "<!-- snippet: src/thing.txt mask=duration -->\n"
            "```text\n"
            'says "hi" — 3ms\n'
            "```\n"
            "<!-- /snippet -->\n",
        )
        failures = check_repository(tmp_path)
        assert len(failures) == 1
        assert "documentation/page.md:1" in failures[0]
        assert "src/thing.txt" in failures[0]

    def test_sync_repository_leaves_a_duration_only_difference_untouched(
        self, tmp_path: Path
    ) -> None:
        """Wall-clock is never a test input (family standard): a fresh run of the source that
        differs only in its masked duration reading is not a pending sync, so `sync_repository`
        must not rewrite the page (and must not report a change) just because this run happened
        to measure 8ms where the page still shows 3ms."""
        _write(tmp_path, "src/thing.txt", 'says "hi" — 8ms\n')
        page_path = _write(
            tmp_path,
            "documentation/page.md",
            "<!-- snippet: src/thing.txt mask=duration -->\n"
            "```text\n"
            'says "hi" — 3ms\n'
            "```\n"
            "<!-- /snippet -->\n",
        )
        before = page_path.read_text(encoding="utf-8")
        assert sync_repository(tmp_path) == []
        assert page_path.read_text(encoding="utf-8") == before

    def test_sync_repository_still_rewrites_a_real_drift_under_masking(
        self, tmp_path: Path
    ) -> None:
        """A masked block still resyncs, and still picks up the real (unmasked) duration, when
        the drift is not just the timing -- only the timing digits themselves are tolerated."""
        _write(tmp_path, "src/thing.txt", 'says "bye" — 8ms\n')
        page_path = _write(
            tmp_path,
            "documentation/page.md",
            "<!-- snippet: src/thing.txt mask=duration -->\n"
            "```text\n"
            'says "hi" — 3ms\n'
            "```\n"
            "<!-- /snippet -->\n",
        )
        changes = sync_repository(tmp_path)
        assert len(changes) == 1
        assert 'says "bye" — 8ms' in page_path.read_text(encoding="utf-8")


class TestTraceNameMasking:
    """`mask=traceName` (2026-09-13 ruling, item 5): a trace/run phrase -- derived from a randomly
    generated id, so it would otherwise fail this gate on every regeneration -- is neutral for
    comparison wherever a renderer or MDC-style logging pattern carries one."""

    def test_check_ignores_a_console_header_phrase_difference(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.txt", "trace: rare relic tells (b4bd61b)\n\nplaceOrder(...)\n")
        _write(
            tmp_path,
            "documentation/page.md",
            "<!-- snippet: src/thing.txt mask=traceName -->\n"
            "```text\n"
            "trace: bold elk soars (a1b2c3d)\n\nplaceOrder(...)\n"
            "```\n"
            "<!-- /snippet -->\n",
        )
        assert check_repository(tmp_path) == []

    def test_check_ignores_the_prose_lead_in_and_the_markdown_title_phrase(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path,
            "src/thing.txt",
            "The trace rare relic tells: placeOrder(...)\n"
            "## Trace: rare relic tells — Order.place\n",
        )
        _write(
            tmp_path,
            "documentation/page.md",
            "<!-- snippet: src/thing.txt mask=traceName -->\n"
            "```text\n"
            "The trace bold elk soars: placeOrder(...)\n## Trace: bold elk soars — Order.place\n"
            "```\n"
            "<!-- /snippet -->\n",
        )
        assert check_repository(tmp_path) == []

    def test_check_ignores_a_bracketed_logging_pattern_phrase(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.txt", "[rare relic tells] [] → placeOrder(...)\n")
        _write(
            tmp_path,
            "documentation/page.md",
            "<!-- snippet: src/thing.txt mask=traceName -->\n"
            "```text\n"
            "[bold elk soars] [] → placeOrder(...)\n"
            "```\n"
            "<!-- /snippet -->\n",
        )
        assert check_repository(tmp_path) == []

    def test_check_still_fails_when_something_else_changed(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "src/thing.txt", "trace: rare relic tells (b4bd61b)\n\nplaceOrder(other)\n"
        )
        _write(
            tmp_path,
            "documentation/page.md",
            "<!-- snippet: src/thing.txt mask=traceName -->\n"
            "```text\n"
            "trace: bold elk soars (a1b2c3d)\n\nplaceOrder(...)\n"
            "```\n"
            "<!-- /snippet -->\n",
        )
        assert len(check_repository(tmp_path)) == 1

    def test_multiple_comma_separated_masks_apply_in_order(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "src/thing.txt", "trace: rare relic tells (b4bd61b)\n\nplaceOrder() — 17ms\n"
        )
        _write(
            tmp_path,
            "documentation/page.md",
            "<!-- snippet: src/thing.txt mask=duration,traceName -->\n"
            "```text\n"
            "trace: bold elk soars (a1b2c3d)\n\nplaceOrder() — 3ms\n"
            "```\n"
            "<!-- /snippet -->\n",
        )
        assert check_repository(tmp_path) == []


class TestCheckAndSyncRepository:
    def test_check_repository_reports_nothing_when_every_block_matches(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "src/thing.py", "old content\n")
        _write(tmp_path, "documentation/page.md", _SIMPLE_PAGE)
        assert check_repository(tmp_path) == []

    def test_check_repository_reports_a_drifted_block(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.py", "new content\n")
        _write(tmp_path, "documentation/page.md", _SIMPLE_PAGE)
        failures = check_repository(tmp_path)
        assert len(failures) == 1
        assert "documentation/page.md:3" in failures[0]
        assert "src/thing.py" in failures[0]

    def test_sync_repository_rewrites_the_page_to_match_the_source(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.py", "new content\n")
        page_path = _write(tmp_path, "documentation/page.md", _SIMPLE_PAGE)
        changes = sync_repository(tmp_path)
        assert len(changes) == 1
        assert page_path.read_text(encoding="utf-8") == _SIMPLE_PAGE.replace(
            "old content", "new content"
        )
        assert check_repository(tmp_path) == []

    def test_sync_repository_reports_nothing_when_already_in_sync(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.py", "old content\n")
        _write(tmp_path, "documentation/page.md", _SIMPLE_PAGE)
        assert sync_repository(tmp_path) == []

    def test_pending_sync_reports_the_same_drift_without_writing_the_page(
        self, tmp_path: Path
    ) -> None:
        """Asking "would a sync rewrite anything?" must never be answered by performing the
        sync. `TestRealRepository` asks it of this repository's own tracked pages, and inside a
        mutmut window the mutated renderer guarantees a drifted regenerated artifact -- the
        answer used to be WRITTEN into the real tree, replacing a `mask=traceName` page's trace
        phrase with a fresh random one (2026-09-17 nightly finding F2)."""
        _write(tmp_path, "src/thing.py", "new content\n")
        page_path = _write(tmp_path, "documentation/page.md", _SIMPLE_PAGE)
        pending = pending_sync(tmp_path)
        assert len(pending) == 1
        assert "documentation/page.md:3" in pending[0]
        assert page_path.read_text(encoding="utf-8") == _SIMPLE_PAGE
        assert pending == sync_repository(tmp_path)

    def test_pending_sync_reports_nothing_when_already_in_sync(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.py", "old content\n")
        _write(tmp_path, "documentation/page.md", _SIMPLE_PAGE)
        assert pending_sync(tmp_path) == []

    def test_sync_repository_never_touches_a_translated_mirror(self, tmp_path: Path) -> None:
        """A file carrying a `translation_check` staleness header is a translation, not a
        source — `_english_markdown_files` must exclude it even if it also carries (copied)
        snippet markers, matching rule 8's "do not add markers to mirrors"."""
        _write(tmp_path, "src/thing.py", "new content\n")
        header = (
            "<!-- source: documentation/page.md blob deadbeefcafe | translated: 2026-09-11 -->\n"
        )
        translated_page = _write(tmp_path, "documentation/es/pagina.md", header + _SIMPLE_PAGE)
        _write(
            tmp_path,
            "documentation/i18n/manifest.json",
            '{"languages": [{"code": "es", "displayName": "Espa\\u00f1ol", '
            '"directory": "documentation/es", "index": "documentation/es/README.md", '
            '"rootReadme": "README.es.md", "status": "complete"}], '
            '"documents": [{"source": "documentation/page.md", '
            '"translations": {"es": "pagina.md"}}]}',
        )
        assert sync_repository(tmp_path) == []
        assert translated_page.read_text(encoding="utf-8") == header + _SIMPLE_PAGE

    def test_a_claude_skill_page_is_checked_the_same_as_a_doc_page(self, tmp_path: Path) -> None:
        """`.claude/skills/*/SKILL.md` is rendered BUILD OUTPUT whose steps embed real source
        through this exact marker convention (never a hand-typed literal in the typed catalogue,
        `narrativetrace_skills.render.claude`) -- this gate must catch a drifted one the same way
        it catches a drifted guide page, belt-and-suspenders alongside `skills_render.py --check`'s
        own whole-file regeneration check."""
        _write(tmp_path, "src/thing.py", "new content\n")
        _write(tmp_path, ".claude/skills/add/SKILL.md", _SIMPLE_PAGE)
        failures = check_repository(tmp_path)
        assert len(failures) == 1
        assert ".claude/skills/add/SKILL.md:3" in failures[0]

    def test_sync_repository_fixes_a_drifted_claude_skill_page(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.py", "new content\n")
        page_path = _write(tmp_path, ".claude/skills/doctor/SKILL.md", _SIMPLE_PAGE)
        changes = sync_repository(tmp_path)
        assert len(changes) == 1
        assert page_path.read_text(encoding="utf-8") == _SIMPLE_PAGE.replace(
            "old content", "new content"
        )
        assert check_repository(tmp_path) == []

    def test_a_codex_skill_page_is_checked_the_same_as_a_doc_page(self, tmp_path: Path) -> None:
        """`.agents/skills/*/SKILL.md` -- Codex CLI's own discovery path -- is the identical body
        `narrativetrace_skills.render.codex` renders from the same catalogue, so it needs the same
        belt-and-suspenders coverage as `.claude/skills/*/SKILL.md` above."""
        _write(tmp_path, "src/thing.py", "new content\n")
        _write(tmp_path, ".agents/skills/add-narrative-tracing/SKILL.md", _SIMPLE_PAGE)
        failures = check_repository(tmp_path)
        assert len(failures) == 1
        assert ".agents/skills/add-narrative-tracing/SKILL.md:3" in failures[0]

    def test_sync_repository_fixes_a_drifted_codex_skill_page(self, tmp_path: Path) -> None:
        _write(tmp_path, "src/thing.py", "new content\n")
        page_path = _write(tmp_path, ".agents/skills/narrativetrace-doctor/SKILL.md", _SIMPLE_PAGE)
        changes = sync_repository(tmp_path)
        assert len(changes) == 1
        assert page_path.read_text(encoding="utf-8") == _SIMPLE_PAGE.replace(
            "old content", "new content"
        )
        assert check_repository(tmp_path) == []


class TestRealRepository:
    """Exercises the check/sync against this real repository's own documentation and source.

    Some snippet sources (``examples/sixty_seconds/build/*.txt``,
    ``examples/build/not_traced_fields.txt``, ``examples/build/import_and_use.txt``) are
    git-ignored, generated artifacts that only their own example's test module writes --
    regenerated here too rather than relying on that test having run first: pytest collects
    ``packages`` before ``examples`` (``testpaths`` in ``pyproject.toml``), and a pristine checkout
    has no pre-existing ``build/`` at all.
    """

    def _regenerate_build_artifacts(self) -> None:
        write_artifacts()
        write_not_traced_fields_artifact()
        write_import_and_use_artifact()

    def test_the_real_repository_has_no_drifted_snippets(self) -> None:
        self._regenerate_build_artifacts()
        assert check_repository(REPO_ROOT) == []

    def test_the_real_repository_has_no_pending_sync(self) -> None:
        """`pending_sync`, never `sync_repository`: this test also runs inside the mutmut
        sandbox, where the mutated renderer drifts the regenerated artifacts on purpose -- a
        writing answer rewrote the real, tracked pages with a mutant's output (2026-09-17
        nightly finding F2)."""
        self._regenerate_build_artifacts()
        assert pending_sync(REPO_ROOT) == []

    def test_asking_the_real_repository_leaves_every_tracked_page_byte_identical(self) -> None:
        """The guard the 2026-09-17 finding needed: whatever the two checks above answer, no
        English page on disk may change while they answer it."""
        before = {path: path.read_bytes() for path in _english_markdown_files(REPO_ROOT)}
        self._regenerate_build_artifacts()
        check_repository(REPO_ROOT)
        pending_sync(REPO_ROOT)
        assert {path: path.read_bytes() for path in _english_markdown_files(REPO_ROOT)} == before


def test_stamped_header_touching_the_tutorial_label_line_is_stripped_exactly() -> None:
    """The publish stamp is four `#` lines with no blank line after them, so the file's own
    `# main.py` label touches the header directly; only the header may go."""
    stamped = (
        "# SPDX-License-Identifier: BUSL-1.1\n"
        "# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four\n"
        "# years from publication; Change License: Apache-2.0\n"
        "# Copyright (c) 2026 Empower Agile\n"
        "# main.py\nfrom narrativetrace import trace_object\n"
    )
    assert _strip_license_header(stamped) == "# main.py\nfrom narrativetrace import trace_object\n"
