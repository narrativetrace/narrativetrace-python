# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``trap.silent-sink`` — Python's own instance of the silent-sink genre: a redaction marker
present in the source but silently doing nothing. Two supported surfaces
(:mod:`narrativetrace.markers`), two ways this happens:

* ``not_traced_field`` imported from ``narrativetrace`` but never actually called to build a
  dataclass field — the marker exists in the import list, protects nothing.
* ``__nt_not_traced__`` declared as a class attribute but with an EMPTY collection — present,
  syntactically valid, and redacts zero fields.

A source that imports the runtime's own redaction primitives and never calls them reads as
"redaction is handled" while nothing is actually redacted."""

from __future__ import annotations

import re

from narrativetrace.doctor.doc_urls import DOC
from narrativetrace.doctor.finding import failed, passed
from narrativetrace.doctor.types import DoctorSnapshot, Finding

ID = "trap.silent-sink"

_IMPORTS_NOT_TRACED_FIELD = re.compile(r"\bimport\b[^\n]*\bnot_traced_field\b")
_CALLS_NOT_TRACED_FIELD = re.compile(r"\bnot_traced_field\s*\(")
_EMPTY_MARKER_ATTR = re.compile(r"__nt_not_traced__\s*=\s*(\(\s*\)|\[\s*\]|set\(\s*\))")


def _unused_field_import(content: str) -> bool:
    return bool(_IMPORTS_NOT_TRACED_FIELD.search(content)) and not _CALLS_NOT_TRACED_FIELD.search(
        content
    )


def _offending_file(snapshot: DoctorSnapshot) -> tuple[str, str] | None:
    for path, content in snapshot.source_files.items():
        if not path.endswith(".py"):
            continue
        if _unused_field_import(content):
            return path, "not_traced_field is imported but never called"
        empty_marker = _EMPTY_MARKER_ATTR.search(content)
        if empty_marker:
            return path, "__nt_not_traced__ is declared but lists no fields"
    return None


def check_not_traced_unused(snapshot: DoctorSnapshot) -> Finding:
    offender = _offending_file(snapshot)
    if offender is None:
        message = "no imported-but-unused not_traced_field/__nt_not_traced__ marker found"
        return passed(ID, message, DOC["redaction_surface_by_surface"])
    path, reason = offender
    return failed(
        ID,
        f"{path}: {reason}",
        "A redaction marker that is present but never applied protects nothing — either call "
        "not_traced_field(...) on a real field or list real field names in __nt_not_traced__, or "
        "remove the unused marker so it stops reading as handled.",
        DOC["redaction_surface_by_surface"],
    )
