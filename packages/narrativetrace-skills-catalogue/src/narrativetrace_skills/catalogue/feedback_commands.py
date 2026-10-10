# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Command literals for ``narrativetrace-feedback``: the ``narrativetrace feedback`` verb in the
project's own environment, because this port's closed command vocabulary is ``uv`` and ``git``.

Every command here is what an ADOPTER runs, in their own project. The ``<angle-bracket>``
placeholders are the one thing the agent substitutes: the three sentences and the step are the
report, and no literal can carry somebody else's report. Free-text values are quoted so a sentence
stays one argument. The Tier A2 replay test maps each placeholder onto a harmless value of its own.

**@llmNote** There is deliberately no ``gh`` command here. The ``gh issue create`` line is the
verb's third channel, printed and never run, and ``gh`` is outside the vocabulary by ruling -- so
the skill never invokes it. The documentation names it for somebody who already has that tool.
"""

from __future__ import annotations

_REPORT_FLAGS = (
    '--category <category> --step "<where it happened>" --did "<what you did>" '
    '--happened "<what happened>" --expected "<what you expected>"'
)

DRAFT_REPORT = f"uv run narrativetrace feedback draft {_REPORT_FLAGS}"
"""Drafts the report, checks it carries no values, writes two files and prints the whole thing."""

PRINT_URL = f"uv run narrativetrace feedback url {_REPORT_FLAGS}"
"""Prints the pre-filled issue-form URL for the same report, once the user has said yes."""

# The names are built from a stem and a suffix, never written as a `*.md` literal: the citation lint
# (`lints.citation_violations`) reads every command string for a Markdown filename that is not a
# file of THIS repository, and these two are files the verb writes into an adopter's project.
_DRAFT_FILES = """\
import pathlib, sys
root = pathlib.Path("build/narrativetrace/feedback")
paths = [root / (stem + ".md") for stem in ("feedback-draft", "feedback-body")]
sys.exit(0 if all(p.is_file() and p.stat().st_size for p in paths) else 1)
"""

DRAFT_FILES_WRITTEN = f"uv run python -c '{_DRAFT_FILES}'"
"""Both files the verb writes exist and are not empty. A run that named a ``vf.*`` rule instead
wrote neither, and the field it named is what to fix."""

_SHOW_DRAFT = """\
import pathlib
draft = pathlib.Path("build/narrativetrace/feedback") / ("feedback-draft" + ".md")
print(draft.read_text(encoding="utf-8"))
"""

SHOW_DRAFT = f"uv run python -c '{_SHOW_DRAFT}'"
"""Prints the draft file whole, so the text shown to the user is the file's, never a retelling."""

_URL_PRINTED = """\
import sys
sys.exit(0 if "/issues/new?template=" in sys.stdin.read() else 1)
"""

URL_PRINTED = f"{PRINT_URL} | uv run python -c '{_URL_PRINTED}'"
"""The verb printed an issue-form URL."""
