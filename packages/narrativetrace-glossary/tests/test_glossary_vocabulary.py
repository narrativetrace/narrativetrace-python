# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The committed glossary as clarity's vocabulary: what it teaches, and what it must not."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from narrativetrace_clarity import EMPTY
from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    SynonymAlias,
    TermKind,
    TermStatus,
)
from narrativetrace_glossary.vocabulary import glossary_vocabulary, read_project_vocabulary

FIRST_SEEN = date(2026, 8, 11)
CONTEXTS = {"trading": BoundedContext("trading", ("acme.trading",))}

GLOSSARY_JSON = """{
  "schemaVersion": 1,
  "contexts": {"trading": {"packages": ["acme.trading"]}},
  "terms": [
    {
      "term": "settle trade",
      "context": "trading",
      "kind": "verb-phrase",
      "status": "curated",
      "firstSeen": "2020-01-01"
    }
  ]
}"""


def term(text: str, kind: TermKind, status: TermStatus, **overrides: object) -> GlossaryTerm:
    fields: dict[str, object] = {
        "term": text,
        "context": "trading",
        "kind": kind,
        "status": status,
        "first_seen": FIRST_SEEN,
    }
    fields.update(overrides)
    return GlossaryTerm(**fields)  # type: ignore[arg-type]


def glossary_of(*terms: GlossaryTerm) -> Glossary:
    return Glossary(CONTEXTS, terms)


class TestGlossaryVocabulary:
    def test_a_verb_phrase_declares_its_leading_verb_and_trailing_nouns(self) -> None:
        vocabulary = glossary_vocabulary(
            glossary_of(term("settle trade", TermKind.VERB_PHRASE, TermStatus.CURATED))
        )

        assert vocabulary.is_domain_verb("settle")
        assert vocabulary.is_domain_noun("trade")
        assert not vocabulary.is_domain_noun("settle")
        assert not vocabulary.is_domain_verb("trade")

    def test_a_noun_phrase_declares_every_token_as_a_noun(self) -> None:
        vocabulary = glossary_vocabulary(
            glossary_of(term("credit tranche", TermKind.NOUN_PHRASE, TermStatus.CURATED))
        )

        assert vocabulary.is_domain_noun("credit")
        assert vocabulary.is_domain_noun("tranche")
        assert not vocabulary.verbs

    def test_a_word_declares_itself_as_a_noun_but_not_as_accepted_shorthand(self) -> None:
        vocabulary = glossary_vocabulary(
            glossary_of(term("fx", TermKind.WORD, TermStatus.HARVESTED))
        )

        assert vocabulary.is_domain_noun("fx")
        assert not vocabulary.is_accepted_abbreviation("fx")

    def test_the_abbreviations_section_is_what_accepts_shorthand(self) -> None:
        vocabulary = glossary_vocabulary(
            Glossary(CONTEXTS, abbreviations={"fx": "foreign exchange"})
        )

        assert vocabulary.is_accepted_abbreviation("fx")
        assert not vocabulary.is_domain_noun("fx")

    def test_a_phrase_token_never_accepts_shorthand_by_accident(self) -> None:
        """The phrase-token defect, inverted: committing `calc total` must not accept `calc`."""
        vocabulary = glossary_vocabulary(
            glossary_of(term("calc total", TermKind.NOUN_PHRASE, TermStatus.HARVESTED))
        )

        assert vocabulary.is_domain_noun("calc")
        assert not vocabulary.is_accepted_abbreviation("calc")

    def test_harvested_terms_count_because_the_commit_is_the_approval(self) -> None:
        vocabulary = glossary_vocabulary(
            glossary_of(term("fold position", TermKind.VERB_PHRASE, TermStatus.HARVESTED))
        )

        assert vocabulary.is_domain_verb("fold")

    def test_stale_terms_are_no_longer_vocabulary(self) -> None:
        vocabulary = glossary_vocabulary(
            glossary_of(term("unwind position", TermKind.VERB_PHRASE, TermStatus.STALE))
        )

        assert vocabulary.is_empty()

    def test_template_entries_are_narration_text_not_vocabulary(self) -> None:
        vocabulary = glossary_vocabulary(
            glossary_of(term("settled {amount}", TermKind.TEMPLATE, TermStatus.CURATED))
        )

        assert vocabulary.is_empty()

    def test_deprecated_synonyms_never_become_vocabulary(self) -> None:
        vocabulary = glossary_vocabulary(
            glossary_of(
                term(
                    "tranche",
                    TermKind.WORD,
                    TermStatus.CURATED,
                    synonyms=(SynonymAlias("slice"),),
                )
            )
        )

        assert vocabulary.is_domain_noun("tranche")
        assert not vocabulary.is_domain_noun("slice")
        assert not vocabulary.is_accepted_abbreviation("slice")

    def test_every_bounded_context_contributes(self) -> None:
        contexts = {
            "trading": BoundedContext("trading", ("acme.trading",)),
            "billing": BoundedContext("billing", ("acme.billing",)),
        }
        billing = GlossaryTerm(
            "invoice",
            "billing",
            TermKind.WORD,
            TermStatus.CURATED,
            first_seen=FIRST_SEEN,
        )

        vocabulary = glossary_vocabulary(
            Glossary(contexts, (term("tranche", TermKind.WORD, TermStatus.CURATED), billing))
        )

        assert vocabulary.is_domain_noun("tranche")
        assert vocabulary.is_domain_noun("invoice")


class TestReadProjectVocabulary:
    def test_no_directory_means_no_committed_vocabulary(self) -> None:
        assert read_project_vocabulary(None) == EMPTY

    def test_a_directory_without_a_glossary_means_no_committed_vocabulary(
        self, tmp_path: Path
    ) -> None:
        assert read_project_vocabulary(tmp_path) == EMPTY
        assert read_project_vocabulary(tmp_path / "absent") == EMPTY

    def test_reads_the_committed_glossary_from_its_directory(self, tmp_path: Path) -> None:
        (tmp_path / "glossary.json").write_text(GLOSSARY_JSON, encoding="utf-8")

        vocabulary = read_project_vocabulary(tmp_path)

        assert vocabulary.is_domain_verb("settle")
        assert vocabulary.is_domain_noun("trade")

    def test_reads_the_accepted_abbreviations_of_a_schema_two_file(self, tmp_path: Path) -> None:
        (tmp_path / "glossary.json").write_text(
            GLOSSARY_JSON.replace(
                '"schemaVersion": 1,',
                '"schemaVersion": 2,\n  "abbreviations": {"fx": "foreign exchange"},',
            ),
            encoding="utf-8",
        )

        assert read_project_vocabulary(tmp_path).is_accepted_abbreviation("fx")

    def test_accepts_the_directory_as_a_string(self, tmp_path: Path) -> None:
        (tmp_path / "glossary.json").write_text(GLOSSARY_JSON, encoding="utf-8")

        assert read_project_vocabulary(str(tmp_path)).is_domain_verb("settle")

    def test_a_directory_named_like_the_glossary_is_not_a_glossary(self, tmp_path: Path) -> None:
        (tmp_path / "glossary.json").mkdir()

        assert read_project_vocabulary(tmp_path) == EMPTY

    def test_reads_a_non_ascii_glossary_as_utf8(self, tmp_path: Path) -> None:
        (tmp_path / "glossary.json").write_text(
            GLOSSARY_JSON.replace('"settle trade"', '"liquidar operación"'),
            encoding="utf-8",
        )

        vocabulary = read_project_vocabulary(tmp_path)

        assert vocabulary.is_domain_verb("liquidar")
        assert vocabulary.is_domain_noun("operación")

    def test_a_malformed_glossary_fails_loudly_rather_than_scoring_without_it(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "glossary.json").write_text("{ not json", encoding="utf-8")

        with pytest.raises(ValueError):
            read_project_vocabulary(tmp_path)
