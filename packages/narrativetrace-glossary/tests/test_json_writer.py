# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Byte-level contract of the deterministic ``glossary.json`` writer."""

from __future__ import annotations

import json
from datetime import date

import pytest
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    SynonymAlias,
    TermKind,
    TermStatus,
    write_glossary_json,
)

FIRST_SEEN = date(2026, 8, 11)


def bare_term(text: str, context: str = "billing") -> GlossaryTerm:
    return GlossaryTerm(text, context, TermKind.WORD, TermStatus.HARVESTED, first_seen=FIRST_SEEN)


def test_a_populated_glossary_renders_the_canonical_document(
    populated_glossary: Glossary, canonical_document: str
) -> None:
    assert write_glossary_json(populated_glossary) == canonical_document


def test_an_empty_glossary_renders_empty_containers_not_omitted_keys() -> None:
    assert write_glossary_json(Glossary()) == (
        '{\n  "schemaVersion": 1,\n  "contexts": {},\n  "terms": []\n}\n'
    )


def test_declared_abbreviations_are_stamped_schema_two_and_rendered_sorted() -> None:
    glossary = Glossary(abbreviations={"fx": "foreign exchange", "calc": "calculate"})

    assert write_glossary_json(glossary) == (
        '{\n  "schemaVersion": 2,\n  "contexts": {},\n'
        '  "abbreviations": {\n'
        '    "calc": "calculate",\n'
        '    "fx": "foreign exchange"\n'
        "  },\n"
        '  "terms": []\n}\n'
    )


def test_a_glossary_without_abbreviations_omits_the_section_and_stays_schema_one() -> None:
    """The anti-churn rule: a repository that never declared shorthand writes the same bytes."""
    without = Glossary({"billing": BoundedContext("billing")}, [bare_term("invoice")])

    rendered = write_glossary_json(without)

    assert "abbreviations" not in rendered
    assert '"schemaVersion": 1' in rendered


def test_an_empty_abbreviations_map_is_indistinguishable_from_none_declared() -> None:
    assert write_glossary_json(Glossary(abbreviations={})) == write_glossary_json(Glossary())


def test_the_document_is_parseable_json(populated_glossary: Glossary) -> None:
    parsed = json.loads(write_glossary_json(populated_glossary))

    assert parsed["terms"][0]["term"] == "overdraft account"
    assert parsed["contexts"]["billing"]["packages"] == ["acme.billing"]


def test_contexts_are_sorted_by_name_whatever_order_they_were_declared_in() -> None:
    declared = Glossary(
        {name: BoundedContext(name) for name in ("shipping", "billing", "_unassigned")}
    )

    rendered = [
        line
        for line in write_glossary_json(declared).splitlines()
        if line.startswith('    "') and line.endswith('": {')
    ]

    assert rendered == ['    "_unassigned": {', '    "billing": {', '    "shipping": {']


def test_translations_are_sorted_by_locale_whatever_order_they_were_supplied_in() -> None:
    term = GlossaryTerm(
        "invoice",
        "billing",
        TermKind.WORD,
        TermStatus.CURATED,
        translations={"pt": "fatura", "es": "factura", "de": "Rechnung"},
        first_seen=FIRST_SEEN,
    )

    document = write_glossary_json(Glossary({"billing": BoundedContext("billing")}, [term]))

    assert '"de": "Rechnung",\n        "es": "factura",\n        "pt": "fatura"' in document


def test_optional_and_empty_fields_are_omitted_entirely() -> None:
    document = write_glossary_json(
        Glossary({"billing": BoundedContext("billing")}, [bare_term("invoice")])
    )

    for omitted in ("description", "definition", "translations", "synonyms", "sources"):
        assert omitted not in document


def test_a_synonym_without_a_note_renders_only_its_alias() -> None:
    term = GlossaryTerm(
        "overdraft account",
        "billing",
        TermKind.NOUN_PHRASE,
        TermStatus.CURATED,
        synonyms=[SynonymAlias("account with overdraft")],
        first_seen=FIRST_SEEN,
    )

    document = write_glossary_json(Glossary({"billing": BoundedContext("billing")}, [term]))

    assert '        { "alias": "account with overdraft" }\n' in document


def test_text_that_would_break_the_document_is_escaped() -> None:
    term = GlossaryTerm(
        "invoice",
        "billing",
        TermKind.WORD,
        TermStatus.CURATED,
        'a "quote", a \\ backslash,\na newline\tand \x01 control',
        first_seen=FIRST_SEEN,
    )

    document = write_glossary_json(Glossary({"billing": BoundedContext("billing")}, [term]))

    escaped = '"a \\"quote\\", a \\\\ backslash,\\na newline\\tand \\u0001 control"'
    assert f'"definition": {escaped}' in document
    assert json.loads(document)["terms"][0]["definition"].endswith("\x01 control")


def test_non_ascii_text_stays_readable_rather_than_being_escaped() -> None:
    term = GlossaryTerm(
        "envío",
        "shipping",
        TermKind.WORD,
        TermStatus.CURATED,
        translations={"zh-CN": "发货"},
        first_seen=FIRST_SEEN,
    )

    document = write_glossary_json(Glossary({"shipping": BoundedContext("shipping")}, [term]))

    assert '"term": "envío"' in document
    assert '"zh-CN": "发货"' in document


def test_the_document_always_ends_with_exactly_one_trailing_newline(
    populated_glossary: Glossary,
) -> None:
    document = write_glossary_json(populated_glossary)

    assert document.endswith("}\n")
    assert not document.endswith("\n\n")


def test_writing_rejects_a_missing_glossary() -> None:
    with pytest.raises(TypeError, match=r"\Aglossary must be a Glossary\Z"):
        write_glossary_json(None)  # type: ignore[arg-type]
