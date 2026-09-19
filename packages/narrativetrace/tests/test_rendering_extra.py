# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Coverage for structured edge paths and flat error/fallback paths of ValueRenderer."""

from __future__ import annotations

import concurrent.futures
from enum import Enum

from narrativetrace.markers import narrative_summary
from narrativetrace.rendering import ValueRenderer
from narrativetrace.values import IntVal, ListVal, ObjectVal, StringVal


class RogueStr(Enum):
    """An enum member's own string conversion is one of the two rendering may call, so a hostile
    one is a real hazard here -- unlike a fieldless plain class's, which is never called at all
    (see ``TestFieldlessValueIsNeverDescribedByItsOwnText``)."""

    ONE = "one"

    def __str__(self) -> str:
        raise RuntimeError("boom")


class RaisingSummary:
    def __init__(self) -> None:
        self.field = 1

    @narrative_summary
    def summary(self) -> str:
        raise RuntimeError("nope")


class LongStr(Enum):
    """Long text from a conversion rendering does call, so the string cap has something to cap."""

    ONE = "one"

    def __str__(self) -> str:
        return "y" * 50


class TestFlatFallbacks:
    def test_rogue_str_degrades_to_the_typed_error_marker(self) -> None:
        assert ValueRenderer().render(RogueStr.ONE) == "<error: RuntimeError>"

    def test_a_fieldless_classs_rogue_str_is_never_called_at_all(self) -> None:
        class Fieldless:
            def __str__(self) -> str:
                raise RuntimeError("boom")

        assert ValueRenderer().render(Fieldless()) == "<Fieldless>"

    def test_raising_summary_renders_the_typed_error_marker(self) -> None:
        """A raising ``@narrative_summary`` never falls through to a different rendering (owner
        ruling, 2026-09-11): it renders ``<error: TypeName>`` outright, even though
        ``RaisingSummary`` also carries a plain field that introspection could otherwise show."""
        assert ValueRenderer().render(RaisingSummary()) == "<error: RuntimeError>"

    def test_custom_str_truncated(self) -> None:
        assert ValueRenderer(max_string_length=5).render(LongStr.ONE) == "yyyyy…"


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
        assert ValueRenderer().render_structured(LongStr.ONE) == StringVal("y" * 50)

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
