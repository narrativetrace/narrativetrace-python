# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/comment_hygiene.py`'s pure decision logic.

`main()`'s glue (reading the real allowlist, printing, exit code) is exercised for real by `poe
comment-hygiene` / `poe check` running the gate against this repository; these tests drive
`packages_source_files`, `find_history_comments`, and `lint` in isolation, plus the two patterns
directly.
"""

from __future__ import annotations

from pathlib import Path

from scripts.comment_hygiene import (
    HISTORY_PATTERN,
    PORT_FRAMING_PATTERN,
    CommentHygieneHit,
    find_history_comments,
    lint,
    packages_source_files,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestHistoryPattern:
    def test_matches_an_owner_ruling_citation_a_ruled_year_phrase_and_a_bare_audit_date(
        self,
    ) -> None:
        assert HISTORY_PATTERN.search("kept for redaction (owner ruling, 2026-09-11).")
        assert HISTORY_PATTERN.search("fixed the gap (ruled 2026-09-12).")
        assert HISTORY_PATTERN.search("recomputed here (2026-09-02).")

    def test_matches_shipped_release_wording(self) -> None:
        assert HISTORY_PATTERN.search(
            "disable buffering here, by design. *(since 0.1.3, unreleased)*"
        )

    def test_does_not_match_an_ordinary_sentence_a_version_alone_or_a_bare_iso_date(self) -> None:
        assert not HISTORY_PATTERN.search("Escapes control characters before rendering.")
        assert not HISTORY_PATTERN.search("Ported from Java's NationalIdShapes.")
        assert not HISTORY_PATTERN.search("Landed 2026-09-10 across every port.")


class TestPortFramingPattern:
    def test_matches_each_named_phrase(self) -> None:
        assert PORT_FRAMING_PATTERN.search("this is the golden source for the algorithm.")
        assert PORT_FRAMING_PATTERN.search("see the Java repo for the original.")
        assert PORT_FRAMING_PATTERN.search("see the Java runtime for the original.")
        assert PORT_FRAMING_PATTERN.search("see the Java implementation for the original.")
        assert PORT_FRAMING_PATTERN.search("mirrors Java's Escape.code().")
        assert PORT_FRAMING_PATTERN.search("an explicit null counts as missing, as in Java.")
        assert PORT_FRAMING_PATTERN.search("this behavior is replaced by the Java builder.")
        assert PORT_FRAMING_PATTERN.search("the Java builder mutates in place.")

    def test_family_wide_framing_is_not_flagged(self) -> None:
        assert not PORT_FRAMING_PATTERN.search("same as every NarrativeTrace runtime.")
        assert not PORT_FRAMING_PATTERN.search("Escapes control characters before rendering.")


class TestPackagesSourceFiles:
    def test_finds_every_py_file_under_each_packages_own_src_and_never_a_sibling_tests_dir(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path / "packages" / "core" / "src" / "a.py", "")
        _write(tmp_path / "packages" / "core" / "src" / "nested" / "b.py", "")
        _write(tmp_path / "packages" / "core" / "tests" / "test_a.py", "")
        _write(tmp_path / "packages" / "other" / "src" / "c.py", "")

        found = packages_source_files(tmp_path)

        assert found == sorted(
            [
                tmp_path / "packages" / "core" / "src" / "a.py",
                tmp_path / "packages" / "core" / "src" / "nested" / "b.py",
                tmp_path / "packages" / "other" / "src" / "c.py",
            ]
        )

    def test_returns_an_empty_list_when_there_is_no_packages_directory_at_all(
        self, tmp_path: Path
    ) -> None:
        assert packages_source_files(tmp_path) == []


class TestFindHistoryComments:
    def test_reports_the_repo_relative_file_1_indexed_line_reason_and_stripped_text(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "src" / "foo.py",
            "x = 1\n# fixed the leak (owner ruling, 2026-09-11).\ny = 2\n",
        )

        assert find_history_comments(tmp_path) == [
            CommentHygieneHit(
                file="packages/core/src/foo.py",
                line=2,
                text="# fixed the leak (owner ruling, 2026-09-11).",
                reason="history",
            )
        ]

    def test_reports_a_port_framing_hit_with_its_own_reason(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "src" / "bar.py",
            '"""mirrors Java\'s RenderWalk."""\n',
        )

        assert find_history_comments(tmp_path) == [
            CommentHygieneHit(
                file="packages/core/src/bar.py",
                line=1,
                text='"""mirrors Java\'s RenderWalk."""',
                reason="port-framing",
            )
        ]

    def test_finds_nothing_in_a_file_with_no_matching_comment(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "packages" / "core" / "src" / "clean.py",
            "# Redacts a value whose shape matches a known secret pattern.\nx = 1\n",
        )

        assert find_history_comments(tmp_path) == []


class TestLint:
    def test_reports_an_unlisted_hit_as_a_violation_and_never_flags_an_allowlisted_one(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path / "packages" / "core" / "src" / "leftover.py",
            "# (owner ruling, 2026-09-11)\n",
        )
        _write(
            tmp_path / "packages" / "pending" / "src" / "notyet.py",
            "# (owner ruling, 2026-09-11)\n",
        )

        result = lint(tmp_path, {"packages/pending/src/notyet.py": "wave pending"})

        assert result.violations == (
            CommentHygieneHit(
                file="packages/core/src/leftover.py",
                line=1,
                text="# (owner ruling, 2026-09-11)",
                reason="history",
            ),
        )
        assert result.stale_allowlist_entries == ()

    def test_flags_an_allowlist_entry_whose_file_no_longer_has_any_hit_as_stale(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path / "packages" / "core" / "src" / "clean.py", "x = 1\n")

        result = lint(tmp_path, {"packages/core/src/clean.py": "no longer needed"})

        assert result.violations == ()
        assert result.stale_allowlist_entries == ("packages/core/src/clean.py",)

    def test_is_clean_when_nothing_matches_and_nothing_is_allowlisted(self, tmp_path: Path) -> None:
        _write(tmp_path / "packages" / "core" / "src" / "clean.py", "x = 1\n")

        result = lint(tmp_path, {})

        assert result.violations == ()
        assert result.stale_allowlist_entries == ()
