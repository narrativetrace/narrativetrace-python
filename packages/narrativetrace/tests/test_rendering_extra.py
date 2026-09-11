# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Coverage for structured edge paths and flat error/fallback paths of ValueRenderer."""

from __future__ import annotations

import concurrent.futures

from narrativetrace.markers import narrative_summary
from narrativetrace.rendering import ValueRenderer
from narrativetrace.values import IntVal, ListVal, ObjectVal, StringVal


class RogueStr:
    def __str__(self) -> str:
        raise RuntimeError("boom")


class RaisingSummary:
    def __init__(self) -> None:
        self.field = 1

    @narrative_summary
    def summary(self) -> str:
        raise RuntimeError("nope")


class LongStr:
    def __str__(self) -> str:
        return "y" * 50


class TestFlatFallbacks:
    def test_rogue_str_degrades_to_the_typed_error_marker(self) -> None:
        assert ValueRenderer().render(RogueStr()) == "<error: RuntimeError>"

    def test_raising_summary_renders_the_typed_error_marker(self) -> None:
        """A raising ``@narrative_summary`` never falls through to a different rendering (owner
        ruling, 2026-09-11): it renders ``<error: TypeName>`` outright, even though
        ``RaisingSummary`` also carries a plain field that introspection could otherwise show."""
        assert ValueRenderer().render(RaisingSummary()) == "<error: RuntimeError>"

    def test_custom_str_truncated(self) -> None:
        assert ValueRenderer(max_string_length=5).render(LongStr()) == "yyyyy…"


class TestStructuredEdges:
    def test_over_cap_collection(self) -> None:
        result = ValueRenderer(max_collection_items=1).render_structured([1, 2, 3])
        assert result == ListVal([IntVal(1)])

    def test_map_key_redaction(self) -> None:
        result = ValueRenderer().render_structured({"token": "x"})
        assert result == ObjectVal("Map", {'"token"': StringVal("[REDACTED]")})

    def test_cycle_identity_marker(self) -> None:
        cyclic: list[object] = [1]
        cyclic.append(cyclic)
        result = ValueRenderer().render_structured(cyclic)
        assert isinstance(result, ListVal)
        second = result.elements[1]
        assert isinstance(second, StringVal)
        assert second.value.startswith("<list@")

    def test_custom_str_object_becomes_string_val(self) -> None:
        assert ValueRenderer().render_structured(LongStr()) == StringVal("y" * 50)

    def test_pending_future(self) -> None:
        fut: concurrent.futures.Future[int] = concurrent.futures.Future()
        assert ValueRenderer().render_structured(fut) == StringVal("<pending>")

    def test_resolved_future_unwrapped(self) -> None:
        fut: concurrent.futures.Future[int] = concurrent.futures.Future()
        fut.set_result(7)
        assert ValueRenderer().render_structured(fut) == IntVal(7)

    def test_cancelled_future(self) -> None:
        fut: concurrent.futures.Future[int] = concurrent.futures.Future()
        fut.cancel()
        assert ValueRenderer().render_structured(fut) == StringVal("<cancelled>")

    def test_failed_future(self) -> None:
        fut: concurrent.futures.Future[int] = concurrent.futures.Future()
        fut.set_exception(ValueError("x"))
        assert ValueRenderer().render_structured(fut) == StringVal("<failed>")

    def test_awaitable_pending(self) -> None:
        async def coro() -> int:
            return 1

        c = coro()
        try:
            assert ValueRenderer().render_structured(c) == StringVal("<pending>")
        finally:
            c.close()
