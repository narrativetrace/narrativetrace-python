# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests behind documentation/guides/decorators.md's `__nt_not_traced__` / `not_traced_field`
example: proves both redaction surfaces actually redact, from a real traced run."""

from __future__ import annotations

from pathlib import Path

from examples.not_traced_fields import run, write_artifact

_BUILD_ARTIFACT = Path(__file__).parent / "build" / "not_traced_fields.txt"


def test_both_surfaces_redact_their_secret_field() -> None:
    rendered = run()
    assert rendered.count("[REDACTED]") == 2
    assert "hunter2" not in rendered


def test_the_non_redacted_field_still_renders() -> None:
    """The `secret` field is hidden; the sibling `username` field is not -- proves the redaction
    is per-field, not a blanket redaction of the whole composite parameter."""
    rendered = run()
    assert 'username="alice"' in rendered
    assert 'username="bob"' in rendered


def _without_trace_header(rendered: str) -> str:
    """Strips the leading `trace: <phrase> (<id>)` header (2026-09-13 ruling, item 4): each call
    to :func:`run` adopts no fixed trace id, so it names a genuinely different, random trace every
    time -- the header is exactly the one thing two otherwise-identical calls must differ on."""
    boundary = rendered.index("\n\n")
    return rendered[boundary + 2 :]


def test_write_artifact_saves_the_same_content_it_returns() -> None:
    """The build artifact `scripts/snippet_check.py` embeds into decorators.md is exactly what
    a reader running this file for themselves would see -- but for the trace header, which names
    a fresh random trace on every call (`mask=traceName` on the page's own embed)."""
    saved = write_artifact()
    assert _BUILD_ARTIFACT.read_text(encoding="utf-8") == saved
    assert _without_trace_header(saved) == _without_trace_header(run())
