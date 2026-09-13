# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``config.output-env`` — ``NARRATIVETRACE_OUTPUT``, if set, should spell a value the pytest
plugin actually recognizes as truthy or falsy, so a typo does not silently flip the setting.

Mirrors :data:`narrativetrace_pytest.plugin._TRUTHY`/its docstring's falsy spellings without
importing that package (the core distribution stays dependency-free and never depends on an
integration) — a genuine drift between the two copies would only ever make this check MORE
permissive, never mask a real trap, and is caught the moment either copy's tests change without
the other (this module's own test asserts the mirrored set matches the plugin's).
"""

from __future__ import annotations

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding

ID = "config.output-env"

TRUTHY = frozenset({"1", "true", "yes", "on"})
FALSY = frozenset({"0", "false", "no", "off"})


def check_output_env(snapshot: DoctorSnapshot) -> Finding:
    raw = snapshot.env.get("NARRATIVETRACE_OUTPUT")
    if raw is None:
        return passed(
            ID,
            "NARRATIVETRACE_OUTPUT is not set — output stays on its default (on)",
            DOC["where_settings_come_from"],
        )
    normalized = raw.strip().lower()
    if normalized in TRUTHY:
        return passed(
            ID, f"NARRATIVETRACE_OUTPUT={raw!r} — output is on", DOC["where_settings_come_from"]
        )
    if normalized in FALSY:
        return passed(
            ID, f"NARRATIVETRACE_OUTPUT={raw!r} — output is off", DOC["where_settings_come_from"]
        )
    return failed(
        ID,
        f"NARRATIVETRACE_OUTPUT is set to {raw!r}, which is neither a recognized truthy "
        f"({sorted(TRUTHY)}) nor falsy ({sorted(FALSY)}) spelling",
        "Anything outside the recognized truthy spellings reads as OFF — set NARRATIVETRACE_OUTPUT "
        "to one of true/1/yes/on (or false/0/no/off, or unset it) so the value means what you "
        "intend.",
        DOC["where_settings_come_from"],
    )
