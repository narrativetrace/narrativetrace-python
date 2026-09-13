# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``trap.redaction-proof`` — redaction is a security property; the trap named across every study
is trusting it by inspection rather than proving it in a test. This looks for a test file that
actually asserts the literal ``[REDACTED]`` marker."""

from __future__ import annotations

import re

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding

ID = "trap.redaction-proof"
_TEST_FILE = re.compile(r"(^|/)test_[^/]+\.py$|(^|/)[^/]+_test\.py$")
_REDACTED_ASSERTION = re.compile(r"\[REDACTED\]")


def check_redaction_proof(snapshot: DoctorSnapshot) -> Finding:
    test_files = (
        content for path, content in snapshot.source_files.items() if _TEST_FILE.search(path)
    )
    proven = any(_REDACTED_ASSERTION.search(content) for content in test_files)
    if proven:
        return passed(
            ID,
            "a test asserts [REDACTED] for a deny-listed parameter name",
            DOC["redaction_surface_by_surface"],
        )
    return failed(
        ID,
        "no test asserts [REDACTED] — redaction is unproven",
        'Render a call with a deny-listed parameter name (e.g. "password", "token") in a test and '
        'assert the output contains "[REDACTED]" — and that a neighboring, non-sensitive value is '
        "still present, so an over-broad redaction also fails.",
        DOC["redaction_surface_by_surface"],
    )
