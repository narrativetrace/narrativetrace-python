# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The duplication report's pure decision logic (`scripts/duplication_report.py`).

`_run_jscpd`/`run_report`'s subprocess and filesystem glue is exercised for real by `poe
duplication-report` / `poe check` running the scan against this repository; these tests drive
`normalize`, `aggregate`, `union_duplicated_lines`, `covered_line_count`, the JSON
(de)serialization, `summary_line`, and the missing-Node decision/status functions in isolation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.duplication_report import (
    DuplicationCluster,
    DuplicationOccurrence,
    DuplicationScanResult,
    DuplicationTreeResult,
    aggregate,
    covered_line_count,
    decide_missing_node,
    duplication_scan_required,
    normalize,
    read_json,
    record_ran_clean,
    record_skipped,
    relativize,
    scan_status,
    summary_line,
    union_duplicated_lines,
    write_json,
)


def _occurrence(file: str, start: int, end: int) -> DuplicationOccurrence:
    return DuplicationOccurrence(file=file, start_line=start, end_line=end)


def _cluster(tokens: int, lines: int, *occurrences: DuplicationOccurrence) -> DuplicationCluster:
    return DuplicationCluster(tokens=tokens, lines=lines, occurrences=occurrences)


class TestCoveredLineCount:
    def test_empty_ranges_is_zero(self) -> None:
        assert covered_line_count([]) == 0

    def test_single_range_counts_its_own_span(self) -> None:
        assert covered_line_count([(10, 14)]) == 5

    def test_overlapping_ranges_count_each_line_once(self) -> None:
        # 10-14 and 12-16 overlap on 12-14; the union is 10-16, 7 lines, not 5 + 5 = 10.
        assert covered_line_count([(10, 14), (12, 16)]) == 7

    def test_adjacent_ranges_merge(self) -> None:
        # 10-14 and 15-16 touch with no gap: still one contiguous 10-16 span.
        assert covered_line_count([(10, 14), (15, 16)]) == 7

    def test_disjoint_ranges_sum_independently(self) -> None:
        assert covered_line_count([(1, 2), (10, 12)]) == 2 + 3

    def test_unsorted_input_still_unions_correctly(self) -> None:
        assert covered_line_count([(10, 16), (1, 2), (12, 14)]) == 7 + 2


class TestUnionDuplicatedLines:
    def test_same_file_overlapping_clusters_count_lines_once(self) -> None:
        clusters = [
            _cluster(80, 5, _occurrence("a.py", 1, 5), _occurrence("a.py", 20, 24)),
            _cluster(70, 5, _occurrence("a.py", 3, 7), _occurrence("a.py", 22, 26)),
        ]
        # a.py: {1-5, 20-24} union {3-7, 22-26} -> 1-7 (7 lines) + 20-26 (7 lines) = 14.
        assert union_duplicated_lines(clusters) == 14

    def test_different_files_never_merge(self) -> None:
        clusters = [_cluster(60, 5, _occurrence("a.py", 1, 5), _occurrence("b.py", 1, 5))]
        assert union_duplicated_lines(clusters) == 10

    def test_no_clusters_is_zero(self) -> None:
        assert union_duplicated_lines([]) == 0


class TestAggregate:
    def test_zero_total_lines_is_zero_percent(self) -> None:
        result = aggregate(0, 0, [])
        assert result.percent == 0.0
        assert result.lines_total == 0

    def test_percent_rounds_half_up_to_one_decimal(self) -> None:
        # 225 / 2000 * 100 = 11.25 -- an exact tie at the second decimal. Round-half-up (this
        # module's own rounding) takes 11.3; Python's banker's-rounding round() would not
        # reliably agree, which is exactly why this module rolls its own.
        result = aggregate(2000, 225, [])
        assert result.percent == 11.3

    def test_clusters_sorted_by_tokens_descending(self) -> None:
        small = _cluster(60, 5, _occurrence("a.py", 1, 5), _occurrence("b.py", 1, 5))
        large = _cluster(200, 10, _occurrence("c.py", 1, 10), _occurrence("d.py", 1, 10))
        result = aggregate(100, 20, [small, large])
        assert [cluster.tokens for cluster in result.clusters] == [200, 60]

    def test_percent_never_exceeds_100(self) -> None:
        # Pathological input (should never happen given a real union count) still cannot render
        # over 100%, since the union guarantees duplicated <= total.
        result = aggregate(10, 10, [])
        assert result.percent == 100.0


class TestNormalize:
    def test_parses_duplicates_and_relativizes_paths(self, tmp_path: Path) -> None:
        root = tmp_path
        raw = {
            "duplicates": [
                {
                    "tokens": 80,
                    "lines": 6,
                    "firstFile": {"name": str(root / "packages/a/src/m.py"), "start": 1, "end": 6},
                    "secondFile": {
                        "name": str(root / "packages/b/src/n.py"),
                        "start": 10,
                        "end": 15,
                    },
                }
            ],
            "statistics": {"total": {"lines": 200}},
        }

        result = normalize(raw, root)

        assert result.lines_total == 200
        assert len(result.clusters) == 1
        cluster = result.clusters[0]
        assert cluster.tokens == 80
        assert cluster.occurrences[0].file == "packages/a/src/m.py"
        assert cluster.occurrences[1].file == "packages/b/src/n.py"

    def test_no_duplicates_is_zero_percent(self, tmp_path: Path) -> None:
        raw = {"duplicates": [], "statistics": {"total": {"lines": 50}}}
        result = normalize(raw, tmp_path)
        assert result.clusters == ()
        assert result.percent == 0.0


class TestRelativize:
    def test_strips_the_repository_root_prefix(self, tmp_path: Path) -> None:
        absolute = str(tmp_path / "packages" / "a" / "src" / "m.py")
        assert relativize(absolute, tmp_path) == "packages/a/src/m.py"

    def test_path_outside_root_is_returned_unchanged(self, tmp_path: Path) -> None:
        outside = "/somewhere/else/m.py"
        assert relativize(outside, tmp_path) == outside

    def test_a_sibling_directory_that_shares_a_prefix_is_not_treated_as_inside(
        self, tmp_path: Path
    ) -> None:
        # tmp_path resolves to e.g. /tmp/foo; a sibling "/tmp/foobar/..." must not be mistaken
        # for a path under /tmp/foo just because the strings share a prefix.
        sibling = str(tmp_path) + "-sibling" + "/m.py"
        assert relativize(sibling, tmp_path) == sibling


class TestJsonRoundTrip:
    def test_write_then_read_reproduces_the_scan(self, tmp_path: Path) -> None:
        main = DuplicationTreeResult(
            lines_total=100,
            lines_duplicated=20,
            percent=20.0,
            clusters=(_cluster(80, 6, _occurrence("a.py", 1, 6), _occurrence("b.py", 1, 6)),),
        )
        test_tree = DuplicationTreeResult(
            lines_total=10, lines_duplicated=0, percent=0.0, clusters=()
        )
        scan = DuplicationScanResult(
            tool="jscpd",
            tool_version="5.2.0",
            language="python",
            min_tokens=60,
            main=main,
            test=test_tree,
        )
        path = tmp_path / "duplication.json"

        write_json(scan, path)
        result = read_json(path)

        assert result == scan

    def test_written_json_uses_camel_case_keys(self, tmp_path: Path) -> None:
        main = DuplicationTreeResult(lines_total=1, lines_duplicated=0, percent=0.0, clusters=())
        scan = DuplicationScanResult(
            tool="jscpd",
            tool_version="5.2.0",
            language="python",
            min_tokens=60,
            main=main,
            test=main,
        )
        path = tmp_path / "duplication.json"

        write_json(scan, path)

        text = path.read_text(encoding="utf-8")
        assert '"toolVersion"' in text
        assert '"minTokens"' in text
        assert '"linesTotal"' in text
        assert '"linesDuplicated"' in text


class TestSummaryLine:
    def test_no_clusters_reads_as_no_clusters(self) -> None:
        empty = DuplicationTreeResult(lines_total=10, lines_duplicated=0, percent=0.0, clusters=())
        scan = DuplicationScanResult("jscpd", "5.2.0", "python", 60, empty, empty)
        line = summary_line(scan)
        assert "no clusters" in line
        assert "reported, not gated" in line

    def test_names_the_largest_cluster_and_its_locations(self) -> None:
        big = _cluster(
            500,
            20,
            _occurrence("packages/a/src/big.py", 1, 20),
            _occurrence("packages/b/src/big.py", 1, 20),
        )
        small = _cluster(60, 5, _occurrence("a.py", 1, 5), _occurrence("b.py", 1, 5))
        main = DuplicationTreeResult(1000, 100, 10.0, (big, small))
        empty = DuplicationTreeResult(0, 0, 0.0, ())
        scan = DuplicationScanResult("jscpd", "5.2.0", "python", 60, main, empty)

        line = summary_line(scan)

        assert "largest 500 tokens" in line
        assert "packages/a/src/big.py:1" in line
        assert "2 clusters" in line


class TestMissingNodeDecision:
    def test_fails_outright_when_required(self) -> None:
        decision = decide_missing_node(required=True)
        assert decision.fail is True
        assert "required" in decision.message

    def test_warns_loudly_when_not_required(self) -> None:
        decision = decide_missing_node(required=False)
        assert decision.fail is False
        assert "SKIPPED" in decision.message
        assert "NOT a clean scan" in decision.message


class TestDuplicationScanRequired:
    def test_false_with_neither_env_var_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("NARRATIVETRACE_DUPLICATION_REQUIRED", raising=False)
        assert duplication_scan_required() is False

    def test_true_when_ci_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("NARRATIVETRACE_DUPLICATION_REQUIRED", raising=False)
        assert duplication_scan_required() is True

    def test_true_when_explicit_flag_is_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("NARRATIVETRACE_DUPLICATION_REQUIRED", "true")
        assert duplication_scan_required() is True


class TestStatusRecording:
    def test_never_ran_when_nothing_recorded_yet(self, tmp_path: Path) -> None:
        assert scan_status(tmp_path, "jscpd") == "never-ran"

    def test_records_and_reads_back_ran_clean(self, tmp_path: Path) -> None:
        record_ran_clean(tmp_path, "jscpd")
        assert scan_status(tmp_path, "jscpd") == "ran-clean"

    def test_records_and_reads_back_a_skip_reason(self, tmp_path: Path) -> None:
        record_skipped(tmp_path, "jscpd", "no Node/npx on PATH")
        assert scan_status(tmp_path, "jscpd") == "skipped: no Node/npx on PATH"
