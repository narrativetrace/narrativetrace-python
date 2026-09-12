# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Approval mode (ADR-002): a committed approved trace is the behavioral contract, and a run
whose structure differs fails with a readable diff.

The value-free ``.nt`` artifact's own approval workflow — the approval-testing idea, applied to
traces. A mismatch writes the current render as a received trace beside the approved one for
review, and approving is promoting the received trace over the approved one. Byte comparison
only: :class:`~narrativetrace.render.structural.StructuralTraceRenderer` is deterministic, so
byte-identical is behaviorally identical. Anything smarter (semantic diff, review workflow) is
deliberately out of scope here.
"""

from __future__ import annotations

from pathlib import Path

from narrativetrace.loss import TraceLoss
from narrativetrace.output import line_diff
from narrativetrace.output.artifact_identity import ArtifactIdentity
from narrativetrace.output.paths import class_directory
from narrativetrace.output.structural_delta import StructuralDelta
from narrativetrace.output.writer import write_text_artifact
from narrativetrace.render.structural import StructuralTraceRenderer
from narrativetrace.tree import TraceTree

_APPROVED_SUFFIX = ".approved.nt"
_RECEIVED_SUFFIX = ".received.nt"
_INCOMPLETE_SUFFIX = ".incomplete.nt"

_APPROVE_HINT = "approve it (run `uv run poe approve` or `narrativetrace-approve`)"


def approved_file(approved_dir: Path, identity: ArtifactIdentity) -> Path:
    """The committed approved trace's location for one test invocation:
    ``<approved_dir>/<SimpleClassName>/<slug>.approved.nt`` — the same class-directory and slug
    rules as every other per-test artifact, so the approved trace and the build artifact line up
    by name."""
    return (
        class_directory(approved_dir, identity.test_class_name)
        / f"{identity.file_slug()}{_APPROVED_SUFFIX}"
    )


def _received_sibling(path: Path) -> Path:
    return path.with_name(path.name.replace(_APPROVED_SUFFIX, _RECEIVED_SUFFIX))


def _incomplete_sibling(path: Path) -> Path:
    """Where a lossy run's structure goes: readable, comparable by hand, and never promotable."""
    return path.with_name(path.name.replace(_APPROVED_SUFFIX, _INCOMPLETE_SUFFIX))


def verify(
    tree: TraceTree, scenario: str, approved_path: Path, loss: TraceLoss | None = None
) -> str:
    """Verifies the scenario's structure against its committed approved trace.

    Raises:
        AssertionError: no approved trace exists yet (the current render is written as the
            received trace to review and approve), or the structure differs from it (a received
            trace is written, and the message carries the readable diff).

    Returns:
        A note to surface for a lossy pass ("consistent with baseline, ..."), empty when the run
        was clean and matched exactly. A lossy pass is weaker evidence than an exact match and
        must not be reported as "unchanged".
    """
    loss = loss if loss is not None else TraceLoss.none()
    current = StructuralTraceRenderer().render_document(tree, scenario)
    received_path = (
        _incomplete_sibling(approved_path) if loss.any() else _received_sibling(approved_path)
    )
    if not approved_path.is_file():
        write_text_artifact(current, received_path)
        raise AssertionError(_no_baseline_message(scenario, received_path, loss))
    baseline = approved_path.read_text(encoding="utf-8")
    if loss.any():
        return _verify_lossy(baseline, current, received_path, loss)
    delta = StructuralDelta(baseline, current)
    if not delta.unchanged:
        write_text_artifact(current, received_path)
        raise AssertionError(_changed_message(delta, received_path))
    received_path.unlink(missing_ok=True)
    return ""


def _no_baseline_message(scenario: str, received_path: Path, loss: TraceLoss) -> str:
    header = f'No approved trace for scenario "{scenario}".'
    if loss.any():
        return (
            f"{header}\nThis run was incomplete ({_describe(loss)}), so its structure was "
            f"written to {received_path} and is deliberately not promotable — rerun to record "
            "a baseline."
        )
    approved_name = received_path.name.replace(_RECEIVED_SUFFIX, _APPROVED_SUFFIX)
    return (
        f"{header}\nReceived: {received_path}\nReview it and {_APPROVE_HINT}, or rename it to "
        f"{approved_name}."
    )


def _changed_message(delta: StructuralDelta, received_path: Path) -> str:
    return (
        f"Structure changed against the approved trace ({delta.summary()}):\n{delta.diff()}"
        f"Received: {received_path}\nIf this change is intended, {_APPROVE_HINT}."
    )


def _verify_lossy(baseline: str, current: str, incomplete_path: Path, loss: TraceLoss) -> str:
    """Subsequence containment: the run may be short, but everything in it must be in the
    baseline."""
    if line_diff.is_subsequence(baseline, current):
        incomplete_path.unlink(missing_ok=True)
        return f"consistent with baseline, but this run was incomplete ({_describe(loss)})"
    write_text_artifact(current, incomplete_path)
    raise AssertionError(
        "Structure changed against the approved trace in a way loss cannot explain:\n"
        f"{line_diff.unified(baseline, current)}"
        f"This run was also incomplete ({_describe(loss)}), so its structure was written to "
        f"{incomplete_path} and is not promotable — fix or rerun, then approve a complete run."
    )


def _describe(loss: TraceLoss) -> str:
    """Human phrasing of what a run lost, for messages that must not read as behaviour change."""
    parts = []
    if loss.dropped_events > 0:
        parts.append(f"{loss.dropped_events} events dropped")
    if loss.refused_scopes > 0:
        parts.append(f"{loss.refused_scopes} async scopes refused")
    return ", ".join(parts)


def promote_received(root: Path) -> list[Path]:
    """Promotes every received trace under ``root`` to its approved counterpart — the whole of
    approving: reviewed received traces become the new contract. Backs the ``approve`` task/
    console script.

    Returns:
        The approved files written, sorted by path; empty when there is nothing to promote or
        ``root`` does not exist yet.
    """
    if not root.is_dir():
        return []
    promoted = []
    for received in sorted(root.rglob(f"*{_RECEIVED_SUFFIX}")):
        approved = received.with_name(received.name.replace(_RECEIVED_SUFFIX, _APPROVED_SUFFIX))
        received.replace(approved)
        promoted.append(approved)
    return promoted
