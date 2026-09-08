# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Translated demo runs: ``--lang es|zh-CN`` re-renders the same recorded scenarios.

Each example's committed ``glossary.json`` (when it has one) is what the launcher's ``--lang``
mode translates against: identifiers get glossed, values stay byte-identical, and untranslated
phrases land in a "glossary gaps" footer per scenario. Every NarrativeTrace runtime's demo
works this way — one in-process run, no second execution — using the same
:class:`~narrativetrace_glossary.translation_view.TraceTranslationView` a live subscriber would.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

from narrativetrace_glossary import Glossary, TraceTranslationView, read_glossary_json
from narrativetrace_glossary.scaffolding import SUPPORTED_LOCALES

from examples.tour import narrated_run, walk
from narrativetrace.tree_canonical import entries_from_tree

if TYPE_CHECKING:
    from collections.abc import Sequence

    from examples.demo.launcher import Example
    from examples.tour import Scenario
    from narrativetrace.tree import TraceTree

GLOSSARY_FILENAME = "glossary.json"
EXAMPLES_DIR = Path(__file__).resolve().parent.parent


def example_directory(name: str) -> Path:
    """The example's own source directory (``examples/<name>``), holding its ``glossary.json``."""
    return EXAMPLES_DIR / name


def load_example_glossary(name: str) -> Glossary | None:
    """Loads ``examples/<name>/glossary.json``, or ``None`` when the example has none committed."""
    path = example_directory(name) / GLOSSARY_FILENAME
    if not path.is_file():
        return None
    return read_glossary_json(path.read_text(encoding="utf-8"))


def declared_locales(glossary: Glossary) -> frozenset[str]:
    """Locales this glossary actually has term translations for, restricted to shipped scaffolding.

    A glossary can declare translations for a locale the renderer ships no scaffolding chrome
    for; that locale is not offered here, since "``--lang``" is a promise about the whole
    rendered page (scaffolding words included), not only the glossed identifiers.
    """
    locales: set[str] = set()
    for term in glossary.terms:
        locales.update(term.translations)
    return frozenset(locales) & set(SUPPORTED_LOCALES)


def menu_locales(glossary: Glossary) -> list[str]:
    """Locales to offer in the launcher's interactive language menu.

    ``en`` always counts as available (there is no translation for it to declare) and always
    comes first; the rest follow in :data:`SUPPORTED_LOCALES` order, restricted to the ones
    :func:`declared_locales` finds actually curated. A result of length 1 means "no real choice"
    — the caller shows no menu at all.
    """
    covered = declared_locales(glossary)
    return [locale for locale in SUPPORTED_LOCALES if locale == "en" or locale in covered]


def record_scenarios(example: Example) -> list[tuple[Scenario, TraceTree]]:
    """Runs every scenario once, live narration discarded, returning each captured trace.

    A silent :func:`~examples.tour.narrated_run` — the translated view renders from the captured
    :class:`~narrativetrace.tree.TraceTree`, never from the live ``→ ← !!`` text stream, so that
    stream is not needed here at all.
    """
    sink = io.StringIO()
    with narrated_run(sink) as context:
        return walk(example.scenarios(), sink, context)


def render_translated_scenarios(
    example: Example, glossary: Glossary, locale: str
) -> list[tuple[Scenario, str]]:
    """Renders every scenario's captured trace through ``glossary`` into ``locale``.

    One :class:`~narrativetrace_glossary.translation_view.TraceTranslationView` per call (a fresh
    render state per scenario — each scenario is its own independent trace, not a shared one).
    """
    view = TraceTranslationView(glossary)
    rendered: list[tuple[Scenario, str]] = []
    for scenario, tree in record_scenarios(example):
        entries = entries_from_tree(tree)
        rendered.append((scenario, view.render(entries, locale)))
    return rendered


def translated_lines(rendered: Sequence[tuple[Scenario, str]]) -> list[str]:
    """Flattens rendered scenarios into ``=== title ===``-headed lines.

    The shape :class:`~examples.demo.launcher.Presenter` (a line-based presenter) already walks.
    """
    lines: list[str] = []
    for index, (scenario, text) in enumerate(rendered):
        if index:
            lines.append("")  # matches examples.tour.walk's own between-scenario blank line
        lines.append(f"=== {scenario.title} ===")
        lines.append("")
        lines.extend(text.splitlines())
    return lines
