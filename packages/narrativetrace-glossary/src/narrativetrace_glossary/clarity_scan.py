# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Glossary-aware entry point for the clarity gate — vocabulary-check defaults (prerequisite 5).

``GlossaryAwareClarityScannerMain``. INTENT: composes ``narrativetrace-clarity``'s CLI
with :func:`~narrativetrace_glossary.vocabulary.read_project_vocabulary` without either package
importing the other's internals — ``narrativetrace_clarity.cli.main`` takes the reader as a plain
callback (see its module docstring). The root ``clarity`` gate task runs *this* module, not
``narrativetrace-clarity`` directly, which is what makes glossary-aware scoring the actual default:
a project with no committed glossary degrades to the built-in dictionaries exactly as before,
silently and without a separate opt-in flag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from narrativetrace_clarity.cli import main as _clarity_main

from narrativetrace_glossary.vocabulary import read_project_vocabulary

if TYPE_CHECKING:
    from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Runs the clarity scan/gate with the repository's committed glossary as domain vocabulary."""
    return _clarity_main(argv, vocabulary_reader=read_project_vocabulary)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
