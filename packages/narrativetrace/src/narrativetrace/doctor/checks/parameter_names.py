# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``trap.parameter-names`` — a ``*args`` method's parameters collapse into one ``args: [...]``
value (Troubleshooting: "A `*args` method's parameters show as one `args: [...]` value"):
``inspect.Signature.bind`` has nothing named to reconstruct per-argument that Python itself does
not have. Doctor reads already-rendered output, if any exists, and flags the tell-tale
``args: [`` capture rather than guessing from source — the same "read the artifact, don't guess"
stance the TypeScript runtime's ``parameter-arg0`` check takes."""

from __future__ import annotations

import re

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding

ID = "trap.parameter-names"
_COLLAPSED_ARGS = re.compile(r"\bargs: \[")
_FIX = (
    'Supply explicit names: @traced("first", "second", ...) above the method — required whenever '
    "a signature binds to *args with no per-argument names to read."
)


def check_parameter_names(snapshot: DoctorSnapshot) -> Finding:
    if not snapshot.output_files:
        message = "no rendered output found yet — run your tests or app once to check this"
        return passed(ID, message, DOC["parameter_names"])
    offender = next(
        (
            path
            for path, content in snapshot.output_files.items()
            if _COLLAPSED_ARGS.search(content)
        ),
        None,
    )
    if offender is None:
        message = (
            "rendered output carries real parameter names — no collapsed args: [...] capture found"
        )
        return passed(ID, message, DOC["parameter_names"])
    message = f"rendered output shows a collapsed args: [...] capture (first seen in {offender})"
    return failed(ID, message, _FIX, DOC["parameter_names"])
