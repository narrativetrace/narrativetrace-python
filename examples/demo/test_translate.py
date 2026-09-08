# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the translated-demo-run machinery: glossary loading and per-scenario rendering."""

from __future__ import annotations

from datetime import date

from narrativetrace_glossary import BoundedContext, Glossary, GlossaryTerm, TermKind, TermStatus

from examples.demo.launcher import load_example
from examples.demo.translate import (
    declared_locales,
    example_directory,
    load_example_glossary,
    menu_locales,
    record_scenarios,
    render_translated_scenarios,
    translated_lines,
)
from examples.tour import Scenario
from narrativetrace.tree import TraceTree


def test_example_directory_points_at_the_examples_package() -> None:
    directory = example_directory("ecommerce")

    assert directory.name == "ecommerce"
    assert (directory / "ecommerce.py").is_file()


def test_load_example_glossary_returns_none_for_an_example_with_no_committed_glossary() -> None:
    # fastapi_service is a real example directory but is not part of the demo picker and has no
    # committed glossary.json.
    assert load_example_glossary("fastapi_service") is None


def test_load_example_glossary_reads_the_committed_ecommerce_glossary() -> None:
    glossary = load_example_glossary("ecommerce")

    assert glossary is not None
    assert "shop" in glossary.contexts


def test_declared_locales_restricted_to_shipped_scaffolding() -> None:
    glossary = Glossary(
        {"x": BoundedContext("x")},
        [
            GlossaryTerm(
                "a",
                "x",
                TermKind.WORD,
                TermStatus.CURATED,
                translations={"es": "a", "fr": "a"},  # "fr" has no shipped scaffolding
                first_seen=date(2026, 8, 11),
            )
        ],
    )

    assert declared_locales(glossary) == frozenset({"es"})


def test_declared_locales_empty_for_a_glossary_with_no_translations() -> None:
    assert declared_locales(Glossary()) == frozenset()


def test_ecommerce_glossary_declares_both_es_and_zh_cn() -> None:
    glossary = load_example_glossary("ecommerce")
    assert glossary is not None

    assert declared_locales(glossary) == frozenset({"es", "zh-CN"})


def test_menu_locales_puts_en_first_then_follows_supported_locales_order() -> None:
    glossary = Glossary(
        {"x": BoundedContext("x")},
        [
            GlossaryTerm(
                "a",
                "x",
                TermKind.WORD,
                TermStatus.CURATED,
                translations={"zh-CN": "a", "es": "a"},  # declared out of order on purpose
                first_seen=date(2026, 8, 11),
            )
        ],
    )

    assert menu_locales(glossary) == ["en", "es", "zh-CN"]


def test_menu_locales_is_en_only_for_a_glossary_with_no_translations() -> None:
    assert menu_locales(Glossary()) == ["en"]


def test_ecommerce_menu_locales_offers_all_three() -> None:
    glossary = load_example_glossary("ecommerce")
    assert glossary is not None

    assert menu_locales(glossary) == ["en", "es", "zh-CN"]


def test_hotel_booking_menu_locales_offers_en_and_es_only() -> None:
    # hotel_booking's committed glossary has es translations only, not zh-CN (item 6's done log).
    glossary = load_example_glossary("hotel_booking")
    assert glossary is not None

    assert menu_locales(glossary) == ["en", "es"]


def test_record_scenarios_captures_every_scenario_with_a_non_empty_tree() -> None:
    example = load_example("library")

    recorded = record_scenarios(example)

    assert len(recorded) == len(example.scenarios())
    assert all(not tree.is_empty for _, tree in recorded)


def test_render_translated_scenarios_produces_one_rendering_per_scenario() -> None:
    example = load_example("ecommerce")
    glossary = load_example_glossary("ecommerce")
    assert glossary is not None

    rendered = render_translated_scenarios(example, glossary, "es")

    assert len(rendered) == len(example.scenarios())
    titles = [scenario.title for scenario, _ in rendered]
    assert titles == [s.title for s in example.scenarios()]


def test_render_translated_scenarios_glosses_identifiers_and_keeps_values() -> None:
    example = load_example("ecommerce")
    glossary = load_example_glossary("ecommerce")
    assert glossary is not None

    rendered = render_translated_scenarios(example, glossary, "es")

    joined = "\n".join(text for _, text in rendered)
    assert "realizar pedido" in joined  # place_order, curated
    assert "C-1234" in joined  # a parameter value, byte-identical


def _empty_scenario(title: str) -> Scenario:
    return Scenario(
        title, "Wiring: none — this scenario is never run.", lambda _context: TraceTree([])
    )


def test_translated_lines_headers_each_scenario_and_separates_them() -> None:
    rendered = [
        (_empty_scenario("One"), "line a\nline b"),
        (_empty_scenario("Two"), "line c"),
    ]

    lines = translated_lines(rendered)

    assert lines == [
        "=== One ===",
        "",
        "line a",
        "line b",
        "",
        "=== Two ===",
        "",
        "line c",
    ]
