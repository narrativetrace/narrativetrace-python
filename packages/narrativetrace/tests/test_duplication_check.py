# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The duplication ratchet's pure decision logic (`scripts/duplication_check.py`).

`main()`'s glue (running the report, then deciding) is exercised for real by `poe
duplication-check` / `poe check` running the gate against this repository; these tests drive
`read_baseline`, `read_exemptions`, `matches_glob`, `is_exempt` and `decide` in isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.duplication_check import (
    DuplicationBaseline,
    DuplicationExemption,
    decide,
    is_exempt,
    matches_glob,
    read_baseline,
    read_exemptions,
)
from scripts.duplication_report import (
    DuplicationCluster,
    DuplicationOccurrence,
    DuplicationTreeResult,
)


def _occurrence(file: str, start: int = 1) -> DuplicationOccurrence:
    return DuplicationOccurrence(file=file, start_line=start, end_line=start + 4)


def _cluster(tokens: int, *files: str) -> DuplicationCluster:
    return DuplicationCluster(
        tokens=tokens, lines=5, occurrences=tuple(_occurrence(f) for f in files)
    )


def _tree(percent: float, clusters: tuple[DuplicationCluster, ...] = ()) -> DuplicationTreeResult:
    return DuplicationTreeResult(
        lines_total=1000, lines_duplicated=int(percent * 10), percent=percent, clusters=clusters
    )


class TestReadBaseline:
    def test_reads_the_required_and_optional_keys(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.properties"
        path.write_text(
            "# a comment\n"
            "recorded=2026-09-12\n"
            "commit=first-scan\n"
            "main.percent=21.5\n"
            "main.largestCluster=521\n",
            encoding="utf-8",
        )

        baseline = read_baseline(path)

        assert baseline == DuplicationBaseline(
            main_percent=21.5, main_largest_cluster=521, recorded="2026-09-12", commit="first-scan"
        )

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match=r"no duplication baseline"):
            read_baseline(tmp_path / "does-not-exist.properties")

    def test_missing_required_key_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.properties"
        path.write_text("main.percent=21.5\n", encoding="utf-8")

        with pytest.raises(ValueError, match=r"missing 'main\.largestCluster'"):
            read_baseline(path)

    def test_recorded_and_commit_are_optional(self, tmp_path: Path) -> None:
        path = tmp_path / "baseline.properties"
        path.write_text("main.percent=1.0\nmain.largestCluster=10\n", encoding="utf-8")

        baseline = read_baseline(path)

        assert baseline.recorded == ""
        assert baseline.commit == ""


class TestReadExemptions:
    def test_empty_when_file_absent(self, tmp_path: Path) -> None:
        assert read_exemptions(tmp_path / "missing.txt") == []

    def test_parses_a_reasoned_pair(self, tmp_path: Path) -> None:
        path = tmp_path / "exemptions.txt"
        path.write_text(
            "# Data tables, not logic.\n"
            "# Second line of the same reason.\n"
            "packages/a/src/*_data.py :: packages/a/src/*_data.py\n",
            encoding="utf-8",
        )

        exemptions = read_exemptions(path)

        assert exemptions == [
            DuplicationExemption(
                glob_a="packages/a/src/*_data.py",
                glob_b="packages/a/src/*_data.py",
                reason="Data tables, not logic. Second line of the same reason.",
            )
        ]

    def test_multiple_entries_separated_by_blank_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "exemptions.txt"
        path.write_text(
            "# first reason\na/x.py :: a/y.py\n\n# second reason\nb/x.py :: b/y.py\n",
            encoding="utf-8",
        )

        exemptions = read_exemptions(path)

        assert len(exemptions) == 2
        assert exemptions[0].reason == "first reason"
        assert exemptions[1].reason == "second reason"

    def test_pair_without_a_reason_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "exemptions.txt"
        path.write_text("a/x.py :: a/y.py\n", encoding="utf-8")

        with pytest.raises(ValueError, match=r"no '# reason' line above it"):
            read_exemptions(path)

    def test_malformed_pair_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "exemptions.txt"
        path.write_text("# reason\nnot-a-pair-line\n", encoding="utf-8")

        with pytest.raises(ValueError, match=r"expected 'globA :: globB'"):
            read_exemptions(path)

    def test_pair_with_an_empty_side_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "exemptions.txt"
        path.write_text("# reason\na/x.py :: \n", encoding="utf-8")

        with pytest.raises(ValueError, match=r"expected 'globA :: globB'"):
            read_exemptions(path)

    def test_a_blank_line_resets_a_dangling_reason(self, tmp_path: Path) -> None:
        path = tmp_path / "exemptions.txt"
        path.write_text("# orphaned reason\n\na/x.py :: a/y.py\n", encoding="utf-8")

        with pytest.raises(ValueError, match=r"no '# reason' line above it"):
            read_exemptions(path)


class TestMatchesGlob:
    def test_literal_path_matches_itself(self) -> None:
        assert matches_glob("a/b/c.py", "a/b/c.py") is True

    def test_single_star_matches_within_one_segment(self) -> None:
        assert (
            matches_glob("packages/clarity/src/*_data.py", "packages/clarity/src/verbs_data.py")
            is True
        )

    def test_single_star_does_not_cross_a_path_separator(self) -> None:
        assert matches_glob("packages/*/x.py", "packages/a/b/x.py") is False

    def test_double_star_crosses_path_separators(self) -> None:
        assert matches_glob("packages/**/x.py", "packages/a/b/x.py") is True

    def test_no_partial_match_on_a_longer_sibling_path(self) -> None:
        # A prefix match must not count: "a/b.py" is not "a/bc.py", and a glob for one file must
        # never accidentally cover a same-prefixed sibling.
        assert matches_glob("a/b.py", "a/bc.py") is False

    def test_question_mark_matches_exactly_one_character(self) -> None:
        assert matches_glob("a/b?.py", "a/bx.py") is True
        assert matches_glob("a/b?.py", "a/bxy.py") is False


class TestIsExempt:
    def test_exempt_when_every_occurrence_matches_the_pair(self) -> None:
        cluster = _cluster(400, "packages/c/src/a_data.py", "packages/c/src/b_data.py")
        exemptions = [
            DuplicationExemption(
                "packages/c/src/*_data.py", "packages/c/src/*_data.py", "data tables"
            )
        ]
        assert is_exempt(cluster, exemptions) is True

    def test_not_exempt_when_one_occurrence_falls_outside_both_globs(self) -> None:
        cluster = _cluster(400, "packages/c/src/a_data.py", "packages/c/src/real_logic.py")
        exemptions = [
            DuplicationExemption(
                "packages/c/src/*_data.py", "packages/c/src/*_data.py", "data tables"
            )
        ]
        assert is_exempt(cluster, exemptions) is False

    def test_default_deny_with_no_exemptions(self) -> None:
        cluster = _cluster(400, "a.py", "b.py")
        assert is_exempt(cluster, []) is False


class TestDecide:
    def _baseline(self, percent: float = 20.0, largest: int = 500) -> DuplicationBaseline:
        return DuplicationBaseline(
            main_percent=percent, main_largest_cluster=largest, recorded="2026-09-12", commit="x"
        )

    def test_passes_when_within_tolerance_and_no_new_large_cluster(self) -> None:
        result = decide(_tree(20.2), self._baseline(percent=20.0), [])
        assert result.passed is True
        assert "within baseline" in result.message

    def test_fails_when_percent_rises_past_tolerance(self) -> None:
        result = decide(_tree(20.4), self._baseline(percent=20.0), [])
        assert result.passed is False
        assert "rose to 20.4%" in result.message

    def test_passes_at_exactly_the_tolerance_boundary(self) -> None:
        # 50.3 - 50.0 == 0.3 in exact decimal arithmetic; IEEE-754 doubles put it a hair under
        # 0.3 (not "> 0.3"), so this pair -- unlike some other decimal pairs at the same nominal
        # boundary -- deterministically stays on the passing side. Picked for that float behavior,
        # not for the round numbers.
        result = decide(_tree(50.3), self._baseline(percent=50.0), [])
        assert result.passed is True

    def test_fails_on_a_new_non_exempt_cluster_larger_than_baseline(self) -> None:
        big = _cluster(600, "a.py", "b.py")
        result = decide(_tree(10.0, (big,)), self._baseline(percent=20.0, largest=500), [])
        assert result.passed is False
        assert "new cluster 600 tokens" in result.message

    def test_an_exempt_large_cluster_does_not_fail_the_ratchet(self) -> None:
        big = _cluster(600, "packages/c/src/a_data.py", "packages/c/src/b_data.py")
        exemptions = [
            DuplicationExemption(
                "packages/c/src/*_data.py", "packages/c/src/*_data.py", "data tables"
            )
        ]
        result = decide(_tree(10.0, (big,)), self._baseline(percent=20.0, largest=500), exemptions)
        assert result.passed is True

    def test_exempt_cluster_never_raises_the_reported_largest_non_exempt(self) -> None:
        # A huge exempt data-table cluster must not become the "largest non-exempt cluster" the
        # passing message reports -- the exemption must not quietly raise the bar for everything
        # else.
        huge_exempt = _cluster(5000, "packages/c/src/a_data.py", "packages/c/src/b_data.py")
        small_real = _cluster(510, "packages/c/src/logic.py", "packages/d/src/logic.py")
        exemptions = [
            DuplicationExemption(
                "packages/c/src/*_data.py", "packages/c/src/*_data.py", "data tables"
            )
        ]
        result = decide(
            _tree(10.0, (huge_exempt, small_real)),
            self._baseline(percent=20.0, largest=520),
            exemptions,
        )

        assert result.passed is True
        assert "largest non-exempt cluster 510 tokens" in result.message

    def test_both_percent_and_cluster_failures_are_reported_together(self) -> None:
        big = _cluster(600, "a.py", "b.py")
        result = decide(_tree(30.0, (big,)), self._baseline(percent=20.0, largest=500), [])
        assert result.passed is False
        assert "rose to 30.0%" in result.message
        assert "new cluster 600 tokens" in result.message
