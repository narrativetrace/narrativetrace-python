# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Best-effort per-trace file writer for the live translated stream.

``TranslationFileSink``. One ``<traceId>.md`` per trace, appended one line at a time as
:class:`~narrativetrace_glossary.translation_subscriber.TranslationSubscriber` renders it.
Best-effort by design, matching the pipeline's own dual-path guarantee
(:mod:`narrativetrace.pipeline.dual_path`): a write failure is reported once, then dropped
silently — a full disk or an unwritable directory must never crash the pipeline this only observes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO


class TranslationFileSink:
    """Writes one Markdown file per trace, appending each rendered line as it arrives.

    ``write`` matches the ``Callable[[str, str], None]`` shape
    :class:`~narrativetrace_glossary.translation_subscriber.TranslationSubscriber` expects as a
    sink, so ``TranslationFileSink(output_dir).write`` is itself a valid sink argument.
    """

    def __init__(self, output_dir: str | Path, diagnostics: TextIO | None = None) -> None:
        self._output_dir = Path(output_dir)
        self._diagnostics = diagnostics if diagnostics is not None else sys.stderr
        self._warned = False

    def write(self, trace_id: str, text: str) -> None:
        """Appends ``text`` to ``<trace_id>.md``, creating the directory/file on first use."""
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            with (self._output_dir / f"{trace_id}.md").open("a", encoding="utf-8") as handle:
                handle.write(text)
        except OSError as error:
            self._warn_once(error)

    def _warn_once(self, error: OSError) -> None:
        if self._warned:
            return
        self._warned = True
        print(
            f"narrative-trace: translated-trace write failed at {self._output_dir}, further "
            f"writes for this sink are dropped silently ({error})",
            file=self._diagnostics,
        )
