# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared glossary sample for the reader/writer/renderer suites.

The sample exercises every optional field at once, so one document pins the whole file format.
Glossary fixtures assert the model invariant at setup *and* teardown: a test that reaches past the
frozen dataclasses and corrupts shared state fails in the test that did it, not in the next one.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    SynonymAlias,
    TermKind,
    TermStatus,
)
from narrativetrace_glossary.models import _invariant

FIRST_SEEN = date(2026, 8, 11)

CANONICAL_DOCUMENT = """{
  "schemaVersion": 1,
  "contexts": {
    "_unassigned": {
      "packages": []
    },
    "billing": {
      "packages": ["acme.billing"],
      "description": "Charging, invoicing, funds"
    }
  },
  "terms": [
    {
      "term": "overdraft account",
      "context": "billing",
      "kind": "noun-phrase",
      "status": "curated",
      "definition": "Account permitted to go below zero up to an agreed limit.",
      "translations": {
        "es": "cuenta con descubierto"
      },
      "synonyms": [
        { "alias": "account with overdraft", "note": "legacy v1 API phrasing" }
      ],
      "sources": ["acme.billing.overdraft_service.open_overdraft_account"],
      "firstSeen": "2026-08-11"
    }
  ]
}
"""


def build_populated_glossary() -> Glossary:
    """Builds the in-memory twin of :data:`CANONICAL_DOCUMENT`."""
    return Glossary(
        {
            "billing": BoundedContext("billing", ["acme.billing"], "Charging, invoicing, funds"),
            "_unassigned": BoundedContext("_unassigned"),
        },
        [
            GlossaryTerm(
                "overdraft account",
                "billing",
                TermKind.NOUN_PHRASE,
                TermStatus.CURATED,
                "Account permitted to go below zero up to an agreed limit.",
                {"es": "cuenta con descubierto"},
                [SynonymAlias("account with overdraft", "legacy v1 API phrasing")],
                ["acme.billing.overdraft_service.open_overdraft_account"],
                first_seen=FIRST_SEEN,
            )
        ],
    )


@pytest.fixture
def canonical_document() -> str:
    return CANONICAL_DOCUMENT


@pytest.fixture
def populated_glossary() -> Iterator[Glossary]:
    glossary = build_populated_glossary()
    assert _invariant(glossary), "sample glossary is inconsistent before the test"
    yield glossary
    assert _invariant(glossary), "the test left the sample glossary inconsistent"
