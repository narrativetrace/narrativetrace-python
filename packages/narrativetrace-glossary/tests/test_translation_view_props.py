# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property-based tests for the translated view's safety properties (plan section 10).

Two are binding for any glossary and any entry sequence, including adversarial ones (null span
ids, unknown parents, exits with no matching enter, unrecognized event types): **no value token
is ever altered by translation**, and **batch render is byte-identical to the concatenation of
per-entry calls plus the gaps footer** — the parity a live subscriber's incremental rendering
relies on.
"""

from __future__ import annotations

from glossary_strategies import glossaries
from hypothesis import given, settings
from hypothesis import strategies as st
from narrativetrace_glossary.models import Glossary
from narrativetrace_glossary.translation_view import TraceTranslationView

from narrativetrace.canonical import CanonicalEntry, ParameterEntry

_LOCALES = ("en", "es", "zh-CN", "unrecognized")
_EVENT_TYPES = ("method_enter", "method_exit", "fork", "join", "async_dispatch", "")
_OUTCOMES = ("success", "failure", "incomplete", None)
_MARKER = "MARK-"  # a prefix no glossary term/translation in this suite ever produces


def _payload(draw: st.DrawFn, tag: str) -> str:
    """A value string carrying an unforgeable marker, so "did it change" is a substring check."""
    return f"{_MARKER}{tag}-" + draw(
        st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), max_size=8)
    )


@st.composite
def parameters(draw: st.DrawFn) -> list[ParameterEntry]:
    count = draw(st.integers(min_value=0, max_value=3))
    return [
        ParameterEntry(
            name=draw(st.sampled_from(["alpha", "beta", "customerId", "x"])),
            value=_payload(draw, f"param{i}"),
            redacted=draw(st.booleans()),
        )
        for i in range(count)
    ]


@st.composite
def entries(draw: st.DrawFn) -> CanonicalEntry:
    span_id = draw(st.one_of(st.none(), st.sampled_from(["s1", "s2", "s3"])))
    parent_span_id = draw(
        st.one_of(st.none(), st.sampled_from(["s1", "s2", "s3", "unknown-parent"]))
    )
    event_type = draw(st.sampled_from(_EVENT_TYPES))
    outcome = draw(st.sampled_from(_OUTCOMES))
    has_exception = outcome == "failure" and draw(st.booleans())
    return CanonicalEntry(
        timestamp="2026-08-11T00:00:00.000Z",
        level="trace",
        message="",
        nt_event_type=event_type,
        span_id=span_id,
        parent_span_id=parent_span_id,
        code_namespace=draw(st.sampled_from(["A", "B", ""])),
        code_function=draw(st.sampled_from(["openAccount", "doThing", ""])),
        nt_package=draw(st.one_of(st.none(), st.sampled_from(["acme.billing", "acme.other"]))),
        nt_parameters=draw(st.one_of(st.none(), parameters())),
        nt_narration_template=draw(st.one_of(st.none(), st.sampled_from(["Doing {alpha}", ""]))),
        nt_outcome=outcome,
        nt_return_value=draw(
            st.one_of(
                st.none(), st.text(min_size=0, max_size=6).map(lambda t: _MARKER + "ret-" + t)
            )
        ),
        exception_type=draw(st.sampled_from(["BoomError", ""])) if has_exception else None,
        exception_message=(_MARKER + "exc-" + draw(st.text(max_size=6))) if has_exception else None,
    )


def _entry_sequences() -> st.SearchStrategy[list[CanonicalEntry]]:
    return st.lists(entries(), max_size=8)


@given(glossaries(), _entry_sequences(), st.sampled_from(_LOCALES))
@settings(max_examples=60)
def test_render_never_raises_over_adversarial_entry_sequences(
    glossary: Glossary, sequence: list[CanonicalEntry], locale: str
) -> None:
    view = TraceTranslationView(glossary)

    view.render(sequence, locale)  # must not raise


@given(glossaries(), _entry_sequences(), st.sampled_from(_LOCALES))
@settings(max_examples=60)
def test_batch_render_equals_incremental_render_plus_footer(
    glossary: Glossary, sequence: list[CanonicalEntry], locale: str
) -> None:
    view = TraceTranslationView(glossary)

    batch = view.render(sequence, locale)

    state = view.new_render_state(locale)
    incremental = "".join(view.render_entry(entry, state) for entry in sequence)
    incremental += view.render_gaps_footer(state)
    assert batch == incremental


def _assert_enter_values_survive(entry: CanonicalEntry, rendered: str) -> None:
    for parameter in entry.nt_parameters or ():
        assert parameter.value in rendered


def _assert_exit_values_survive(entry: CanonicalEntry, rendered: str) -> None:
    # A return value only ever renders on the success path — "incomplete"/"failure" outcomes
    # never consult it, by design (there is nothing meaningful to show).
    renders_return_value = entry.nt_outcome not in ("incomplete", "failure")
    if entry.nt_return_value is not None and renders_return_value:
        assert entry.nt_return_value in rendered
    if entry.exception_message is not None and entry.nt_outcome == "failure":
        assert entry.exception_message in rendered


@given(glossaries(), _entry_sequences(), st.sampled_from(_LOCALES))
@settings(max_examples=60)
def test_every_marked_value_passes_through_the_render_verbatim(
    glossary: Glossary, sequence: list[CanonicalEntry], locale: str
) -> None:
    """No value token (parameter, return, exception message) is ever altered by translation."""
    view = TraceTranslationView(glossary)

    rendered = view.render(sequence, locale)

    for entry in sequence:
        if entry.nt_event_type == "method_enter":
            _assert_enter_values_survive(entry, rendered)
        if entry.nt_event_type == "method_exit":
            _assert_exit_values_survive(entry, rendered)
