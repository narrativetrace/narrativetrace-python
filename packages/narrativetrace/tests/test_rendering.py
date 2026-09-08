# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the ValueRenderer flat and structured rendering paths."""

from __future__ import annotations

import concurrent.futures
import dataclasses
import locale
from enum import Enum
from typing import NamedTuple

import pytest
from hypothesis import given
from hypothesis import strategies as st

from narrativetrace.markers import narrative_summary, not_traced_field
from narrativetrace.redaction import RedactionPolicy
from narrativetrace.rendering import ValueRenderer
from narrativetrace.values import (
    BoolVal,
    FloatVal,
    IntVal,
    ListVal,
    NullVal,
    ObjectVal,
    RenderedValue,
    StringVal,
)


@pytest.fixture
def renderer() -> ValueRenderer:
    return ValueRenderer()


class Color(Enum):
    RED = "red"


@dataclasses.dataclass
class Account:
    username: str
    password: str  # redacted by name
    balance: int


@dataclasses.dataclass
class Marked:
    shown: int
    hidden: str = not_traced_field(default="x")


class Plain:
    def __init__(self) -> None:
        self.a = 1
        self.token = "leak"


class WithStr:
    def __str__(self) -> str:
        return "custom-repr"


class CardTuple(NamedTuple):
    number: str
    cvv: str


CardTuple.__nt_not_traced__ = ("cvv",)  # type: ignore[attr-defined]


class PlainPair(NamedTuple):
    x: int
    y: int


class Summarised:
    def __init__(self) -> None:
        self.big = "x" * 1000

    @narrative_summary
    def summary(self) -> str:
        return "concise"


class TestPrimitives:
    def test_none(self, renderer: ValueRenderer) -> None:
        assert renderer.render(None) == "null"

    def test_string_is_quoted(self, renderer: ValueRenderer) -> None:
        assert renderer.render("hi") == '"hi"'

    def test_string_truncated_with_ellipsis(self) -> None:
        r = ValueRenderer(max_string_length=3)
        assert r.render("abcdef") == '"abc…"'

    def test_control_chars_sanitised(self, renderer: ValueRenderer) -> None:
        assert renderer.render("a\nb") == '"a\\nb"'

    def test_numbers(self, renderer: ValueRenderer) -> None:
        assert renderer.render(42) == "42"
        assert renderer.render(1.5) == "1.5"

    def test_bool_before_int(self, renderer: ValueRenderer) -> None:
        assert renderer.render(True) == "True"

    def test_enum(self, renderer: ValueRenderer) -> None:
        assert renderer.render(Color.RED) == "Color.RED"


class _HostileInt(int):
    def __str__(self) -> str:
        return "1\n## forged\n"


class _HostileFloat(float):
    def __str__(self) -> str:
        return "1.0\n## forged\n"


class _HostileEnum(Enum):
    RED = "red"

    def __str__(self) -> str:
        return "red\n## forged\n"


class _ThrowingInt(int):
    def __str__(self) -> str:
        raise RuntimeError("boom")


class TestHostileScalarSubclasses:
    """A security-suite finding (fixed 2026-09-04): ``renderScalar``'s trusted numeric/enum fast
    path is an ``isinstance`` check, so an ``int``/``float`` subclass or a plain ``Enum``
    overriding ``__str__`` matched it and skipped ``control_sanitize`` entirely -- a value like
    this could inject a raw newline plus Markdown structure into narrative text. Only the literal
    built-in ``int``/``float`` (never a subclass) is fast-pathed; everything else routes through
    the same sanitizer a string does."""

    def test_a_hostile_int_subclass_is_sanitised_not_trusted(self, renderer: ValueRenderer) -> None:
        rendered = renderer.render(_HostileInt(1))
        assert "\n" not in rendered
        assert "\\n" in rendered

    def test_a_hostile_float_subclass_is_sanitised_not_trusted(
        self, renderer: ValueRenderer
    ) -> None:
        rendered = renderer.render(_HostileFloat(1.0))
        assert "\n" not in rendered
        assert "\\n" in rendered

    def test_a_hostile_enum_is_sanitised(self, renderer: ValueRenderer) -> None:
        rendered = renderer.render(_HostileEnum.RED)
        assert "\n" not in rendered
        assert "\\n" in rendered

    def test_a_trusted_int_is_not_run_through_the_sanitiser(self, renderer: ValueRenderer) -> None:
        assert renderer.render(42) == "42"

    def test_a_numeric_subclass_whose_str_throws_degrades_to_the_type_marker(
        self, renderer: ValueRenderer
    ) -> None:
        assert renderer.render(_ThrowingInt(1)) == "<_ThrowingInt>"

    def test_structured_hostile_int_subclass_becomes_a_sanitised_string_val(
        self, renderer: ValueRenderer
    ) -> None:
        result = renderer.render_structured(_HostileInt(1))
        assert result == StringVal("1\\n## forged\\n")

    def test_structured_hostile_float_subclass_becomes_a_sanitised_string_val(
        self, renderer: ValueRenderer
    ) -> None:
        result = renderer.render_structured(_HostileFloat(1.0))
        assert result == StringVal("1.0\\n## forged\\n")

    def test_structured_hostile_enum_becomes_a_sanitised_string_val(
        self, renderer: ValueRenderer
    ) -> None:
        result = renderer.render_structured(_HostileEnum.RED)
        assert result == StringVal("red\\n## forged\\n")

    def test_structured_trusted_int_still_becomes_int_val(self, renderer: ValueRenderer) -> None:
        assert renderer.render_structured(3) == IntVal(3)


class TestCollections:
    def test_list(self, renderer: ValueRenderer) -> None:
        assert renderer.render([1, 2, 3]) == "[1, 2, 3]"

    def test_tuple_and_strings(self, renderer: ValueRenderer) -> None:
        assert renderer.render(("a", "b")) == '["a", "b"]'

    def test_over_cap_shows_total(self) -> None:
        r = ValueRenderer(max_collection_items=2)
        assert r.render([1, 2, 3, 4]) == "[1, 2, … (4 total)]"


class TestMaps:
    def test_entries_rendered_with_equals(self, renderer: ValueRenderer) -> None:
        assert renderer.render({"a": 1}) == "{a=1}"

    def test_key_name_redaction(self, renderer: ValueRenderer) -> None:
        assert renderer.render({"password": "hunter2"}) == "{password=[REDACTED]}"

    def test_over_cap_truncation_marker(self) -> None:
        r = ValueRenderer(max_collection_items=1)
        assert r.render({"a": 1, "b": 2}) == "{a=1, …}"


class TestObjects:
    def test_dataclass_introspected_with_redaction(self, renderer: ValueRenderer) -> None:
        rendered = renderer.render(Account("alice", "hunter2", 100))
        assert rendered == 'Account(username="alice", password=[REDACTED], balance=100)'

    def test_field_marker_redacts(self, renderer: ValueRenderer) -> None:
        assert renderer.render(Marked(1)) == "Marked(shown=1, hidden=[REDACTED])"

    def test_plain_object_introspected(self, renderer: ValueRenderer) -> None:
        assert renderer.render(Plain()) == "Plain(a=1, token=[REDACTED])"

    def test_custom_str_takes_precedence(self, renderer: ValueRenderer) -> None:
        assert renderer.render(WithStr()) == "custom-repr"

    def test_object_default_str_does_not_count_as_custom(self, renderer: ValueRenderer) -> None:
        assert renderer.render(Plain()).startswith("Plain(")

    def test_over_cap_object_fields(self) -> None:
        r = ValueRenderer(max_object_fields=1)
        assert r.render(Account("a", "b", 1)) == 'Account(username="a", …)'

    def test_narrative_summary_hook(self, renderer: ValueRenderer) -> None:
        assert renderer.render(Summarised()) == "concise"


class TestNamedTuples:
    """Template-resolution family: a NamedTuple is a tuple, so it used to fall into the anonymous
    positional collection path (`[..., ...]`) instead of field-name-aware introspection -- the
    same class of bug as Java's wrapper toString() leaks, opened one container deep."""

    def test_fields_render_by_name_not_position(self, renderer: ValueRenderer) -> None:
        assert renderer.render(PlainPair(1, 2)) == "PlainPair(x=1, y=2)"

    def test_a_redacted_field_is_hidden(self, renderer: ValueRenderer) -> None:
        rendered = renderer.render(CardTuple("4111", "123"))
        assert rendered == 'CardTuple(number="4111", cvv=[REDACTED])'
        assert "123" not in rendered

    def test_over_cap_object_fields(self) -> None:
        r = ValueRenderer(max_object_fields=1)
        assert r.render(PlainPair(1, 2)) == "PlainPair(x=1, …)"


class Wrapper(NamedTuple):
    """A container stack layer with no field of its own worth redacting."""

    inner: object


_SECRET = "s3cr3t-value"
_CONTAINER_STACK = st.lists(
    st.sampled_from(["list", "dict", "named_tuple"]), min_size=0, max_size=4
)


def _wrap(layers: list[str], payload: object) -> object:
    for layer in reversed(layers):
        if layer == "list":
            payload = [payload]
        elif layer == "dict":
            payload = {"item": payload}
        else:
            payload = Wrapper(payload)
    return payload


class TestNamedTupleContainmentProperty:
    """Pins the bug class, not just the reported instance: a redacted field must survive an
    arbitrary stack of ordinary containers wrapped around the NamedTuple that carries it."""

    @given(_CONTAINER_STACK)
    def test_a_redacted_field_never_survives_any_container_stack(self, layers: list[str]) -> None:
        renderer = ValueRenderer()
        wrapped = _wrap(layers, CardTuple("4111", _SECRET))

        rendered = renderer.render(wrapped)

        assert _SECRET not in rendered
        assert "[REDACTED]" in rendered


class TestCycles:
    def test_self_referential_list_gets_identity_marker(self, renderer: ValueRenderer) -> None:
        cyclic: list[object] = [1]
        cyclic.append(cyclic)
        rendered = renderer.render(cyclic)
        assert rendered.startswith("[1, <list@")
        assert rendered.endswith(">]")


class TestFutures:
    def test_pending_future(self, renderer: ValueRenderer) -> None:
        fut: concurrent.futures.Future[int] = concurrent.futures.Future()
        assert renderer.render(fut) == "<pending>"

    def test_resolved_future_unwrapped(self, renderer: ValueRenderer) -> None:
        fut: concurrent.futures.Future[int] = concurrent.futures.Future()
        fut.set_result(7)
        assert renderer.render(fut) == "7"

    def test_cancelled_future(self, renderer: ValueRenderer) -> None:
        fut: concurrent.futures.Future[int] = concurrent.futures.Future()
        fut.cancel()
        assert renderer.render(fut) == "<cancelled>"

    def test_failed_future(self, renderer: ValueRenderer) -> None:
        fut: concurrent.futures.Future[int] = concurrent.futures.Future()
        fut.set_exception(ValueError("boom"))
        assert renderer.render(fut) == "<failed>"

    def test_awaitable_pending(self, renderer: ValueRenderer) -> None:
        async def coro() -> int:
            return 1

        c = coro()
        try:
            assert renderer.render(c) == "<pending>"
        finally:
            c.close()


class TestDisabledPolicy:
    def test_annotation_survives_disabled_policy(self) -> None:
        r = ValueRenderer(redaction_policy=RedactionPolicy.DISABLED)
        # name-based redaction off, but the explicit field marker still redacts
        assert r.render(Marked(1)) == "Marked(shown=1, hidden=[REDACTED])"

    def test_name_redaction_off_under_disabled(self) -> None:
        r = ValueRenderer(redaction_policy=RedactionPolicy.DISABLED)
        assert r.render({"password": "hunter2"}) == '{password="hunter2"}'


class TestStructured:
    def test_scalars(self, renderer: ValueRenderer) -> None:
        assert renderer.render_structured(None) == NullVal()
        assert renderer.render_structured(True) == BoolVal(True)
        assert renderer.render_structured(3) == IntVal(3)
        assert renderer.render_structured(1.5) == FloatVal(1.5)
        assert renderer.render_structured("x") == StringVal("x")

    def test_list(self, renderer: ValueRenderer) -> None:
        assert renderer.render_structured([1, 2]) == ListVal([IntVal(1), IntVal(2)])

    def test_object(self, renderer: ValueRenderer) -> None:
        result = renderer.render_structured(Account("alice", "hunter2", 100))
        assert result == ObjectVal(
            "Account",
            {
                "username": StringVal("alice"),
                "password": StringVal("[REDACTED]"),
                "balance": IntVal(100),
            },
        )

    def test_map(self, renderer: ValueRenderer) -> None:
        assert renderer.render_structured({"a": 1}) == ObjectVal("Map", {"a": IntVal(1)})

    def test_named_tuple_redacts_a_marked_field(self, renderer: ValueRenderer) -> None:
        result = renderer.render_structured(CardTuple("4111", "123"))
        assert result == ObjectVal(
            "CardTuple", {"number": StringVal("4111"), "cvv": StringVal("[REDACTED]")}
        )


class TestValueShapeMaskingParity:
    """Adversarial-audit mirror (2026-09-02): a secret-shaped value must be masked on both
    render paths, under an innocuous field name, since divergence between the flat and structured
    paths is this repository's documented top bug source (the Contract-Augmented TDD convention)."""

    _PAN = "4111111111111111"

    def test_flat_path_masks_a_pan_shaped_value_under_an_ordinary_field_name(
        self, renderer: ValueRenderer
    ) -> None:
        assert renderer.render({"orderNumber": self._PAN}) == "{orderNumber=[REDACTED]}"

    def test_structured_path_masks_a_pan_shaped_value_under_an_ordinary_field_name(
        self, renderer: ValueRenderer
    ) -> None:
        result = renderer.render_structured({"orderNumber": self._PAN})
        assert result == ObjectVal("Map", {"orderNumber": StringVal("[REDACTED]")})

    def test_flat_path_leaves_a_luhn_invalid_order_number_visible(
        self, renderer: ValueRenderer
    ) -> None:
        assert renderer.render("4111111111111112") == '"4111111111111112"'

    def test_structured_path_leaves_a_luhn_invalid_order_number_visible(
        self, renderer: ValueRenderer
    ) -> None:
        assert renderer.render_structured("4111111111111112") == StringVal("4111111111111112")

    def test_disabled_policy_leaves_a_pan_shaped_value_visible_on_both_paths(self) -> None:
        r = ValueRenderer(redaction_policy=RedactionPolicy.DISABLED)
        assert r.render(self._PAN) == f'"{self._PAN}"'
        assert r.render_structured(self._PAN) == StringVal(self._PAN)


class TestLocaleInvariance:
    def test_numbers_never_use_grouping_separators(self) -> None:
        # f-strings / str() are locale-independent in Python (unlike the .NET runtime's culture
        # bug); a big number never gains a thousands separator.
        renderer = ValueRenderer()
        assert renderer.render(1000000) == "1000000"
        assert renderer.render(1234567.5) == "1234567.5"

    def test_number_rendering_identical_under_forced_locale(self) -> None:
        renderer = ValueRenderer()
        baseline = renderer.render(1234567.89)
        try:
            locale.setlocale(locale.LC_ALL, "de_DE.UTF-8")
        except locale.Error:
            pytest.skip("de_DE.UTF-8 locale not available")
        try:
            assert renderer.render(1234567.89) == baseline
            assert renderer.render(1000000) == "1000000"
        finally:
            locale.setlocale(locale.LC_ALL, "C")


@st.composite
def _json_like(draw: st.DrawFn) -> object:
    return draw(
        st.recursive(
            st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(),
            lambda children: (
                st.lists(children, max_size=4)
                | st.dictionaries(st.text(max_size=5), children, max_size=4)
            ),
            max_leaves=15,
        )
    )


def _nest_lists(depth: int, payload: object) -> object:
    """Wraps ``payload`` in ``depth`` list layers, innermost first."""
    for _ in range(depth):
        payload = [payload]
    return payload


class TestDepthLimiting:
    """A security-suite finding (mirrors Java's deep-graph stack overflow, fixed in
    ``ValueRenderer``/``RenderWalk``): an identity-based cycle guard never trips on a linear
    chain, so unbounded recursion crashed `render()` with an uncaught `RecursionError` on a
    10,000-deep container chain -- Python's analogue of Java's uncaught `StackOverflowError`."""

    def test_a_ten_thousand_deep_list_chain_does_not_overflow_the_stack(
        self, renderer: ValueRenderer
    ) -> None:
        rendered = renderer.render(_nest_lists(10_000, 0))
        assert isinstance(rendered, str)

    def test_a_ten_thousand_deep_dict_chain_does_not_overflow_the_stack(
        self, renderer: ValueRenderer
    ) -> None:
        deep: object = 0
        for _ in range(10_000):
            deep = {"nxt": deep}
        assert isinstance(renderer.render(deep), str)

    def test_exactly_at_the_cap_renders_whole_with_no_marker(self, renderer: ValueRenderer) -> None:
        rendered = renderer.render(_nest_lists(ValueRenderer.MAX_DEPTH, 0))
        assert "<max-depth>" not in rendered

    def test_one_past_the_cap_shows_the_marker(self, renderer: ValueRenderer) -> None:
        rendered = renderer.render(_nest_lists(ValueRenderer.MAX_DEPTH + 1, 0))
        assert "<max-depth>" in rendered

    def test_a_redacted_component_below_the_cap_still_redacts(
        self, renderer: ValueRenderer
    ) -> None:
        rendered = renderer.render(_nest_lists(5, Marked(1)))
        assert "[REDACTED]" in rendered

    def test_a_secret_beyond_the_cap_is_never_leaked(self, renderer: ValueRenderer) -> None:
        deep_secret = _nest_lists(ValueRenderer.MAX_DEPTH + 5, CardTuple("4111", _SECRET))
        rendered = renderer.render(deep_secret)
        assert _SECRET not in rendered

    def test_the_cap_is_per_sibling_not_shared(self, renderer: ValueRenderer) -> None:
        shallow = Account("alice", "hunter2", 100)
        rendered = renderer.render([_nest_lists(ValueRenderer.MAX_DEPTH + 5, 0), shallow])
        assert '"alice"' in rendered
        assert "<max-depth>" in rendered

    def test_structured_path_also_caps_depth(self, renderer: ValueRenderer) -> None:
        result = renderer.render_structured(_nest_lists(ValueRenderer.MAX_DEPTH + 1, 0))
        assert "<max-depth>" in repr(result)


class TestNoCrashProperty:
    @given(_json_like())
    def test_render_never_crashes_and_is_sanitised(self, value: object) -> None:
        out = ValueRenderer().render(value)
        assert isinstance(out, str)
        assert not any(ord(c) <= 0x1F or 0x7F <= ord(c) <= 0x9F for c in out)

    @given(_json_like())
    def test_render_structured_never_crashes(self, value: object) -> None:
        assert isinstance(ValueRenderer().render_structured(value), RenderedValue)
