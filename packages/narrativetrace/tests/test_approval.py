# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for :mod:`narrativetrace.output.approval` — approval mode's verify/promote lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from narrativetrace.loss import TraceLoss
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.output import approval
from narrativetrace.output.artifact_identity import ArtifactIdentity
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree


def _tree(*method_names: str) -> TraceTree:
    return TraceTree(
        [TraceNode(MethodSignature("Svc", name, []), [], Returned("ok")) for name in method_names]
    )


class TestApprovedFile:
    def test_path_follows_the_same_class_and_slug_rules_as_other_artifacts(
        self, tmp_path: Path
    ) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "customerPlacesOrder")
        path = approval.approved_file(tmp_path, identity)
        assert path == tmp_path / "CatalogTest" / "customer_places_order.approved.nt"


class TestNoBaseline:
    def test_writes_the_received_trace_and_raises(self, tmp_path: Path) -> None:
        approved = tmp_path / "T" / "m.approved.nt"
        with pytest.raises(AssertionError, match="No approved trace"):
            approval.verify(_tree("run"), "scenario", approved)
        received = tmp_path / "T" / "m.received.nt"
        assert received.is_file()
        assert received.read_text(encoding="utf-8").startswith("scenario: scenario\n")


class TestMatchingStructure:
    def test_verify_passes_silently_and_deletes_a_stale_received_trace(
        self, tmp_path: Path
    ) -> None:
        approved = tmp_path / "T" / "m.approved.nt"
        approved.parent.mkdir(parents=True)
        approved.write_text("scenario: scenario\n\n- Svc.run() → value\n", encoding="utf-8")
        stale_received = tmp_path / "T" / "m.received.nt"
        stale_received.write_text("stale", encoding="utf-8")

        note = approval.verify(_tree("run"), "scenario", approved)

        assert note == ""
        assert not stale_received.exists()


class TestChangedStructure:
    def test_writes_the_received_trace_and_raises_with_the_diff(self, tmp_path: Path) -> None:
        approved = tmp_path / "T" / "m.approved.nt"
        approved.parent.mkdir(parents=True)
        approved.write_text("scenario: scenario\n\n- Svc.run() → value\n", encoding="utf-8")

        with pytest.raises(AssertionError, match="Structure changed against the approved trace"):
            approval.verify(_tree("run", "extra"), "scenario", approved)

        received = tmp_path / "T" / "m.received.nt"
        assert received.is_file()
        assert "extra" in received.read_text(encoding="utf-8")


class TestPromoteReceived:
    def test_promotes_every_received_trace_under_the_root(self, tmp_path: Path) -> None:
        (tmp_path / "A").mkdir()
        (tmp_path / "A" / "one.received.nt").write_text("one", encoding="utf-8")
        (tmp_path / "B").mkdir()
        (tmp_path / "B" / "two.received.nt").write_text("two", encoding="utf-8")

        promoted = approval.promote_received(tmp_path)

        assert {p.name for p in promoted} == {"one.approved.nt", "two.approved.nt"}
        assert (tmp_path / "A" / "one.approved.nt").read_text(encoding="utf-8") == "one"
        assert not (tmp_path / "A" / "one.received.nt").exists()

    def test_ignores_incomplete_traces_by_name(self, tmp_path: Path) -> None:
        (tmp_path / "A").mkdir()
        (tmp_path / "A" / "one.incomplete.nt").write_text("one", encoding="utf-8")

        promoted = approval.promote_received(tmp_path)

        assert promoted == []
        assert (tmp_path / "A" / "one.incomplete.nt").exists()

    def test_a_missing_root_promotes_nothing(self, tmp_path: Path) -> None:
        assert approval.promote_received(tmp_path / "does-not-exist") == []

    def test_the_full_review_workflow_run_reject_review_promote_run(self, tmp_path: Path) -> None:
        approved = tmp_path / "T" / "m.approved.nt"

        with pytest.raises(AssertionError):
            approval.verify(_tree("run"), "scenario", approved)

        approval.promote_received(tmp_path)
        assert approved.is_file()

        note = approval.verify(_tree("run"), "scenario", approved)
        assert note == ""


class TestLossyRuns:
    def test_a_lossy_run_consistent_with_the_baseline_is_reported_not_as_unchanged(
        self, tmp_path: Path
    ) -> None:
        approved = tmp_path / "T" / "m.approved.nt"
        approved.parent.mkdir(parents=True)
        approved.write_text(
            "scenario: scenario\n\n- Svc.run() → value\n- Svc.other() → value\n", encoding="utf-8"
        )
        loss = TraceLoss(dropped_events=1, refused_scopes=0, refused_spans=0)

        note = approval.verify(_tree("run"), "scenario", approved, loss)

        assert "consistent with baseline" in note
        assert "incomplete" in note
        incomplete = tmp_path / "T" / "m.incomplete.nt"
        assert not incomplete.exists()

    def test_a_lossy_run_with_an_addition_still_fails(self, tmp_path: Path) -> None:
        approved = tmp_path / "T" / "m.approved.nt"
        approved.parent.mkdir(parents=True)
        approved.write_text("scenario: scenario\n\n- Svc.run() → value\n", encoding="utf-8")
        loss = TraceLoss(dropped_events=1, refused_scopes=0, refused_spans=0)

        with pytest.raises(AssertionError, match="loss cannot explain"):
            approval.verify(_tree("run", "extra"), "scenario", approved, loss)

        incomplete = tmp_path / "T" / "m.incomplete.nt"
        assert incomplete.is_file()

    def test_no_baseline_and_a_lossy_run_writes_incomplete_not_received(
        self, tmp_path: Path
    ) -> None:
        approved = tmp_path / "T" / "m.approved.nt"
        loss = TraceLoss(dropped_events=1, refused_scopes=0, refused_spans=0)

        with pytest.raises(AssertionError, match="deliberately not promotable"):
            approval.verify(_tree("run"), "scenario", approved, loss)

        assert (tmp_path / "T" / "m.incomplete.nt").is_file()
        assert not (tmp_path / "T" / "m.received.nt").exists()

    def test_incomplete_traces_are_never_promoted_even_after_being_written(
        self, tmp_path: Path
    ) -> None:
        approved = tmp_path / "T" / "m.approved.nt"
        loss = TraceLoss(dropped_events=1, refused_scopes=0, refused_spans=0)
        with pytest.raises(AssertionError):
            approval.verify(_tree("run"), "scenario", approved, loss)

        promoted = approval.promote_received(tmp_path)

        assert promoted == []
        assert not approved.exists()
