# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Best-effort per-trace file writer for the live translated stream."""

from __future__ import annotations

import io
from pathlib import Path

from narrativetrace_glossary.translation_file_sink import TranslationFileSink


def test_writes_one_file_per_trace(tmp_path: Path) -> None:
    sink = TranslationFileSink(tmp_path)

    sink.write("trace-1", "line one\n")
    sink.write("trace-2", "other trace\n")

    assert (tmp_path / "trace-1.md").read_text(encoding="utf-8") == "line one\n"
    assert (tmp_path / "trace-2.md").read_text(encoding="utf-8") == "other trace\n"


def test_appends_multiple_writes_to_the_same_trace(tmp_path: Path) -> None:
    sink = TranslationFileSink(tmp_path)

    sink.write("trace-1", "first\n")
    sink.write("trace-1", "second\n")

    assert (tmp_path / "trace-1.md").read_text(encoding="utf-8") == "first\nsecond\n"


def test_creates_missing_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "nested" / "dir"
    sink = TranslationFileSink(output_dir)

    sink.write("trace-1", "x\n")

    assert output_dir.is_dir()


def test_a_write_failure_is_reported_once_then_dropped_silently(tmp_path: Path) -> None:
    # output_dir already exists as a *file*, so mkdir(parents=True, exist_ok=True) fails every time.
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    diagnostics = io.StringIO()
    sink = TranslationFileSink(blocked, diagnostics)

    sink.write("trace-1", "a\n")
    sink.write("trace-1", "b\n")

    output = diagnostics.getvalue()
    assert output.count("translated-trace write failed") == 1


def test_defaults_diagnostics_to_stderr_without_raising(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    sink = TranslationFileSink(blocked)

    sink.write("trace-1", "a\n")  # must not raise
