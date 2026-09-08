# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The glossary translation lookup: exact phrase, then per-token, then untranslated."""

from __future__ import annotations

from datetime import date

import pytest
from narrativetrace_glossary.models import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    TermKind,
    TermStatus,
)
from narrativetrace_glossary.translator import GlossaryTranslator, PhraseTranslation

_FIRST_SEEN = date(2026, 8, 11)


def _term(term: str, context: str, kind: TermKind, translations: dict[str, str]) -> GlossaryTerm:
    return GlossaryTerm(
        term, context, kind, TermStatus.CURATED, translations=translations, first_seen=_FIRST_SEEN
    )


def _glossary() -> Glossary:
    return Glossary(
        {"billing": BoundedContext("billing", ["acme.billing"])},
        [
            _term(
                "overdraft account",
                "billing",
                TermKind.NOUN_PHRASE,
                {"es": "cuenta con descubierto"},
            ),
            _term("open", "billing", TermKind.WORD, {"es": "abre"}),
            _term(
                "customer {customerId} not found",
                "billing",
                TermKind.TEMPLATE,
                {"es": "cliente {customerId} no encontrado"},
            ),
        ],
    )


def test_exact_phrase_match_is_complete() -> None:
    translator = GlossaryTranslator(_glossary())

    result = translator.translate("overdraft account", "billing", "es")

    assert result == PhraseTranslation("cuenta con descubierto", True)


def test_token_by_token_fallback_when_no_exact_phrase_exists() -> None:
    translator = GlossaryTranslator(_glossary())

    # "open" is a known word, "account" is not — partial coverage, marked incomplete.
    result = translator.translate("open account", "billing", "es")

    assert result == PhraseTranslation("abre account", False)


def test_fully_uncovered_phrase_passes_through_byte_identical() -> None:
    translator = GlossaryTranslator(_glossary())

    result = translator.translate("totally unknown phrase", "billing", "es")

    assert result == PhraseTranslation("totally unknown phrase", False)


def test_a_locale_the_term_has_no_translation_for_is_incomplete() -> None:
    translator = GlossaryTranslator(_glossary())

    result = translator.translate("overdraft account", "billing", "zh-CN")

    assert result == PhraseTranslation("overdraft account", False)


def test_context_isolation_a_phrase_in_another_context_does_not_match() -> None:
    translator = GlossaryTranslator(_glossary())

    result = translator.translate("overdraft account", "shipping", "es")

    assert result == PhraseTranslation("overdraft account", False)


def test_template_variant_is_exact_lookup_only_no_token_fallback() -> None:
    translator = GlossaryTranslator(_glossary())

    variant = translator.template_variant("customer {customerId} not found", "billing", "es")

    assert variant == "cliente {customerId} no encontrado"


def test_template_variant_with_no_locale_match_returns_none() -> None:
    translator = GlossaryTranslator(_glossary())

    assert (
        translator.template_variant("customer {customerId} not found", "billing", "zh-CN") is None
    )


def test_template_variant_never_falls_back_to_token_by_token() -> None:
    translator = GlossaryTranslator(_glossary())

    # Even though "customer" alone might tokenize to something, templates are exact-only.
    assert translator.template_variant("customer not found at all", "billing", "es") is None


@pytest.mark.parametrize(
    ("phrase", "context", "locale"),
    [("", "billing", "es"), ("open", "", "es"), ("open", "billing", "")],
)
def test_translate_rejects_blank_arguments(phrase: str, context: str, locale: str) -> None:
    translator = GlossaryTranslator(_glossary())
    with pytest.raises(ValueError, match="must not be blank"):
        translator.translate(phrase, context, locale)


def test_template_variant_rejects_blank_arguments() -> None:
    translator = GlossaryTranslator(_glossary())
    with pytest.raises(ValueError, match="must not be blank"):
        translator.template_variant("", "billing", "es")


def test_rejects_a_non_glossary() -> None:
    with pytest.raises(TypeError, match=r"\Aglossary must be a Glossary\Z"):
        GlossaryTranslator({"not": "a glossary"})  # type: ignore[arg-type]
