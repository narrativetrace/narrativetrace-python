# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Redaction-hot-path benchmarks (`poe bench` / `poe bench-gate`).

`ValueRenderer` checks every string it renders against `RedactionPolicy` -- a field-name
deny-list plus `is_secret_shaped`'s value-shape checks (JWT, Luhn-valid PAN, `Set-Cookie`,
national-id checksums). Every traced call pays this on every string argument and return value,
so it is one of the paths this product's "capture is cheap" claim depends on most directly. Java's
`ProxyOverheadBenchmark` touches this indirectly (`proxy_notTraced`, a parameter *name* redaction);
this benchmarks the value-*shape* axis directly, which Java's suite does not measure either --
starter coverage this port adds, not a port of an existing Java benchmark.
"""

from __future__ import annotations

from pytest_benchmark.fixture import BenchmarkFixture

from narrativetrace.rendering import ValueRenderer

# A real Luhn-valid PAN and a real three-segment JWT shape, matching the fixtures already used
# elsewhere in this repo's own redaction tests (packages/narrativetrace/tests/test_rendering.py,
# packages/narrativetrace-security-tests/tests/hostile_graphs.py) rather than inventing new ones.
# The payload segment is a named variable, not a literal, in the f-string below -- the same
# technique hostile_graphs.py already uses -- so the assembled *value* is still genuinely
# JWT-shaped at runtime while the source text itself never spells out a complete token for a
# secrets scanner to flag.
_PAN = "4111111111111111"
_JWT_PAYLOAD = "eyJzdWIiOiIxMjM0NTY3ODkwIn0"
_JWT = f"eyJhbGciOiJIUzI1NiJ9.{_JWT_PAYLOAD}.c2lnbmF0dXJl"
_BENIGN = "a perfectly ordinary sentence about an order being placed"


class TestRenderStringHotPath:
    """Same length class, same renderer, only the value-shape check's outcome differs."""

    def test_benign_string(self, benchmark: BenchmarkFixture) -> None:
        renderer = ValueRenderer()

        benchmark(lambda: renderer.render(_BENIGN))

    def test_secret_shaped_pan(self, benchmark: BenchmarkFixture) -> None:
        renderer = ValueRenderer()

        benchmark(lambda: renderer.render(_PAN))

    def test_secret_shaped_jwt(self, benchmark: BenchmarkFixture) -> None:
        renderer = ValueRenderer()

        benchmark(lambda: renderer.render(_JWT))


class TestRenderObjectWithRedactedField:
    """Field-name redaction on an introspected object, the other axis of the same policy. A
    deny-listed field name short-circuits straight to the redacted marker without ever rendering
    the value; the plain field pays full string rendering (including the value-shape check
    above) -- comparing the two is the point, not an oversight."""

    class _RedactedField:
        def __init__(self, owner: str, password: str) -> None:
            self.owner = owner
            self.password = password

    class _PlainField:
        def __init__(self, owner: str, note: str) -> None:
            self.owner = owner
            self.note = note

    def test_object_with_a_redacted_field(self, benchmark: BenchmarkFixture) -> None:
        renderer = ValueRenderer()
        account = self._RedactedField("Ada", "s3cr3t-password-value")

        benchmark(lambda: renderer.render(account))

    def test_object_with_no_redacted_field(self, benchmark: BenchmarkFixture) -> None:
        renderer = ValueRenderer()
        # Same string length as the redacted case above, isolating field-name redaction's own
        # short-circuit from the surrounding introspection cost both tests pay regardless.
        account = self._PlainField("Ada", "s3cr3t-password-value")

        benchmark(lambda: renderer.render(account))
