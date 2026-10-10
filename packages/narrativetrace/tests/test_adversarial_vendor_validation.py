# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial tests for vendor_validation.py: edge cases in recording, staging, and aggregation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts.vendor_validation import (
    VendorCheck,
    VendorCheckResult,
    VendorOutcome,
    aggregate,
    record,
    recorded_status,
    stage_from_head,
)

ROW = VendorCheck(
    tool="faketool",
    probe=("--version",),
    validate=("validate",),
    artifact="some/artifact.json",
    staged_paths=("some",),
    install_hint="put faketool on the PATH",
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=T", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


class TestRecordEdgeCases:
    """Edge cases for record() function."""

    def test_record_twice_for_same_tool_overwrites(self, tmp_path: Path) -> None:
        """Calling record twice for the same tool should overwrite cleanly."""
        reports = tmp_path / "reports"

        result1 = VendorCheckResult(
            "faketool", "a/b.json", VendorOutcome.PASSED, "first run", "output1"
        )
        result2 = VendorCheckResult(
            "faketool", "a/b.json", VendorOutcome.FAILED, "second run", "output2"
        )

        record(reports, result1)
        record(reports, result2)

        # Should read the second one
        status = recorded_status(reports, "faketool")
        assert status.startswith("failed: ")
        assert "second run" in status

    def test_record_preserves_tool_names_with_special_chars(self, tmp_path: Path) -> None:
        """Tool names with dashes/underscores should be recorded correctly."""
        reports = tmp_path / "reports"

        result = VendorCheckResult("my-tool_v2", "artifact.json", VendorOutcome.PASSED, "ok", "")
        record(reports, result)

        status = recorded_status(reports, "my-tool_v2")
        assert status.startswith("passed: ")

    def test_record_handles_very_long_messages(self, tmp_path: Path) -> None:
        """Very long messages should be recorded and retrieved."""
        reports = tmp_path / "reports"
        long_message = "x" * 10000

        result = VendorCheckResult("faketool", "a/b.json", VendorOutcome.FAILED, long_message, "")
        record(reports, result)

        status = recorded_status(reports, "faketool")
        assert long_message in status

    def test_record_with_empty_message(self, tmp_path: Path) -> None:
        """Empty message should still record the outcome."""
        reports = tmp_path / "reports"

        result = VendorCheckResult("faketool", "a/b.json", VendorOutcome.PASSED, "", "")
        record(reports, result)

        status = recorded_status(reports, "faketool")
        # With empty message, the colon has no trailing space
        assert status == "passed:"


class TestAggregateEdgeCases:
    """Edge cases for aggregate() function."""

    @staticmethod
    def _result(outcome: VendorOutcome, tool: str = "tool1") -> VendorCheckResult:
        return VendorCheckResult(tool, "a/b.json", outcome, "msg", "")

    def test_aggregate_many_passed_rows(self) -> None:
        """Multiple passing rows should still result in PASSED."""
        results = [self._result(VendorOutcome.PASSED, f"tool{i}") for i in range(10)]
        assert aggregate(results) is VendorOutcome.PASSED

    def test_aggregate_passed_and_skipped_is_passed(self) -> None:
        """Even with many SKIPPEDs, one PASSED makes the whole run PASSED."""
        results = [
            self._result(VendorOutcome.SKIPPED, "tool1"),
            self._result(VendorOutcome.SKIPPED, "tool2"),
            self._result(VendorOutcome.PASSED, "tool3"),
            self._result(VendorOutcome.SKIPPED, "tool4"),
        ]
        assert aggregate(results) is VendorOutcome.PASSED

    def test_aggregate_single_failed_overrides_many_passed(self) -> None:
        """One FAILED makes everything fail, regardless of passes."""
        results = [
            self._result(VendorOutcome.PASSED, "tool1"),
            self._result(VendorOutcome.PASSED, "tool2"),
            self._result(VendorOutcome.FAILED, "tool3"),
            self._result(VendorOutcome.PASSED, "tool4"),
        ]
        assert aggregate(results) is VendorOutcome.FAILED

    def test_aggregate_hundreds_of_skipped(self) -> None:
        """Hundreds of SKIPPEDs with no passes = SKIP."""
        results = [self._result(VendorOutcome.SKIPPED, f"tool{i}") for i in range(100)]
        assert aggregate(results) is VendorOutcome.SKIPPED

    def test_aggregate_preserves_order_invariant(self) -> None:
        """Aggregate result doesn't depend on order."""
        results_a = [
            self._result(VendorOutcome.SKIPPED),
            self._result(VendorOutcome.PASSED, "tool2"),
            self._result(VendorOutcome.FAILED, "tool3"),
        ]
        results_b = [
            self._result(VendorOutcome.FAILED, "tool3"),
            self._result(VendorOutcome.SKIPPED),
            self._result(VendorOutcome.PASSED, "tool2"),
        ]
        # Both orders should yield FAILED
        assert aggregate(results_a) is VendorOutcome.FAILED
        assert aggregate(results_b) is VendorOutcome.FAILED


class TestStageFromHeadEdgeCases:
    """Edge cases for stage_from_head()."""

    def test_stage_from_head_rejects_empty_paths_tuple(self, tmp_path: Path) -> None:
        """An empty `paths` tuple is REJECTED, not silently treated as "stage nothing".

        Verified empirically: `git archive HEAD --` with nothing after `--` is NOT an empty
        pathspec in git's own semantics -- it archives the ENTIRE tree, identical to omitting
        `--` altogether. A caller that passed `()` by mistake (e.g. a future `VendorCheck` row
        with an empty `staged_paths`) would silently stage the whole repository instead of
        nothing, violating `stage_from_head`'s own documented contract ("stages `paths`").
        The ORIGINAL version of this adversarial test asserted only `into.exists()`, which
        passes regardless of what actually landed inside -- too weak to have caught this.
        """
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "--quiet")
        _git(repo, "commit", "--allow-empty", "-m", "initial")

        into = tmp_path / "into"
        with pytest.raises(ValueError, match="paths must not be empty"):
            stage_from_head(repo, (), into)

    def test_stage_from_head_preserves_directory_structure(self, tmp_path: Path) -> None:
        """Staging should preserve directory nesting."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "--quiet")

        nested = repo / "a" / "b" / "c"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("content", encoding="utf-8")
        _git(repo, "add", "a")
        _git(repo, "commit", "-m", "nested")

        into = tmp_path / "into"
        stage_from_head(repo, ("a",), into)

        # Nested structure should exist
        staged_file = into / "a" / "b" / "c" / "file.txt"
        assert staged_file.is_file()
        assert staged_file.read_text(encoding="utf-8") == "content"

    def test_stage_from_head_ignores_uncommitted_changes(self, tmp_path: Path) -> None:
        """Staging takes HEAD, not working tree."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "--quiet")

        file_a = repo / "file.txt"
        file_a.write_text("committed", encoding="utf-8")
        _git(repo, "add", "file.txt")
        _git(repo, "commit", "-m", "commit")

        # Modify but don't commit
        file_a.write_text("modified", encoding="utf-8")

        into = tmp_path / "into"
        stage_from_head(repo, ("file.txt",), into)

        staged = into / "file.txt"
        assert staged.read_text(encoding="utf-8") == "committed"

    def test_stage_from_head_handles_paths_with_special_chars(self, tmp_path: Path) -> None:
        """Staging should handle file paths with spaces, dashes, etc."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "--quiet")

        special_dir = repo / "my-test_dir"
        special_dir.mkdir()
        (special_dir / "file with spaces.txt").write_text("content", encoding="utf-8")
        _git(repo, "add", "my-test_dir")
        _git(repo, "commit", "-m", "special")

        into = tmp_path / "into"
        stage_from_head(repo, ("my-test_dir",), into)

        staged = into / "my-test_dir" / "file with spaces.txt"
        assert staged.is_file()

    def test_stage_from_head_raises_on_missing_path_in_head(self, tmp_path: Path) -> None:
        """Staging a path that doesn't exist at HEAD should raise RuntimeError."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init", "--quiet")
        _git(repo, "commit", "--allow-empty", "-m", "initial")

        into = tmp_path / "into"

        with pytest.raises(RuntimeError) as exc_info:
            stage_from_head(repo, ("nonexistent/path",), into)

        assert "git archive" in str(exc_info.value)
