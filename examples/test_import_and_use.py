# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests behind documentation/privacy-and-redaction.md's and
documentation/guides/decorators.md's "you imported this — apply it like this" block: proves the
minimal `@narrated` + `@not_traced` pairing actually narrates and actually redacts, from a real
traced run -- the same assertion the doctor's `trap.redaction-proof` check looks for in a project's
own tests."""

from __future__ import annotations

from pathlib import Path

from examples.import_and_use import run, write_artifact

_BUILD_ARTIFACT = Path(__file__).parent / "build" / "import_and_use.txt"


def test_the_password_is_redacted() -> None:
    rendered = run()
    assert "[REDACTED]" in rendered
    assert "hunter2" not in rendered


def test_the_narration_still_names_the_non_redacted_argument() -> None:
    """The narration template names both parameters; only the deny-listed one is hidden -- proves
    redaction reaches the narration layer without silencing the whole sentence."""
    rendered = run()
    assert "login attempt for alice with [REDACTED]" in rendered


def _without_trace_header(rendered: str) -> str:
    """Strips the leading `The trace <phrase>:` header: each call to :func:`run` adopts no fixed
    trace id, so it names a genuinely different, random trace every time (see
    examples/not_traced_fields.py's own `_without_trace_header` for the identical reasoning)."""
    boundary = rendered.index("\n\n")
    return rendered[boundary + 2 :]


def test_write_artifact_saves_the_same_content_it_returns() -> None:
    """The build artifact `scripts/snippet_check.py` embeds is exactly what a reader running this
    file for themselves would see -- but for the trace header, which names a fresh random trace on
    every call (`mask=traceName` on the page's own embed)."""
    saved = write_artifact()
    assert _BUILD_ARTIFACT.read_text(encoding="utf-8") == saved
    assert _without_trace_header(saved) == _without_trace_header(run())
