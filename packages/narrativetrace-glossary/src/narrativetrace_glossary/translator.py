# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Looks up a glossary's per-locale translation of a normalized phrase.

``GlossaryTranslator``. INTENT: the lookup chain is exact phrase, then per-token word
lookup, then untranslated passthrough — never a fuzzy or partial match, so a translation is either
exactly what a human curated or visibly incomplete (never a guess). An uncovered phrase renders
byte-identical to its input and reports ``complete=False``, which is what drives the translated
view's "glossary gaps" footer (plan safety property 1's lookup-layer half: nothing this returns
ever differs from a curated translation or the untouched input).
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace_glossary.models import Glossary, GlossaryTerm


@dataclass(frozen=True, slots=True)
class PhraseTranslation:
    """One lookup's outcome: the text to display, and whether every part of it was translated."""

    text: str
    complete: bool


def _index(glossary: Glossary) -> dict[str, dict[str, GlossaryTerm]]:
    index: dict[str, dict[str, GlossaryTerm]] = {}
    for term in glossary.terms:
        index.setdefault(term.context, {})[term.term] = term
    return index


class GlossaryTranslator:
    """Translates normalized glossary phrases and raw narration templates into one locale."""

    def __init__(self, glossary: Glossary) -> None:
        if not isinstance(glossary, Glossary):
            raise TypeError("glossary must be a Glossary")
        self._terms_by_context = _index(glossary)

    def _lookup(self, phrase: str, context: str, locale: str) -> str | None:
        term = self._terms_by_context.get(context, {}).get(phrase)
        return None if term is None else term.translations.get(locale)

    def translate(self, phrase: str, context: str, locale: str) -> PhraseTranslation:
        """Translates a normalized phrase: exact match, else per-token, else untranslated.

        Args:
            phrase: a normalized glossary phrase (lowercase, space-separated) — an identifier
                must already be run through
                :func:`~narrativetrace_glossary.normalizer.normalize_phrase`.
            context: the bounded context the phrase was observed in.
            locale: the target locale.

        Returns:
            The translated text (or ``phrase`` itself, byte-identical, when nothing matched) and
            whether every token was actually translated.

        Raises:
            ValueError: if ``phrase``, ``context``, or ``locale`` is blank.
        """
        _require_non_blank(phrase=phrase, context=context, locale=locale)
        exact = self._lookup(phrase, context, locale)
        if exact is not None:
            return PhraseTranslation(exact, True)
        return self._translate_token_by_token(phrase, context, locale)

    def _translate_token_by_token(
        self, phrase: str, context: str, locale: str
    ) -> PhraseTranslation:
        tokens = phrase.split(" ")
        rendered: list[str] = []
        complete = True
        for token in tokens:
            variant = self._lookup(token, context, locale)
            if variant is None:
                complete = False
                rendered.append(token)
            else:
                rendered.append(variant)
        return PhraseTranslation(" ".join(rendered), complete)

    def template_variant(self, raw_template: str, context: str, locale: str) -> str | None:
        """Exact-lookup only: a raw narration template with its ``{placeholders}`` intact.

        No token fallback — a template is prose with placeholders, not a phrase to gloss
        word-by-word. Returns ``None`` when the glossary declares no variant for this locale, which
        is what tells the caller to treat the raw template as a gap rather than guess at one.
        """
        _require_non_blank(raw_template=raw_template, context=context, locale=locale)
        return self._lookup(raw_template, context, locale)


def _require_non_blank(**fields: str) -> None:
    for name, value in fields.items():
        if not value.strip():
            raise ValueError(f"{name} must not be blank")
