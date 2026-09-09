# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Strictness contract of the ``glossary.json`` reader.

The committed glossary is hand-curated, so a typo must fail loudly at load rather than be silently
dropped: unknown keys, wrong JSON types, bad enum labels and malformed dates are all errors.
"""

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
    read_glossary_json,
    write_glossary_json,
)
from narrativetrace_glossary.json_reader import _MAX_JSON_NESTING_DEPTH, _check_nesting_depth

MINIMAL_TERM: dict[str, object] = {
    "term": "invoice",
    "context": "billing",
    "kind": "word",
    "status": "harvested",
    "firstSeen": "2026-08-11",
}


def document(**overrides: object) -> str:
    body: dict[str, object] = {
        "schemaVersion": 1,
        "contexts": {"billing": {"packages": ["acme.billing"]}},
        "terms": [dict(MINIMAL_TERM)],
    }
    body.update(overrides)
    return json.dumps(body)


def with_term(**overrides: object) -> str:
    term = dict(MINIMAL_TERM)
    term.update(overrides)
    return document(terms=[term])


def test_the_canonical_document_reads_back_into_the_glossary_that_wrote_it(
    populated_glossary: Glossary, canonical_document: str
) -> None:
    assert read_glossary_json(canonical_document) == populated_glossary


def test_reading_and_writing_round_trip_byte_for_byte(canonical_document: str) -> None:
    assert write_glossary_json(read_glossary_json(canonical_document)) == canonical_document


def test_a_fully_populated_term_reads_every_human_owned_field(canonical_document: str) -> None:
    term = read_glossary_json(canonical_document).terms[0]

    assert term == GlossaryTerm(
        "overdraft account",
        "billing",
        TermKind.NOUN_PHRASE,
        TermStatus.CURATED,
        "Account permitted to go below zero up to an agreed limit.",
        {"es": "cuenta con descubierto"},
        [SynonymAlias("account with overdraft", "legacy v1 API phrasing")],
        ["acme.billing.overdraft_service.open_overdraft_account"],
        first_seen=date(2026, 8, 11),
    )


def test_a_context_without_a_description_reads_as_having_none() -> None:
    glossary = read_glossary_json(document(terms=[]))

    assert glossary.contexts == {"billing": BoundedContext("billing", ["acme.billing"])}


def test_absent_optional_term_fields_read_as_empty() -> None:
    term = read_glossary_json(document()).terms[0]

    assert (term.definition, term.translations, term.synonyms, term.sources) == (None, {}, (), ())


def test_an_explicit_null_optional_field_reads_as_absent() -> None:
    glossary = read_glossary_json(
        document(contexts={"billing": {"packages": [], "description": None}})
    )

    assert glossary.contexts["billing"].description is None


def test_malformed_json_is_rejected_with_a_glossary_specific_message() -> None:
    with pytest.raises(ValueError, match=r"\Amalformed glossary JSON: "):
        read_glossary_json("{not json")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[]", "document root must be a JSON object"),
        ('{"schemaVersion": 1, "contexts": [], "terms": []}', "contexts must be a JSON object"),
        ('{"schemaVersion": 1, "contexts": {}, "terms": {}}', "terms must be a JSON array"),
    ],
)
def test_a_container_of_the_wrong_json_type_is_rejected(text: str, expected: str) -> None:
    with pytest.raises(ValueError, match=rf"\A{expected}\Z"):
        read_glossary_json(text)


@pytest.mark.parametrize("version", [True, 1.5, "1"])
def test_a_schema_version_that_is_not_a_json_integer_is_rejected(version: object) -> None:
    with pytest.raises(ValueError, match=r"\AschemaVersion must be a JSON integer\Z"):
        read_glossary_json(document(schemaVersion=version))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (document(unexpected=1), "unknown key 'unexpected' in glossary"),
        (
            document(contexts={"billing": {"packages": [], "owner": "x"}}),
            "unknown key 'owner' in context 'billing'",
        ),
        (with_term(occurrences=3), "unknown key 'occurrences' in term"),
        (
            with_term(synonyms=[{"alias": "a", "reason": "b"}]),
            "unknown key 'reason' in synonym",
        ),
    ],
)
def test_an_unknown_key_is_rejected_wherever_it_appears(text: str, expected: str) -> None:
    with pytest.raises(ValueError, match=rf"\A{expected}\Z"):
        read_glossary_json(text)


@pytest.mark.parametrize("key", ["schemaVersion", "contexts", "terms"])
def test_a_missing_root_key_is_rejected(key: str) -> None:
    body = json.loads(document())
    del body[key]

    with pytest.raises(ValueError, match=rf"\Amissing required key '{key}'\Z"):
        read_glossary_json(json.dumps(body))


@pytest.mark.parametrize("key", ["term", "context", "kind", "status", "firstSeen"])
def test_a_missing_term_key_is_rejected(key: str) -> None:
    term = dict(MINIMAL_TERM)
    del term[key]

    with pytest.raises(ValueError, match=rf"\Amissing required key '{key}'\Z"):
        read_glossary_json(document(terms=[term]))


def test_an_explicit_null_required_key_is_rejected_as_missing() -> None:
    with pytest.raises(ValueError, match=r"\Amissing required key 'term'\Z"):
        read_glossary_json(with_term(term=None))


def test_a_context_missing_its_package_list_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\Amissing required key 'packages'\Z"):
        read_glossary_json(document(contexts={"billing": {}}))


def test_an_unknown_term_kind_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\Aunknown term kind 'phrase'\Z"):
        read_glossary_json(with_term(kind="phrase"))


def test_an_unknown_term_status_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\Aunknown term status 'reviewed'\Z"):
        read_glossary_json(with_term(status="reviewed"))


@pytest.mark.parametrize(
    "text",
    [
        "2026-13-01",
        "11/08/2026",
        "2026-08-11T10:00:00Z",
        "",
        pytest.param("20260811", id="basic-iso-form-python-would-otherwise-accept"),
        pytest.param("2026-W33-1", id="iso-week-date-python-would-otherwise-accept"),
    ],
)
def test_a_malformed_first_seen_date_is_rejected(text: str) -> None:
    with pytest.raises(ValueError, match=rf"\Ainvalid firstSeen date '{text}'\Z"):
        read_glossary_json(with_term(firstSeen=text))


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"term": 7}, "term must be a JSON string"),
        ({"context": 7}, "context must be a JSON string"),
        ({"kind": 7}, "kind must be a JSON string"),
        ({"status": 7}, "status must be a JSON string"),
        ({"firstSeen": 7}, "firstSeen must be a JSON string"),
        ({"definition": 7}, "definition must be a JSON string"),
        ({"sources": "acme.billing"}, "sources must be a JSON array"),
        ({"sources": [7]}, "sources element must be a JSON string"),
        ({"translations": []}, "translations must be a JSON object"),
        ({"translations": {"es": 7}}, "translation 'es' must be a JSON string"),
        ({"synonyms": {}}, "synonyms must be a JSON array"),
        ({"synonyms": ["account with overdraft"]}, "synonym entry must be a JSON object"),
        ({"synonyms": [{"alias": 7}]}, "alias must be a JSON string"),
        ({"synonyms": [{"alias": "a", "note": 7}]}, "note must be a JSON string"),
    ],
)
def test_a_term_field_of_the_wrong_json_type_is_rejected(
    overrides: dict[str, object], expected: str
) -> None:
    with pytest.raises(ValueError, match=rf"\A{expected}\Z"):
        read_glossary_json(with_term(**overrides))


def test_a_term_entry_that_is_not_an_object_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\Aterm entry must be a JSON object\Z"):
        read_glossary_json(document(terms=["invoice"]))


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (7, "context 'billing' must be a JSON object"),
        ({"packages": "acme.billing"}, "packages must be a JSON array"),
        ({"packages": [7]}, "packages element must be a JSON string"),
        ({"packages": [], "description": 7}, "description must be a JSON string"),
    ],
)
def test_a_context_field_of_the_wrong_json_type_is_rejected(body: object, expected: str) -> None:
    with pytest.raises(ValueError, match=rf"\A{expected}\Z"):
        read_glossary_json(document(contexts={"billing": body}, terms=[]))


def test_structural_violations_survive_the_reader() -> None:
    with pytest.raises(ValueError, match=r"\Aterm 'invoice' references undeclared context"):
        read_glossary_json(document(contexts={}))


def test_a_duplicate_term_in_the_file_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\Aduplicate term key: billing/invoice\Z"):
        read_glossary_json(document(terms=[dict(MINIMAL_TERM), dict(MINIMAL_TERM)]))


def test_a_glossary_of_a_future_schema_version_still_loads() -> None:
    assert read_glossary_json(document(schemaVersion=2)).schema_version == 2


def test_a_schema_two_file_reads_its_accepted_abbreviations() -> None:
    text = document(schemaVersion=2, abbreviations={"fx": "foreign exchange"})

    assert dict(read_glossary_json(text).abbreviations) == {"fx": "foreign exchange"}


def test_a_schema_one_file_without_the_section_still_reads() -> None:
    glossary = read_glossary_json(document())

    assert glossary.abbreviations == {}
    assert glossary.schema_version == 1


def test_the_section_is_accepted_on_a_file_still_stamped_schema_one() -> None:
    """Readers must not refuse an additive section — that would be a migration cliff."""
    glossary = read_glossary_json(document(schemaVersion=1, abbreviations={"calc": "calculate"}))

    assert dict(glossary.abbreviations) == {"calc": "calculate"}
    assert glossary.schema_version == 2


def test_an_abbreviations_section_that_is_not_an_object_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"\Aabbreviations must be a JSON object\Z"):
        read_glossary_json(document(abbreviations=["fx"]))


def test_a_non_string_expansion_is_rejected() -> None:
    with pytest.raises(
        ValueError, match=r"\Aexpansion of abbreviation 'fx' must be a JSON string\Z"
    ):
        read_glossary_json(document(abbreviations={"fx": 3}))


def test_a_blank_expansion_is_rejected_by_the_model_the_reader_builds() -> None:
    with pytest.raises(ValueError, match=r"\Aabbreviation 'fx' has a blank expansion\Z"):
        read_glossary_json(document(abbreviations={"fx": " "}))


def test_reading_rejects_input_that_is_not_text() -> None:
    with pytest.raises(TypeError, match=r"\Atext must be a string\Z"):
        read_glossary_json(None)  # type: ignore[arg-type]


def test_an_empty_glossary_file_reads_as_an_empty_glossary() -> None:
    assert read_glossary_json(write_glossary_json(Glossary())) == Glossary()


def test_json_nesting_at_the_family_depth_limit_is_accepted() -> None:
    text = "[" * _MAX_JSON_NESTING_DEPTH + "]" * _MAX_JSON_NESTING_DEPTH

    _check_nesting_depth(text)  # must not raise


def test_json_nesting_one_level_past_the_family_depth_limit_is_rejected() -> None:
    depth = _MAX_JSON_NESTING_DEPTH + 1
    text = "[" * depth + "]" * depth

    with pytest.raises(
        ValueError,
        match=rf"\Aglossary JSON nesting depth {depth} exceeds the limit of "
        rf"{_MAX_JSON_NESTING_DEPTH}\Z",
    ):
        _check_nesting_depth(text)


def test_bracket_characters_inside_a_json_string_do_not_count_toward_nesting_depth() -> None:
    text = json.dumps({"a": "[" * (_MAX_JSON_NESTING_DEPTH + 50)})

    _check_nesting_depth(text)  # must not raise: only one real container, the root object


def test_an_escaped_quote_does_not_end_the_string_early() -> None:
    depth = _MAX_JSON_NESTING_DEPTH + 1
    text = '{"a": "value with \\" quote"}' + ("[" * depth + "]" * depth)

    with pytest.raises(ValueError, match=rf"\Aglossary JSON nesting depth {depth} exceeds"):
        _check_nesting_depth(text)


def test_deeply_nested_glossary_json_is_rejected_before_the_decoder_ever_sees_it() -> None:
    depth = _MAX_JSON_NESTING_DEPTH + 1
    text = "[" * depth + "]" * depth

    with pytest.raises(
        ValueError,
        match=rf"\Aglossary JSON nesting depth {depth} exceeds the limit of "
        rf"{_MAX_JSON_NESTING_DEPTH}\Z",
    ):
        read_glossary_json(text)
