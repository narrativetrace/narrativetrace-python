# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier A, target 1: the W3C ``traceparent``/``tracestate`` wire reader.

``TraceparentParsingPropertyTest``. The corpus replays first (so a failure names a
case id), then a generated sweep explores the header alphabet Hypothesis can reach. Oracle:
parsing never throws, and whatever it accepts is well-formed and round-trips.
"""

from __future__ import annotations

import re

import pytest
from fuzz_config import fuzz_settings
from hostile_corpus import HeaderCase, traceparents, tracestates
from hypothesis import given
from hypothesis import strategies as st
from narrativetrace_asgi import format_traceparent, parse_traceparent
from oracles import no_new_threads

from narrativetrace.rendering import ValueRenderer

_TRACE_ID = re.compile(r"[0-9a-f]{32}")
_SPAN_ID = re.compile(r"[0-9a-f]{16}")


def _assert_well_formed(parsed: object) -> None:
    assert parsed is not None
    assert _TRACE_ID.fullmatch(str(parsed.trace_id))  # type: ignore[attr-defined]
    assert _SPAN_ID.fullmatch(str(parsed.span_id))  # type: ignore[attr-defined]
    assert 0 <= parsed.flags <= 0xFF  # type: ignore[attr-defined]


class TestCorpusTraceparents:
    @pytest.mark.parametrize("case", traceparents(), ids=str)
    def test_acceptance_matches_the_corpus_declaration(self, case: HeaderCase) -> None:
        parsed = parse_traceparent(case.value)
        assert (parsed is not None) == case.accepted

    @pytest.mark.parametrize("case", [c for c in traceparents() if c.accepted], ids=str)
    def test_an_accepted_header_is_well_formed(self, case: HeaderCase) -> None:
        _assert_well_formed(parse_traceparent(case.value))

    @pytest.mark.parametrize("case", [c for c in traceparents() if c.accepted], ids=str)
    def test_an_accepted_header_round_trips_the_identity_it_carries(self, case: HeaderCase) -> None:
        parsed = parse_traceparent(case.value)
        assert parsed is not None
        reformatted = format_traceparent(parsed.trace_id, parsed.span_id, sampled=parsed.sampled)
        reparsed = parse_traceparent(reformatted)
        assert reparsed is not None
        assert reparsed.trace_id == parsed.trace_id
        assert reparsed.span_id == parsed.span_id
        assert reparsed.sampled == parsed.sampled

    # `very-long-fields` (a hundred thousand extension fields, spec-permitted so it must be
    # ACCEPTED) is exercised for correctness by `test_acceptance_matches_the_corpus_declaration`
    # above like every other corpus case. It used to also carry a dedicated wall-clock assertion
    # here (`oracles.within_budget`) -- removed 2026-09-13 (family release rule 3: wall-clock, GC
    # and scheduler are never test inputs). The parse-*cost* property that assertion actually
    # guarded is genuine (an attacker-controlled header on every request; a naive splitter could
    # go quadratic on a hundred thousand fields) but not reducible to a bounded-output property,
    # so it now lives as a `pytest-benchmark` case in the benchmark lane instead:
    # `narrativetrace-asgi/tests/test_bench_traceparent.py` (`poe bench`/`poe bench-gate`, never
    # part of the per-commit gate).

    def test_parsing_starts_no_background_thread(self) -> None:
        case = next(c for c in traceparents() if c.id == "valid-v00")
        no_new_threads(lambda: parse_traceparent(case.value))


class TestCorpusTracestates:
    """This runtime carries ``tracestate`` as an opaque value -- it is never parsed, only rendered
    (Java: ``everyCorpusTracestateSurvivesBeingCarriedAsAValue``)."""

    @pytest.mark.parametrize("case", tracestates(), ids=str)
    def test_a_tracestate_value_renders_without_crashing(self, case: HeaderCase) -> None:
        assert isinstance(ValueRenderer().render(case.value), str)


_HEADER_ALPHABET = st.sampled_from([*"0123456789abcdef-z \n", chr(0x0664)])
_HEADER_SHAPED = st.text(alphabet=_HEADER_ALPHABET, max_size=60)


@st.composite
def _well_formed_header(draw: st.DrawFn) -> str:
    trace_id = draw(st.text(alphabet="0123456789abcdef", min_size=32, max_size=32))
    span_id = draw(st.text(alphabet="0123456789abcdef", min_size=16, max_size=16))
    flags = draw(st.text(alphabet="0123456789abcdef", min_size=2, max_size=2))
    if trace_id == "0" * 32 or span_id == "0" * 16:
        trace_id = "1" + trace_id[1:]
    return f"00-{trace_id}-{span_id}-{flags}"


class TestGeneratedHeaders:
    @fuzz_settings
    @given(_HEADER_SHAPED)
    def test_parsing_never_throws_whatever_the_header_contains(self, header: str) -> None:
        parse_traceparent(header)

    @fuzz_settings
    @given(st.text(max_size=200))
    def test_parsing_never_throws_on_arbitrary_text(self, header: str) -> None:
        parse_traceparent(header)

    @fuzz_settings
    @given(_well_formed_header())
    def test_what_the_parser_accepts_is_always_well_formed(self, header: str) -> None:
        parsed = parse_traceparent(header)
        if parsed is not None:
            _assert_well_formed(parsed)

    @fuzz_settings
    @given(_well_formed_header())
    def test_what_the_parser_accepts_always_round_trips(self, header: str) -> None:
        parsed = parse_traceparent(header)
        if parsed is None:
            return
        reformatted = format_traceparent(parsed.trace_id, parsed.span_id, sampled=parsed.sampled)
        reparsed = parse_traceparent(reformatted)
        assert reparsed is not None
        assert reparsed.trace_id == parsed.trace_id
        assert reparsed.span_id == parsed.span_id
