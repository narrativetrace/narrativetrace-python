# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The scenario → file index a suite run leaves beside its artifacts.

``ScenarioManifest`` (module-level functions, this port's idiom for a stateless formatter).
Artifact names are derived, not announced, so a reader who knows a scenario had to guess which
file holds it — and once a test method runs more than once, guessing stops working.
``manifest.json`` answers the question directly: one row per traced scenario, naming the test that
produced it, its invocation number when the method ran more than once, and every artifact it owns
as a path relative to the output directory.

Rows appear in suite execution order and paths always use ``/``, so the file diffs cleanly and
reads the same on every platform. The listing is what is actually on disk: an artifact a format or
a flag did not produce is absent from the row rather than listed and missing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from narrativetrace.output.artifact_identity import ArtifactIdentity
from narrativetrace.output.paths import diagram_file_for, structural_file, trace_artifact
from narrativetrace.output.writer import write_text_artifact

FILE_NAME = "manifest.json"
_SCHEMA = "narrativetrace/scenario-manifest/1"

# The `traces` tree probed in listing order. The four rendering formats share the `trace` role --
# a run writes exactly one of them -- and the first that exists claims it.
_TRACE_ROLES = (
    ("trace", ".md"),
    ("trace", ".txt"),
    ("trace", ".mmd"),
    ("trace", ".puml"),
    ("json", ".json"),
    ("canonicalJson", ".canonical.json"),
)


@dataclass(frozen=True, slots=True)
class Entry:
    """One traced scenario's row.

    Args:
        scenario: the humanized scenario name, as the artifacts' own headers spell it.
        identity: which test invocation produced it.
        artifacts: role → path relative to the output directory, in listing order. Copied into a
            fresh ``dict`` at construction so a row cannot change after the run that recorded it.
    """

    scenario: str
    identity: ArtifactIdentity
    artifacts: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", dict(self.artifacts))


def entry_for(output_dir: Path, identity: ArtifactIdentity, scenario: str) -> Entry:
    """Builds one scenario's row by probing the artifact layout for files that exist."""
    slug = identity.file_slug()
    class_name = identity.test_class_name
    artifacts: dict[str, str] = {}
    for role, suffix in _TRACE_ROLES:
        _put_if_present(
            artifacts, role, output_dir, trace_artifact(output_dir, class_name, slug, suffix)
        )
    _put_if_present(
        artifacts, "diagram", output_dir, diagram_file_for(output_dir, class_name, slug)
    )
    _put_if_present(
        artifacts, "structural", output_dir, structural_file(output_dir, class_name, slug)
    )
    return Entry(scenario, identity, artifacts)


def _put_if_present(artifacts: dict[str, str], role: str, output_dir: Path, file: Path) -> None:
    """Records a file that exists under its role, keeping the first path a role resolves to."""
    if role not in artifacts and file.is_file():
        artifacts[role] = _relative(output_dir, file)


def _relative(output_dir: Path, file: Path) -> str:
    """The path as the manifest states it: relative to the output directory, ``/``-separated."""
    return file.relative_to(output_dir).as_posix()


def write(entries: list[Entry], output_dir: Path) -> None:
    """Writes ``manifest.json``; writes nothing at all when the run traced no scenario."""
    if not entries:
        return
    write_text_artifact(render(entries), output_dir / FILE_NAME)


def render(entries: list[Entry]) -> str:
    """The manifest document, rendered."""
    document = {"schema": _SCHEMA, "scenarios": [_entry_dict(entry) for entry in entries]}
    return json.dumps(document, indent=2) + "\n"


def _entry_dict(entry: Entry) -> dict[str, object]:
    identity = entry.identity
    row: dict[str, object] = {
        "scenario": entry.scenario,
        "testClass": identity.test_class_name,
        "testMethod": identity.method_name,
    }
    if identity.is_invocation:
        row["invocation"] = identity.invocation_index
    row["artifacts"] = dict(entry.artifacts)
    return row
