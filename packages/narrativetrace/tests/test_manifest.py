# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for :mod:`narrativetrace.output.manifest` — the ``manifest.json`` scenario → file index."""

from __future__ import annotations

import json
from pathlib import Path

from narrativetrace.output.artifact_identity import ArtifactIdentity
from narrativetrace.output.manifest import Entry, entry_for, render, write
from narrativetrace.output.run_identity import RunIdentity


class TestEntryFor:
    def test_probes_only_files_that_actually_exist(self, tmp_path: Path) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "customerPlacesOrder")
        entry = entry_for(tmp_path, identity, "Customer places order")
        assert entry.artifacts == {}

    def test_finds_the_trace_and_structural_files_once_written(self, tmp_path: Path) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "customerPlacesOrder")
        slug = identity.file_slug()
        trace_dir = tmp_path / "traces" / "CatalogTest"
        trace_dir.mkdir(parents=True)
        (trace_dir / f"{slug}.md").write_text("x", encoding="utf-8")
        structural_dir = tmp_path / "structural" / "CatalogTest"
        structural_dir.mkdir(parents=True)
        (structural_dir / f"{slug}.nt").write_text("x", encoding="utf-8")

        entry = entry_for(tmp_path, identity, "Customer places order")

        assert entry.artifacts["trace"] == f"traces/CatalogTest/{slug}.md"
        assert entry.artifacts["structural"] == f"structural/CatalogTest/{slug}.nt"

    def test_invocation_identity_is_carried_on_the_entry(self, tmp_path: Path) -> None:
        identity = ArtifactIdentity.of_invocation("CatalogTest", "equipmentCanBeFound", 2, "TENT")
        entry = entry_for(tmp_path, identity, "find TENT")
        assert entry.identity.invocation_index == 2


class TestRender:
    def test_writes_nothing_at_all_when_the_run_traced_no_scenario(self, tmp_path: Path) -> None:
        write([], tmp_path)
        assert not (tmp_path / "manifest.json").exists()

    def test_render_produces_valid_json_with_the_schema_marker(self) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "customerPlacesOrder")
        entry = Entry("Customer places order", identity, {"trace": "traces/CatalogTest/x.md"})
        document = json.loads(render([entry]))
        assert document["schema"] == "narrativetrace/scenario-manifest/1"
        assert document["scenarios"][0]["scenario"] == "Customer places order"
        assert document["scenarios"][0]["testClass"] == "CatalogTest"
        assert "invocation" not in document["scenarios"][0]

    def test_invocation_rows_carry_the_invocation_index(self) -> None:
        identity = ArtifactIdentity.of_invocation("CatalogTest", "equipmentCanBeFound", 2, "TENT")
        entry = Entry("find TENT", identity, {})
        document = json.loads(render([entry]))
        assert document["scenarios"][0]["invocation"] == 2

    def test_write_creates_the_manifest_file(self, tmp_path: Path) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "customerPlacesOrder")
        entry = Entry("Customer places order", identity, {})
        write([entry], tmp_path)
        assert (tmp_path / "manifest.json").is_file()


class TestRunField:
    """The top-level `run` object naming the test-suite run a manifest belongs to (2026-09-13
    ruling, item 2) -- omitted entirely when no `RunIdentity` is given."""

    def _entry(self) -> Entry:
        identity = ArtifactIdentity.of_method("T", "finds")
        return Entry("finds", identity, {"trace": "traces/T/finds.md"})

    def test_omits_the_run_object_when_no_run_identity_is_given(self) -> None:
        document = json.loads(render([self._entry()]))
        assert "run" not in document

    def test_names_the_run_top_level_when_a_run_identity_is_given(self) -> None:
        run = RunIdentity("a" * 32, "bold elk soars")
        manifest = render([self._entry()], run)
        document = json.loads(manifest)
        assert document["run"] == {"id": "a" * 32, "name": "bold elk soars"}
        # Top-level, alongside "scenarios" -- not folded into any scenario row.
        assert manifest.index('"run"') < manifest.index('"scenarios"')

    def test_two_different_run_identities_never_change_a_scenario_row(self) -> None:
        entry = self._entry()
        run_one = RunIdentity("a" * 32, "bold elk soars")
        run_two = RunIdentity("b" * 32, "shy owl waits")

        manifest_one = render([entry], run_one)
        manifest_two = render([entry], run_two)

        scenarios_one = manifest_one[manifest_one.index('"scenarios"') :]
        scenarios_two = manifest_two[manifest_two.index('"scenarios"') :]
        assert scenarios_one == scenarios_two

    def test_write_creates_the_manifest_with_a_run_object(self, tmp_path: Path) -> None:
        run = RunIdentity("a" * 32, "bold elk soars")
        write([self._entry()], tmp_path, run)
        document = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert document["run"]["name"] == "bold elk soars"


class TestEntryImmutability:
    def test_the_artifacts_map_is_copied_defensively(self) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "customerPlacesOrder")
        source = {"trace": "x.md"}
        entry = Entry("scenario", identity, source)
        source["trace"] = "mutated.md"
        assert entry.artifacts["trace"] == "x.md"
