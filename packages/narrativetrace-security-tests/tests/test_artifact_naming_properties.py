# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A: the writers' other input -- not the value, the *name*.

``ArtifactNamingPropertyTest``. Every other target in this suite feeds hostile data
through a renderer. This one feeds it through the path builder, because a trace artifact's
location is derived from a test class and method name, and ``write_trace``/``TraceArtifact`` is
public API whose callers do not all derive those from a real class -- a scenario name, an HTTP
route or a test-framework display name reaches these functions in real integrations.

The limit asserted here is 255 *bytes*, not characters: ext4, APFS and every other mainstream
filesystem count bytes, so 200 three-byte characters overflow a component 200 ASCII ones fit
inside. The corpus carries that exact case, and a character-counting cap passes it while the
filesystem refuses the write.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hostile_corpus import CorpusCase, names

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.output.paths import trace_file
from narrativetrace.output.writer import TraceArtifact, write_trace
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree

_MAX_COMPONENT_BYTES = 255


def _tree() -> TraceTree:
    node = TraceNode(MethodSignature("HostileCase", "run", []), [], Returned('"probe"'))
    return TraceTree([node])


def _write(base_dir: Path, class_name: str, method_name: str) -> list[Path]:
    result = write_trace(
        _tree(),
        TraceMetadata("s", ScenarioResult.SUCCESS),
        TraceArtifact(base_dir, class_name, method_name),
        json_exporter=lambda _t: "{}",
        diagram_renderer=lambda _t: "sequenceDiagram",
    )
    return result.files


class TestEveryCorpusNameWritesWithoutRaising:
    @pytest.mark.parametrize("name", names(), ids=str)
    def test_a_hostile_class_name_writes_every_artifact_without_raising(
        self, name: CorpusCase, tmp_path: Path
    ) -> None:
        _write(tmp_path / name.id / "class-route" / "out", name.value, "m")

    @pytest.mark.parametrize("name", names(), ids=str)
    def test_a_hostile_method_name_writes_every_artifact_without_raising(
        self, name: CorpusCase, tmp_path: Path
    ) -> None:
        _write(tmp_path / name.id / "method-route" / "out", "cls", name.value)


class TestEveryArtifactStaysInsideTheOutputDirectory:
    """The escape this suite exists to catch: a class name reaching ``Path`` construction
    unfiltered put artifacts at an *absolute* path outside the output directory the caller gave
    (``../../etc/passwd`` resolving through a ``/`` join, which takes an absolute right-hand side
    as the whole answer). The sandbox is one level above the output directory, so anything that
    walked out of it either lands somewhere this assertion can see, or leaves the expected
    location empty -- either way, the property fails loudly."""

    @pytest.mark.parametrize("name", names(), ids=str)
    def test_a_hostile_name_produces_artifacts_only_inside_the_output_directory(
        self, name: CorpusCase, tmp_path: Path
    ) -> None:
        enclosure = tmp_path / name.id
        output = enclosure / "out"

        _write(output, name.value, name.value)

        written = [f for f in enclosure.rglob("*") if f.is_file()]
        assert written, f"{name.id} wrote nothing, so nothing was checked"
        for file in written:
            assert file.resolve().is_relative_to(output.resolve()), f"{name.id}: {name.description}"


class TestNoComponentExceedsTheFilesystemLimit:
    @pytest.mark.parametrize("name", names(), ids=str)
    def test_no_path_component_a_hostile_name_produces_exceeds_the_filesystem_limit(
        self, name: CorpusCase, tmp_path: Path
    ) -> None:
        _assert_components_fit(tmp_path, trace_file(tmp_path, name.value, "m"), name)
        _assert_components_fit(tmp_path, trace_file(tmp_path, "cls", name.value), name)


def _assert_components_fit(base: Path, resolved: Path, name: CorpusCase) -> None:
    for component in resolved.relative_to(base).parts:
        assert len(component.encode("utf-8")) <= _MAX_COMPONENT_BYTES, (
            f"{name.id}: component {component!r} must fit a filesystem path element"
        )


class TestLongNamesDisambiguate:
    """Truncation without disambiguation is a silent overwrite: two 300-character names sharing
    their first 240 characters would land on one artifact, and one test's approved baseline
    would then judge another test's trace."""

    def test_names_that_differ_only_past_the_limit_still_resolve_to_different_artifacts(
        self, tmp_path: Path
    ) -> None:
        seen: dict[Path, str] = {}
        for name in names():
            if not name.id.startswith("long-"):
                continue
            file = trace_file(tmp_path, "cls", name.value + name.id)
            assert file not in seen, f"{name.id} collides with {seen.get(file)} at {file.name}"
            seen[file] = name.id


class TestDeterministicResolution:
    @pytest.mark.parametrize("name", names(), ids=str)
    def test_resolving_the_same_name_twice_always_gives_the_same_path(
        self, name: CorpusCase, tmp_path: Path
    ) -> None:
        assert trace_file(tmp_path, name.value, name.value) == trace_file(
            tmp_path, name.value, name.value
        )
