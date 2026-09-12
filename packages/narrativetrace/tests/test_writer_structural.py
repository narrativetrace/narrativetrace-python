# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the structural-artifact / last-green-delta slice of
:func:`narrativetrace.output.writer.write_trace` — mirrors Java's ``LastGreenLifecycleTest``:
write → compare → verdict → promote, last green advancing only on a fully green verdict.
"""

from __future__ import annotations

from pathlib import Path

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.output.artifact_identity import ArtifactIdentity
from narrativetrace.output.structural_delta import Kind
from narrativetrace.output.writer import TraceArtifact, write_trace
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree


def _tree(*method_names: str) -> TraceTree:
    return TraceTree(
        [TraceNode(MethodSignature("Svc", name, []), [], Returned("ok")) for name in method_names]
    )


def _structural_path(tmp_path: Path, class_name: str = "T", slug: str = "m") -> Path:
    return tmp_path / "structural" / class_name / f"{slug}.nt"


class TestFirstRun:
    def test_a_first_run_writes_the_structural_artifact_and_reports_new(
        self, tmp_path: Path
    ) -> None:
        result = write_trace(
            _tree("run"),
            TraceMetadata("s", ScenarioResult.SUCCESS),
            TraceArtifact(tmp_path, "T", "m"),
        )
        assert result.delta is not None
        assert result.delta.kind is Kind.NEW
        assert _structural_path(tmp_path).is_file()

    def test_a_failed_first_run_computes_the_delta_but_never_writes_a_baseline(
        self, tmp_path: Path
    ) -> None:
        result = write_trace(
            _tree("run"),
            TraceMetadata("s", ScenarioResult.ERROR),
            TraceArtifact(tmp_path, "T", "m"),
        )
        assert result.delta is not None
        assert result.delta.kind is Kind.NEW
        assert not _structural_path(tmp_path).is_file()


class TestLastGreenLifecycle:
    """Reproduces the exact reference sequence: baseline -> add a call -> run -> fail -> baseline
    unchanged -> remove the call -> run -> "unchanged since last green"."""

    def test_baseline_add_call_fail_leaves_baseline_untouched_then_revert_reports_unchanged(
        self, tmp_path: Path
    ) -> None:
        artifact = TraceArtifact(tmp_path, "T", "m")

        # 1. Establish the baseline with a green run.
        write_trace(_tree("run"), TraceMetadata("s", ScenarioResult.SUCCESS), artifact)
        baseline_bytes = _structural_path(tmp_path).read_bytes()

        # 2. Add a call and fail the test: the delta reports CHANGED, but the baseline must not
        #    move -- "green" is the whole verdict, and a failed run is not green.
        failing = write_trace(
            _tree("run", "extra"), TraceMetadata("s", ScenarioResult.ERROR), artifact
        )
        assert failing.delta is not None
        assert failing.delta.kind is Kind.CHANGED
        assert _structural_path(tmp_path).read_bytes() == baseline_bytes

        # 3. Remove the call again (revert) and pass: the delta against the untouched baseline
        #    reports UNCHANGED -- the rejected change never leaked into the baseline.
        reverted = write_trace(_tree("run"), TraceMetadata("s", ScenarioResult.SUCCESS), artifact)
        assert reverted.delta is not None
        assert reverted.delta.kind is Kind.UNCHANGED
        assert _structural_path(tmp_path).read_bytes() == baseline_bytes

    def test_an_accepted_change_still_advances_the_last_green_artifact(
        self, tmp_path: Path
    ) -> None:
        artifact = TraceArtifact(tmp_path, "T", "m")
        write_trace(_tree("run"), TraceMetadata("s", ScenarioResult.SUCCESS), artifact)
        baseline_bytes = _structural_path(tmp_path).read_bytes()

        accepted = write_trace(
            _tree("run", "extra"), TraceMetadata("s", ScenarioResult.SUCCESS), artifact
        )

        assert accepted.delta is not None
        assert accepted.delta.kind is Kind.CHANGED
        assert _structural_path(tmp_path).read_bytes() != baseline_bytes
        assert b"extra" in _structural_path(tmp_path).read_bytes()


class TestStructuralOnlyOnMarkdown:
    def test_text_format_does_not_write_a_structural_artifact(self, tmp_path: Path) -> None:
        result = write_trace(
            _tree("run"),
            TraceMetadata("s", ScenarioResult.SUCCESS),
            TraceArtifact(tmp_path, "T", "m", fmt="text"),
        )
        assert result.delta is None
        assert not _structural_path(tmp_path).is_file()


class TestInvocationIdentityFeedsTheStructuralHeader:
    def test_the_structural_header_names_the_invocation_never_its_display_name(
        self, tmp_path: Path
    ) -> None:
        identity = ArtifactIdentity.of_invocation("CatalogTest", "equipmentCanBeFound", 2, "TENT")
        artifact = TraceArtifact(
            tmp_path,
            "CatalogTest",
            "equipmentCanBeFound",
            identity=identity,
            display_name="find TENT",
        )
        write_trace(_tree("run"), TraceMetadata("find TENT", ScenarioResult.SUCCESS), artifact)

        structural_path = _structural_path(
            tmp_path, "CatalogTest", "equipment_can_be_found-002-tent"
        )
        content = structural_path.read_text(encoding="utf-8")
        assert content.startswith("scenario: Equipment can be found #2\n")
        assert "TENT" not in content

    def test_the_markdown_narrative_still_carries_the_display_name(self, tmp_path: Path) -> None:
        identity = ArtifactIdentity.of_invocation("CatalogTest", "equipmentCanBeFound", 2, "TENT")
        artifact = TraceArtifact(
            tmp_path,
            "CatalogTest",
            "equipmentCanBeFound",
            identity=identity,
            display_name="find TENT",
        )
        result = write_trace(
            _tree("run"), TraceMetadata("find TENT", ScenarioResult.SUCCESS), artifact
        )
        md_path = next(p for p in result.files if p.suffix == ".md")
        assert "find TENT" in md_path.read_text(encoding="utf-8")
