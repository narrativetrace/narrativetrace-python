# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The translation platform gate (`scripts/translation_check.py`, `poe translation-check`).

`main()`'s stdout/exit-code glue is exercised for real by `poe check` running the script against
this repository (and by `test_real_repository_has_no_failures` below); these tests drive each
`Support`-equivalent function in isolation against synthetic `tmp_path` trees.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.translation_check import (
    ENGLISH_INDEX,
    REPO_ROOT,
    I18nDocument,
    I18nLanguage,
    I18nManifest,
    broken_links,
    check_all_index,
    check_all_structure,
    check_completeness,
    check_english_index_menu,
    check_language_index,
    check_staleness,
    compare,
    document_targets,
    expected_menu,
    git_blob_hash,
    load_manifest_or_none,
    menu_line,
    parse_header,
    profile,
    review_summary_line,
    run_all,
    status_report,
    translated_files,
    unreviewed,
)

ES = I18nLanguage(
    "es", "Español", "documentation/es", "documentation/LEAME.md", "LEAME.md", "in-progress"
)
ZH = I18nLanguage(
    "zh-CN",
    "简体中文",
    "documentation/zh-CN",
    "documentation/自述文件.md",
    "自述文件.md",
    "in-progress",
)


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _header(source: str, blob: str, reviewed: str | None = None) -> str:
    tail = f" | reviewed: {reviewed}" if reviewed else ""
    return f"<!-- source: {source} blob {blob} | translated: 2026-09-03{tail} -->"


class TestParseHeader:
    def test_minimal_header(self) -> None:
        header = parse_header(
            "<!-- source: documentation/foo.md blob 1a2b3c4d5e6f | translated: 2026-09-03 -->"
        )
        assert header is not None
        assert header.source_path == "documentation/foo.md"
        assert header.blob_hash_prefix == "1a2b3c4d5e6f"
        assert header.reviewed is None

    def test_reviewed_date_is_captured(self) -> None:
        header = parse_header(_header("documentation/foo.md", "1a2b3c4d5e6f", "2026-09-04"))
        assert header is not None
        assert header.reviewed == "2026-09-04"

    def test_reviewed_dash_means_unreviewed(self) -> None:
        header = parse_header(_header("documentation/foo.md", "1a2b3c4d5e6f", "-"))
        assert header is not None
        assert header.reviewed is None

    def test_leading_and_trailing_whitespace_is_tolerated(self) -> None:
        raw = "  " + _header("documentation/foo.md", "1a2b3c4d5e6f") + "  \n"
        assert parse_header(raw) is not None

    @pytest.mark.parametrize(
        "line",
        [
            "",
            "# Not a header",
            "<!-- source: documentation/foo.md blob short | translated: 2026-09-03 -->",
            "<!-- source: documentation/foo.md blob 1a2b3c4d5e6f | translated: 09-03-2026 -->",
        ],
    )
    def test_malformed_lines_are_not_headers(self, line: str) -> None:
        assert parse_header(line) is None


class TestGitBlobHash:
    def test_empty_content_matches_the_well_known_git_empty_blob_hash(self) -> None:
        assert git_blob_hash(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"

    def test_different_content_hashes_differently(self) -> None:
        assert git_blob_hash(b"hello\n") != git_blob_hash(b"world\n")


class TestCheckStaleness:
    def test_in_sync_translation_reports_nothing(self, tmp_path: Path) -> None:
        source = _write(tmp_path, "documentation/foo.md", "# Foo\n\nBody.\n")
        blob = git_blob_hash(source.read_bytes())[:12]
        _write(
            tmp_path, "documentation/es/foo.md", _header("documentation/foo.md", blob) + "\n# Foo\n"
        )
        assert check_staleness(tmp_path) == []

    def test_stale_translation_is_reported(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/foo.md", "# Foo\n\nNew body.\n")
        _write(
            tmp_path,
            "documentation/es/foo.md",
            _header("documentation/foo.md", "000000000000") + "\n# Foo\n",
        )
        problems = check_staleness(tmp_path)
        assert len(problems) == 1
        assert "stale" in problems[0]

    def test_missing_source_is_reported(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "documentation/es/foo.md",
            _header("documentation/gone.md", "000000000000") + "\n",
        )
        problems = check_staleness(tmp_path)
        assert "source 'documentation/gone.md' is missing" in problems[0]

    def test_missing_header_is_reported(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/foo.md", "# Foo\n")
        _write(tmp_path, "documentation/es/foo.md", "# Foo (no header)\n")
        problems = check_staleness(tmp_path)
        assert "missing or malformed staleness header" in problems[0]

    def test_source_path_escaping_the_repo_root_is_reported(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "documentation/es/foo.md", _header("../../etc/passwd", "000000000000") + "\n"
        )
        problems = check_staleness(tmp_path)
        assert "escapes the repository root" in problems[0]

    def test_headered_root_file_outside_a_language_directory_is_discovered(
        self, tmp_path: Path
    ) -> None:
        source = _write(tmp_path, "README.md", "# Hi\n")
        blob = git_blob_hash(source.read_bytes())[:12]
        _write(tmp_path, "LEAME.md", _header("README.md", blob) + "\n# Hola\n")
        assert check_staleness(tmp_path) == []
        assert any(f.name == "LEAME.md" for f in translated_files(tmp_path))

    def test_i18n_directory_itself_is_never_treated_as_a_language(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/i18n/manifest.json", '{"languages": [], "documents": []}')
        assert translated_files(tmp_path) == []

    def test_build_and_dot_directories_are_never_walked(self, tmp_path: Path) -> None:
        _write(tmp_path, "build/stale.md", _header("nope.md", "000000000000") + "\n")
        _write(tmp_path, ".hidden/stale.md", _header("nope.md", "000000000000") + "\n")
        assert translated_files(tmp_path) == []

    def test_an_english_topical_subdirectory_is_never_mistaken_for_a_language_directory(
        self, tmp_path: Path
    ) -> None:
        # documentation/guides/ is English content living alongside where translations will land —
        # unlike the Java runtime, this runtime nests topical subdirectories under documentation/,
        # so "every non-i18n subdirectory is a language" would misclassify it and demand headers on
        # plain English guides. The manifest's declared directories disambiguate.
        _write(tmp_path, "documentation/guides/installation.md", "# Installation\n")
        manifest = {
            "sourceLanguage": "en",
            "languages": [
                {
                    "code": "es",
                    "displayName": "Español",
                    "directory": "documentation/es",
                    "index": "documentation/LEAME.md",
                    "rootReadme": "LEAME.md",
                    "status": "in-progress",
                }
            ],
            "documents": [],
        }
        _write(tmp_path, "documentation/i18n/manifest.json", json.dumps(manifest))
        assert translated_files(tmp_path) == []
        assert check_staleness(tmp_path) == []


class TestProfile:
    def test_headings_code_blocks_and_tables_are_captured(self) -> None:
        text = "\n".join(
            [
                "# Title",
                "## Sub",
                "```python",
                "x = 1",
                "```",
                "| A | B |",
                "|---|---|",
                "| 1 | 2 |",
            ]
        )
        result = profile(text)
        assert result.heading_levels == [1, 2]
        # The closing fence marker itself is never appended to the accumulated block — ported
        # verbatim from the Kotlin original, which joins `fence` before recording the marker line.
        # Harmless: both profiles being compared build blocks the same way, so comparisons stay
        # self-consistent even though the recorded text omits the closing "```".
        assert result.code_blocks == ["```python\nx = 1"]
        assert result.tables == [(1, 2)]

    def test_a_table_with_no_separator_row_is_not_a_table(self) -> None:
        result = profile("| just one row |\nnot a table\n")
        assert result.tables == []

    def test_lines_inside_a_fence_are_not_scanned_for_headings_or_tables(self) -> None:
        text = "```\n# not a heading\n| not | a table |\n|---|---|\n```\n"
        result = profile(text)
        assert result.heading_levels == []
        assert result.tables == []


class TestCompare:
    def test_identical_profiles_compare_clean(self) -> None:
        p = profile("# Title\n\nBody.\n")
        result = compare(p, p, "source.md", "es/source.md")
        assert result.failures == []
        assert result.warnings == []

    def test_heading_count_mismatch_is_a_failure(self) -> None:
        source = profile("# Title\n## Sub\n")
        translation = profile("# Title\n")
        result = compare(source, translation, "source.md", "es/source.md")
        assert any("heading count" in f for f in result.failures)

    def test_heading_level_mismatch_is_a_failure(self) -> None:
        source = profile("# Title\n## Sub\n")
        translation = profile("# Title\n### Sub\n")
        result = compare(source, translation, "source.md", "es/source.md")
        assert any("heading 2 is level 3" in f for f in result.failures)

    def test_code_block_count_mismatch_is_a_failure(self) -> None:
        source = profile("```\na\n```\n```\nb\n```\n")
        translation = profile("```\na\n```\n")
        result = compare(source, translation, "source.md", "es/source.md")
        assert any("code block count" in f for f in result.failures)

    def test_code_block_content_drift_is_only_a_warning(self) -> None:
        source = profile("```\n# English comment\n```\n")
        translation = profile("```\n# comentario en español\n```\n")
        result = compare(source, translation, "source.md", "es/source.md")
        assert result.failures == []
        assert any("code block 1 differs" in w for w in result.warnings)

    def test_table_shape_mismatch_is_a_failure(self) -> None:
        source = profile("| A | B |\n|---|---|\n| 1 | 2 |\n")
        translation = profile("| A |\n|---|\n| 1 |\n")
        result = compare(source, translation, "source.md", "es/source.md")
        assert any("table 1 shape mismatches" in f for f in result.failures)


class TestBrokenLinks:
    def test_resolving_relative_link_is_not_reported(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/other.md", "# Other\n")
        doc = _write(tmp_path, "documentation/guide.md", "See [Other](other.md).\n")
        assert broken_links(doc, tmp_path) == []

    def test_unresolvable_relative_link_is_reported(self, tmp_path: Path) -> None:
        doc = _write(tmp_path, "documentation/guide.md", "See [Missing](missing.md).\n")
        problems = broken_links(doc, tmp_path)
        assert "link target 'missing.md' does not resolve" in problems[0]

    def test_external_links_are_skipped(self, tmp_path: Path) -> None:
        doc = _write(tmp_path, "documentation/guide.md", "See [Ext](https://example.com/x).\n")
        assert broken_links(doc, tmp_path) == []

    def test_anchor_fragment_is_stripped_before_resolving(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/other.md", "# Other\n")
        doc = _write(tmp_path, "documentation/guide.md", "See [Other](other.md#section).\n")
        assert broken_links(doc, tmp_path) == []

    def test_links_inside_fenced_code_are_ignored(self, tmp_path: Path) -> None:
        doc = _write(tmp_path, "documentation/guide.md", "```\n[Missing](missing.md)\n```\n")
        assert broken_links(doc, tmp_path) == []


class TestCheckCompleteness:
    def _manifest(self, status: str) -> I18nManifest:
        language = I18nLanguage(
            "es", "Español", "documentation/es", "documentation/LEAME.md", "LEAME.md", status
        )
        document = I18nDocument("documentation/foo.md", {})
        return I18nManifest("en", [language], [document])

    def test_complete_language_missing_a_document_fails(self, tmp_path: Path) -> None:
        result = check_completeness(tmp_path, self._manifest("complete"))
        assert result.warnings == []
        assert any("missing translation of documentation/foo.md" in f for f in result.failures)

    def test_in_progress_language_missing_a_document_only_warns(self, tmp_path: Path) -> None:
        result = check_completeness(tmp_path, self._manifest("in-progress"))
        assert result.failures == []
        assert any("missing translation of documentation/foo.md" in w for w in result.warnings)

    def test_a_declared_translation_missing_from_disk_is_a_hard_failure_even_in_progress(
        self, tmp_path: Path
    ) -> None:
        language = I18nLanguage(
            "es", "Español", "documentation/es", "documentation/LEAME.md", "LEAME.md", "in-progress"
        )
        document = I18nDocument("documentation/foo.md", {"es": "foo-es.md"})
        result = check_completeness(tmp_path, I18nManifest("en", [language], [document]))
        assert any("does not exist" in f for f in result.failures)

    def test_a_document_that_exists_for_every_language_reports_nothing(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "documentation/es/foo-es.md", "# Foo\n")
        language = I18nLanguage(
            "es", "Español", "documentation/es", "documentation/LEAME.md", "LEAME.md", "complete"
        )
        document = I18nDocument("documentation/foo.md", {"es": "foo-es.md"})
        result = check_completeness(tmp_path, I18nManifest("en", [language], [document]))
        assert result.failures == []
        assert result.warnings == []


class TestIndexMenuIntegrity:
    def _manifest(self) -> I18nManifest:
        return I18nManifest("en", [ES, ZH], [I18nDocument("documentation/foo.md", {})])

    def test_menu_line_is_the_first_non_blank_line_after_h1(self) -> None:
        assert menu_line("# Title\n\nMenu line\n\nBody\n") == "Menu line"

    def test_menu_line_is_none_without_an_h1(self) -> None:
        assert menu_line("Just prose.\n") is None

    def test_expected_menu_lists_english_first_always_linked(self, tmp_path: Path) -> None:
        assert expected_menu(self._manifest(), tmp_path, None).startswith("[English](README.md) | ")

    def test_expected_menu_bolds_the_current_language_and_leaves_others_plain(
        self, tmp_path: Path
    ) -> None:
        menu = expected_menu(self._manifest(), tmp_path, "es")
        assert "**Español**" in menu
        assert "简体中文" in menu and "[简体中文]" not in menu

    def test_expected_menu_links_a_language_once_its_sibling_index_exists(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, ES.index, "# Index\n")
        menu = expected_menu(self._manifest(), tmp_path, None)
        assert "[Español](LEAME.md)" in menu

    def test_missing_english_index_fails(self, tmp_path: Path) -> None:
        problems = check_english_index_menu(tmp_path, self._manifest())
        assert f"{ENGLISH_INDEX}: missing" in problems

    def test_mismatched_english_menu_fails(self, tmp_path: Path) -> None:
        _write(tmp_path, ENGLISH_INDEX, "# Docs\n\nwrong menu\n")
        problems = check_english_index_menu(tmp_path, self._manifest())
        assert any("language menu is" in p for p in problems)

    def test_correct_english_menu_passes(self, tmp_path: Path) -> None:
        expected = expected_menu(self._manifest(), tmp_path, None)
        _write(tmp_path, ENGLISH_INDEX, f"# Docs\n\n{expected}\n")
        assert check_english_index_menu(tmp_path, self._manifest()) == []

    def test_missing_in_progress_language_index_is_not_a_problem(self, tmp_path: Path) -> None:
        assert check_language_index(tmp_path, self._manifest(), ES) == []

    def test_missing_complete_language_index_is_a_failure(self, tmp_path: Path) -> None:
        complete = I18nLanguage(
            "es", "Español", "documentation/es", "documentation/LEAME.md", "LEAME.md", "complete"
        )
        problems = check_language_index(tmp_path, I18nManifest("en", [complete], []), complete)
        assert any("declared complete but has no sibling index" in p for p in problems)

    def test_sibling_index_row_set_must_match_the_manifest_exactly(self, tmp_path: Path) -> None:
        manifest = I18nManifest(
            "en",
            [ES],
            [I18nDocument("documentation/foo.md", {"es": "foo-es.md"})],
        )
        expected = expected_menu(manifest, tmp_path, "es")
        _write(tmp_path, "documentation/es/foo-es.md", "# Foo\n")
        _write(
            tmp_path,
            ES.index,
            f"# Índice\n\n{expected}\n\n| Doc | Qué cubre |\n|---|---|\n"
            "| [Otro](otro.md) | huérfano |\n",
        )
        problems = check_language_index(tmp_path, manifest, ES)
        assert any("missing an index row for 'es/foo-es.md'" in p for p in problems)
        assert any("is not a manifest document" in p for p in problems)
        assert any("does not resolve" in p for p in problems)


class TestReview:
    def test_a_header_with_no_reviewed_clause_is_unreviewed(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "documentation/es/foo.md",
            _header("documentation/foo.md", "000000000000") + "\n",
        )
        assert unreviewed(tmp_path) == ["documentation/es/foo.md"]

    def test_a_reviewed_header_is_not_unreviewed(self, tmp_path: Path) -> None:
        header = _header("documentation/foo.md", "000000000000", "2026-09-04")
        _write(tmp_path, "documentation/es/foo.md", header + "\n")
        assert unreviewed(tmp_path) == []

    def test_summary_line_counts_unreviewed_documents(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "documentation/es/foo.md",
            _header("documentation/foo.md", "000000000000") + "\n",
        )
        assert review_summary_line(tmp_path).startswith(
            "translation-check: 1 translated document(s)"
        )

    def test_status_report_without_a_manifest_says_so(self, tmp_path: Path) -> None:
        assert "no manifest" in status_report(tmp_path, None)

    def test_status_report_counts_translated_documents_per_language(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/es/foo-es.md", "# Foo\n")
        manifest = I18nManifest(
            "en", [ES], [I18nDocument("documentation/foo.md", {"es": "foo-es.md"})]
        )
        report = status_report(tmp_path, manifest)
        assert "es (in-progress): 1/1 translated, 0 unreviewed" in report


class TestRunAll:
    def test_no_manifest_degrades_to_staleness_only_with_one_warning(self, tmp_path: Path) -> None:
        result = run_all(tmp_path)
        assert result.failures == []
        assert len(result.warnings) == 1
        assert "no manifest" in result.warnings[0]

    def test_a_malformed_manifest_status_raises(self, tmp_path: Path) -> None:
        manifest = {
            "sourceLanguage": "en",
            "languages": [
                {
                    "code": "es",
                    "displayName": "Español",
                    "directory": "documentation/es",
                    "index": "documentation/LEAME.md",
                    "rootReadme": "LEAME.md",
                    "status": "bogus",
                }
            ],
            "documents": [],
        }
        _write(tmp_path, "documentation/i18n/manifest.json", json.dumps(manifest))
        with pytest.raises(ValueError, match="unknown language status"):
            load_manifest_or_none(tmp_path)

    def test_a_fully_in_sync_manifest_produces_only_warnings(self, tmp_path: Path) -> None:
        manifest = {
            "sourceLanguage": "en",
            "languages": [
                {
                    "code": "es",
                    "displayName": "Español",
                    "directory": "documentation/es",
                    "index": "documentation/LEAME.md",
                    "rootReadme": "LEAME.md",
                    "status": "in-progress",
                }
            ],
            "documents": [{"source": "documentation/foo.md", "translations": {}}],
        }
        _write(tmp_path, "documentation/i18n/manifest.json", json.dumps(manifest))
        _write(tmp_path, "documentation/foo.md", "# Foo\n")
        expected = expected_menu(
            I18nManifest("en", [ES], [I18nDocument("documentation/foo.md", {})]), tmp_path, None
        )
        _write(tmp_path, ENGLISH_INDEX, f"# Docs\n\n{expected}\n")
        result = run_all(tmp_path)
        assert result.failures == []
        assert any("missing translation of documentation/foo.md" in w for w in result.warnings)


class TestRealRepository:
    def test_the_real_repository_has_no_failures(self) -> None:
        manifest = load_manifest_or_none(REPO_ROOT)
        assert manifest is not None
        result = run_all(REPO_ROOT)
        assert result.failures == []

    def test_the_real_repository_manifest_status_matches_translation_progress(self) -> None:
        manifest = load_manifest_or_none(REPO_ROOT)
        assert manifest is not None
        statuses = {language.code: language.status for language in manifest.languages}
        assert statuses == {"es": "complete", "pt-BR": "complete", "zh-CN": "complete"}

    def test_the_real_repository_completeness_warns_for_every_in_progress_language(self) -> None:
        manifest = load_manifest_or_none(REPO_ROOT)
        assert manifest is not None
        result = check_completeness(REPO_ROOT, manifest)
        assert result.failures == []
        in_progress = [
            language for language in manifest.languages if language.status == "in-progress"
        ]
        assert len(result.warnings) == len(in_progress)

    def test_document_targets_ignores_the_separator_row(self) -> None:
        text = "| Doc | What |\n|---|---|\n| [A](a.md) | x |\n"
        assert document_targets(text) == ["a.md"]

    def test_check_all_structure_and_check_all_index_run_clean(self) -> None:
        manifest = load_manifest_or_none(REPO_ROOT)
        assert manifest is not None
        assert check_all_structure(REPO_ROOT).failures == []
        assert check_all_index(REPO_ROOT, manifest) == []
