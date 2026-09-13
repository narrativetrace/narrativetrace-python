# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`traceparent` parsing benchmark (`poe bench` / `poe bench-gate`).

Home for a genuine performance guard that used to live as a wall-clock assertion in
`narrativetrace-security-tests`' Tier A suite (`oracles.within_budget`, removed 2026-09-13 --
family release rule 3: wall-clock, GC and scheduler are never test inputs). That suite's hostile
corpus (`resources/hostile-corpus/headers.json`, id `very-long-fields`) carries a version-01
header with a hundred thousand extension fields -- valid per the W3C spec, so it must be
**accepted**, which `test_traceparent_properties.py::TestCorpusTraceparents::
test_acceptance_matches_the_corpus_declaration` already pins with no clock involved.

What that removed assertion actually guarded beyond acceptance was parse *cost*: a naive
field-splitting implementation could go quadratic on a hundred thousand fields, and that is a
genuine algorithmic-complexity concern (an attacker-controlled header, one every ASGI request
carries) -- not reducible to a bounded-*output* property the way a renderer's truncating caps are.
`bench-gate` is the family's answer to "assert a performance property without wall-clock ever
being a pass/fail input": it compares this run's mean time against the most recently saved run on
*this machine*, so a slower/shared/loaded host has a slower baseline to match rather than an
absolute cutoff to race. Starter coverage; `poe bench`/`poe bench-gate` are scheduled/on-demand,
never per commit.
"""

from __future__ import annotations

from narrativetrace_asgi import parse_traceparent
from pytest_benchmark.fixture import BenchmarkFixture

_VERY_LONG_FIELDS = "01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" + "-x" * 100_000
"""Mirrors the hostile corpus's `very-long-fields` case exactly (prefix, repeat unit and count)
-- kept as a literal here rather than imported, since `narrativetrace-asgi`'s test suite has no
path to the security-tests package's shared corpus loader."""


class TestParseTraceparent:
    def test_a_hundred_thousand_extension_fields(self, benchmark: BenchmarkFixture) -> None:
        parsed = benchmark(lambda: parse_traceparent(_VERY_LONG_FIELDS))

        assert parsed is not None, "a spec-permitted header must still be accepted"
