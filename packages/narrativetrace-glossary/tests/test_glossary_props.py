# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for the glossary's serialization safety properties.

Plan section 10 makes determinism binding: ``write ∘ read ∘ write == write`` for any structurally
valid glossary, so a run that harvests nothing leaves the committed file byte-identical.

Generators live in ``glossary_strategies``, shared with the merge suite.
"""

from __future__ import annotations

import json
import re

import pytest
from glossary_strategies import glossaries
from hypothesis import given
from hypothesis import strategies as st
from narrativetrace_glossary import (
    Glossary,
    read_glossary_json,
    render_glossary_markdown,
    write_glossary_json,
)
from narrativetrace_glossary.json_reader import _ROOT_KEYS
from narrativetrace_glossary.models import _invariant

UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")

MARKDOWN_TABLE_HEADER = "| Term | Status | Definition | Deprecated synonyms | Translations |"


@given(glossaries())
def test_every_generated_glossary_satisfies_the_model_invariant(glossary: Glossary) -> None:
    assert _invariant(glossary)


@given(glossaries())
def test_writing_reading_and_writing_again_reproduces_the_bytes(glossary: Glossary) -> None:
    written = write_glossary_json(glossary)
    reread = read_glossary_json(written)

    assert reread == glossary
    assert write_glossary_json(reread) == written


@given(glossaries())
def test_the_written_bytes_do_not_depend_on_insertion_order(glossary: Glossary) -> None:
    reversed_order = Glossary(
        dict(reversed(list(glossary.contexts.items()))),
        list(reversed(list(glossary.terms))),
        dict(reversed(list(glossary.abbreviations.items()))),
        schema_version=glossary.schema_version,
    )

    assert write_glossary_json(reversed_order) == write_glossary_json(glossary)


@given(glossaries())
def test_no_curated_text_is_altered_by_the_round_trip(glossary: Glossary) -> None:
    reread = read_glossary_json(write_glossary_json(glossary))

    assert [term.definition for term in reread.terms] == [
        term.definition for term in glossary.terms
    ]
    assert [dict(term.translations) for term in reread.terms] == [
        dict(term.translations) for term in glossary.terms
    ]


@given(glossaries())
def test_the_document_is_always_parseable_and_newline_terminated(glossary: Glossary) -> None:
    written = write_glossary_json(glossary)

    assert json.loads(written)["schemaVersion"] == glossary.schema_version
    assert written.endswith("}\n")


@given(glossaries())
def test_dropping_the_abbreviations_leaves_the_bytes_a_schema_one_file_would_have(
    glossary: Glossary,
) -> None:
    """The anti-churn rule: the section costs nothing to a repository that declares none."""
    without = Glossary(glossary.contexts, glossary.terms)

    written = write_glossary_json(without)

    assert '"abbreviations"' not in written
    assert json.loads(written)["schemaVersion"] == 1


@given(glossaries())
def test_every_markdown_table_line_holds_exactly_five_cells(glossary: Glossary) -> None:
    lines = render_glossary_markdown(glossary).splitlines()

    for line in (line for line in lines if line.startswith("|")):
        assert len(UNESCAPED_PIPE.split(line)) == 7, line


@given(glossaries())
def test_markdown_renders_one_row_per_term(glossary: Glossary) -> None:
    lines = render_glossary_markdown(glossary).splitlines()

    rows = [line for line in lines if line.startswith("| ") and line != MARKDOWN_TABLE_HEADER]

    assert len(rows) == len(glossary.terms)


@given(glossaries(), st.text(min_size=1).filter(lambda key: key not in _ROOT_KEYS))
def test_an_unknown_root_key_is_always_rejected(glossary: Glossary, key: str) -> None:
    body = json.loads(write_glossary_json(glossary))
    body[key] = "anything"

    with pytest.raises(ValueError) as rejection:
        read_glossary_json(json.dumps(body))

    assert str(rejection.value) == f"unknown key '{key}' in glossary"
