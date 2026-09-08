# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Rendering canonical entries into a translated trace: re-derivation, never substitution."""

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
from narrativetrace_glossary.translation_view import TraceTranslationView

from narrativetrace.canonical import CanonicalEntry, ParameterEntry

_FIRST_SEEN = date(2026, 8, 11)


def _term(term: str, context: str, kind: TermKind, translations: dict[str, str]) -> GlossaryTerm:
    return GlossaryTerm(
        term, context, kind, TermStatus.CURATED, translations=translations, first_seen=_FIRST_SEEN
    )


def _billing_glossary(*extra: GlossaryTerm) -> Glossary:
    return Glossary({"billing": BoundedContext("billing", ["acme.billing"])}, list(extra))


def _enter(
    span_id: str,
    parent_span_id: str | None,
    class_name: str,
    function: str,
    package: str = "acme.billing",
    parameters: list[ParameterEntry] | None = None,
    narration_template: str | None = None,
) -> CanonicalEntry:
    return CanonicalEntry(
        timestamp="2026-08-11T00:00:00.000Z",
        level="trace",
        message="",
        nt_event_type="method_enter",
        span_id=span_id,
        parent_span_id=parent_span_id,
        code_namespace=class_name,
        code_function=function,
        nt_package=package,
        nt_parameters=parameters,
        nt_narration_template=narration_template,
    )


def _exit(
    span_id: str,
    outcome: str = "success",
    return_value: str | None = None,
    exception_type: str | None = None,
    exception_message: str | None = None,
) -> CanonicalEntry:
    return CanonicalEntry(
        timestamp="2026-08-11T00:00:00.010Z",
        level="trace",
        message="",
        nt_event_type="method_exit",
        span_id=span_id,
        nt_outcome=outcome,
        nt_return_value=return_value,
        exception_type=exception_type,
        exception_message=exception_message,
    )


def test_renders_translated_function_with_original_kept_alongside() -> None:
    glossary = _billing_glossary(_term("open", "billing", TermKind.WORD, {"es": "abre"}))
    view = TraceTranslationView(glossary)
    state = view.new_render_state("es")

    line = view.render_entry(_enter("s1", None, "OverdraftService", "open"), state)

    assert line == "OverdraftService.abre (open)\n"


def test_renders_translated_parameter_names_with_values_verbatim() -> None:
    glossary = _billing_glossary(_term("customer", "billing", TermKind.WORD, {"es": "cliente"}))
    view = TraceTranslationView(glossary)
    state = view.new_render_state("es")
    entry = _enter(
        "s1", None, "OverdraftService", "open", parameters=[ParameterEntry("customer", '"C-1"')]
    )

    line = view.render_entry(entry, state)

    assert line == 'OverdraftService.open (open) (cliente: "C-1")\n'


def test_a_role_suffixed_parameter_name_strips_the_suffix_before_lookup() -> None:
    """Regression: a parameter's glossed name must match how it was harvested.

    ``parameter_candidate`` (what the harvester used to create the "customer" term in the first
    place) strips a trailing ``id`` role token; the view must normalize the same way; a naive
    whole-phrase normalization would look up "customer id" instead, never match, and render the
    odd half-translated "cliente id" this test used to catch.
    """
    glossary = _billing_glossary(_term("customer", "billing", TermKind.WORD, {"es": "cliente"}))
    view = TraceTranslationView(glossary)
    state = view.new_render_state("es")
    entry = _enter(
        "s1", None, "OverdraftService", "open", parameters=[ParameterEntry("customer_id", '"C-1"')]
    )

    line = view.render_entry(entry, state)

    assert line == 'OverdraftService.open (open) (cliente: "C-1")\n'
    assert "customer id" not in state.gaps


def test_a_parameter_naming_only_a_role_token_passes_through_untranslated_no_gap() -> None:
    glossary = _billing_glossary(_term("open", "billing", TermKind.WORD, {"es": "abre"}))
    view = TraceTranslationView(glossary)
    state = view.new_render_state("es")
    entry = _enter("s1", None, "X", "open", parameters=[ParameterEntry("id", '"1"')])

    line = view.render_entry(entry, state)

    assert line == 'X.abre (open) (id: "1")\n'
    assert not state.gaps  # "id" alone names no concept: passed through, but not a reportable gap


def test_redacted_parameter_values_pass_through_verbatim() -> None:
    glossary = _billing_glossary(_term("password", "billing", TermKind.WORD, {"es": "contraseña"}))
    view = TraceTranslationView(glossary)
    state = view.new_render_state("es")
    entry = _enter(
        "s1",
        None,
        "AuthService",
        "login",
        parameters=[ParameterEntry("password", "[REDACTED]", redacted=True)],
    )

    line = view.render_entry(entry, state)

    assert "contraseña: [REDACTED]" in line


def test_untranslated_identifier_shows_normalized_phrase_and_becomes_a_gap() -> None:
    view = TraceTranslationView(_billing_glossary())
    state = view.new_render_state("es")

    view.render_entry(_enter("s1", None, "OverdraftService", "openAccount"), state)

    assert "open account" in state.gaps


def test_exit_success_with_return_value() -> None:
    glossary = Glossary()
    view = TraceTranslationView(glossary)
    state = view.new_render_state("es")

    line = view.render_entry(_exit("s1", return_value="42"), state)

    assert line == "-> devuelve 42\n"


def test_exit_success_with_no_return_value() -> None:
    view = TraceTranslationView(Glossary())
    state = view.new_render_state("es")

    line = view.render_entry(_exit("s1"), state)

    assert line == "-> devuelve\n"


def test_exit_incomplete() -> None:
    view = TraceTranslationView(Glossary())
    state = view.new_render_state("es")

    line = view.render_entry(_exit("s1", outcome="incomplete"), state)

    assert line == ".. incompleto\n"


def test_exit_failure_translates_the_exception_phrase_original_type_and_message_verbatim() -> None:
    glossary = _billing_glossary(
        _term("insufficient fund", "billing", TermKind.NOUN_PHRASE, {"es": "fondos insuficientes"})
    )
    view = TraceTranslationView(glossary)
    state = view.new_render_state("es")
    view.render_entry(_enter("s1", None, "PaymentService", "charge"), state)  # sets context for s1

    line = view.render_entry(
        _exit(
            "s1",
            outcome="failure",
            exception_type="InsufficientFundsException",
            exception_message="balance 12.50 below required 74.97",
        ),
        state,
    )

    expected = (
        "!! fondos insuficientes [InsufficientFundsException]: balance 12.50 below required 74.97\n"
    )
    assert line == expected


def test_exit_failure_with_an_unnormalizable_exception_type_falls_back_to_the_raw_name() -> None:
    view = TraceTranslationView(Glossary())
    state = view.new_render_state("es")

    line = view.render_entry(
        _exit("s1", outcome="failure", exception_type="_", exception_message="boom"), state
    )

    assert line == "!! _ [_]: boom\n"


def test_nested_calls_indent_by_depth() -> None:
    view = TraceTranslationView(Glossary())
    state = view.new_render_state("es")

    root = view.render_entry(_enter("s1", None, "A", "root"), state)
    child = view.render_entry(_enter("s2", "s1", "B", "child"), state)
    child_exit = view.render_entry(_exit("s2"), state)
    root_exit = view.render_entry(_exit("s1"), state)

    assert root == "A.root (root)\n"
    assert child == "  B.child (child)\n"
    assert child_exit == "  -> devuelve\n"
    assert root_exit == "-> devuelve\n"


def test_narration_template_is_filled_from_untouched_parameter_values() -> None:
    glossary = _billing_glossary(
        _term(
            "Opening overdraft for {customerId}",
            "billing",
            TermKind.TEMPLATE,
            {"es": "Abriendo descubierto para {customerId}"},
        )
    )
    view = TraceTranslationView(glossary)
    state = view.new_render_state("es")
    entry = _enter(
        "s1",
        None,
        "OverdraftService",
        "open",
        parameters=[ParameterEntry("customerId", '"C-1"')],
        narration_template="Opening overdraft for {customerId}",
    )

    line = view.render_entry(entry, state)

    assert '// Abriendo descubierto para "C-1"' in line


def test_narration_template_without_a_locale_variant_renders_no_line_and_becomes_a_gap() -> None:
    view = TraceTranslationView(_billing_glossary())
    state = view.new_render_state("es")
    entry = _enter("s1", None, "X", "open", narration_template="Opening for {a}")

    line = view.render_entry(entry, state)

    assert "//" not in line
    assert "Opening for {a}" in state.gaps


def test_gaps_footer_empty_when_nothing_is_missing() -> None:
    view = TraceTranslationView(Glossary())
    state = view.new_render_state("es")

    assert view.render_gaps_footer(state) == ""


def test_gaps_footer_lists_every_missing_phrase_sorted() -> None:
    view = TraceTranslationView(_billing_glossary())
    state = view.new_render_state("es")
    view.render_entry(_enter("s1", None, "Z", "zebra"), state)
    view.render_entry(_enter("s2", "s1", "A", "apple"), state)

    footer = view.render_gaps_footer(state)

    assert footer == "\n---\nVacíos del glosario:\n- apple\n- zebra\n"


def test_single_context_glossary_applies_even_with_no_matching_module() -> None:
    glossary = Glossary(
        {"billing": BoundedContext("billing", ["something.else"])},
        [_term("open", "billing", TermKind.WORD, {"es": "abre"})],
    )
    view = TraceTranslationView(glossary)
    state = view.new_render_state("es")

    line = view.render_entry(_enter("s1", None, "X", "open", package="unrelated.module"), state)

    assert line == "X.abre (open)\n"


def test_batch_render_equals_concatenated_entries_plus_footer() -> None:
    glossary = _billing_glossary(_term("open", "billing", TermKind.WORD, {"es": "abre"}))
    view = TraceTranslationView(glossary)
    entries = [
        _enter("s1", None, "OverdraftService", "open"),
        _enter("s2", "s1", "Y", "unknownMethod"),
        _exit("s2"),
        _exit("s1"),
    ]

    batch = view.render(entries, "es")

    state = view.new_render_state("es")
    incremental = "".join(view.render_entry(e, state) for e in entries) + view.render_gaps_footer(
        state
    )
    assert batch == incremental
    assert "Vacíos del glosario" in batch


def test_concurrency_marker_event_types_render_as_empty_string() -> None:
    view = TraceTranslationView(Glossary())
    state = view.new_render_state("es")
    fork = CanonicalEntry(
        timestamp="2026-08-11T00:00:00.000Z", level="trace", message="", nt_event_type="fork"
    )

    assert view.render_entry(fork, state) == ""


def test_render_and_new_render_state_reject_a_blank_locale() -> None:
    view = TraceTranslationView(Glossary())
    with pytest.raises(ValueError, match=r"\Alocale must not be blank\Z"):
        view.new_render_state("")
    with pytest.raises(ValueError, match=r"\Alocale must not be blank\Z"):
        view.render([], "")


def test_render_state_is_reusable_across_multiple_traces_sequentially() -> None:
    view = TraceTranslationView(
        _billing_glossary(_term("open", "billing", TermKind.WORD, {"es": "abre"}))
    )
    state = view.new_render_state("es")

    first = view.render_entry(_enter("s1", None, "X", "open"), state)
    view.render_entry(_exit("s1"), state)
    second = view.render_entry(_enter("s1", None, "X", "open"), state)  # span id reused, new trace

    assert first == second == "X.abre (open)\n"
