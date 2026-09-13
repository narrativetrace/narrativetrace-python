# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``trap.approval-traces`` — a ``.received.nt`` sitting in the approved directory is a
reviewed-but-not-yet-resolved diff: ``documentation/what-to-commit.md`` warns never to commit one,
and exactly what a doctor run should surface before someone else does."""

from __future__ import annotations

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding

ID = "trap.approval-traces"
_FIX = (
    "Review each .received.nt diff against its .approved.nt baseline, then run `uv run poe "
    "approve` (or narrativetrace-approve) to promote it, or delete it if the change was wrong — "
    "never commit a .received.nt file."
)


def check_approval_traces(snapshot: DoctorSnapshot) -> Finding:
    paths = list(snapshot.approved_dir_files)
    if not paths:
        return passed(
            ID,
            "no approval traces configured yet — nothing to check",
            DOC["approval_traces_end_to_end"],
        )
    received = sorted(path for path in paths if path.endswith(".received.nt"))
    if received:
        message = f"{len(received)} stale received trace(s) found: {', '.join(received)}"
        return failed(ID, message, _FIX, DOC["approval_traces_end_to_end"])
    approved = [path for path in paths if path.endswith(".approved.nt")]
    message = f"{len(approved)} approved trace(s) found, no pending received diffs"
    return passed(ID, message, DOC["approval_traces_end_to_end"])
