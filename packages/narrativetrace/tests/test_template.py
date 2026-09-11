# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the annotation template parser/resolver."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from narrativetrace import template as template_module
from narrativetrace.markers import narrative_summary, not_traced_field
from narrativetrace.template import find_unresolved, resolve


@dataclass
class Order:
    total: int

    @property
    def label(self) -> str:
        return "big"

    def broken(self) -> str:
        raise RuntimeError("no")


class TestSimplePlaceholder:
    def test_unquoted_substitution(self) -> None:
        assert resolve("Greeting {name}", {"name": "Alice"}) == "Greeting Alice"

    def test_numbers_stringified(self) -> None:
        assert resolve("qty {n}", {"n": 3}) == "qty 3"

    def test_none_arg_preserves_literal(self) -> None:
        assert resolve("Greeting {name}", {"name": None}) == "Greeting {name}"

    def test_missing_key_preserves_literal(self) -> None:
        assert resolve("Greeting {name}", {}) == "Greeting {name}"

    def test_multiple_and_literals(self) -> None:
        assert resolve("{a}-{b}!", {"a": "x", "b": "y"}) == "x-y!"


class TestPropertyPlaceholder:
    def test_attribute_access(self) -> None:
        assert resolve("total {o.total}", {"o": Order(5)}) == "total 5"

    def test_property_access(self) -> None:
        assert resolve("{o.label}", {"o": Order(5)}) == "big"

    def test_missing_object_preserves_literal(self) -> None:
        assert resolve("{o.total}", {"o": None}) == "{o.total}"

    def test_missing_property_preserves_literal(self) -> None:
        assert resolve("{o.nope}", {"o": Order(5)}) == "{o.nope}"

    def test_raising_accessor_preserves_literal(self) -> None:
        assert resolve("{o.broken}", {"o": Order(5)}) == "{o.broken}"


@dataclass
class Card:
    number: str
    cvv: str = not_traced_field(default="")


@dataclass
class Order2:
    id: str
    card: Card | None


@dataclass
class Payment:
    __nt_not_traced__ = ("card",)

    id: str
    card: Card | None


class Login:
    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password


class TestRedactedPathResolution:
    """Template-resolution family: a path reaching a redacted member resolves to
    `[REDACTED]`, at every depth — naming a path never weakens the value's own rules."""

    def test_a_template_naming_a_redacted_field_renders_the_marker(self) -> None:
        result = resolve("charging {card.cvv}", {"card": Card("4111", "123")})

        assert result == "charging [REDACTED]"
        assert "123" not in result

    def test_the_deny_list_redacts_an_unannotated_property_by_name_alone(self) -> None:
        result = resolve("login {user.password}", {"user": Login("jsmith", "hunter2")})

        assert result == "login [REDACTED]"
        assert "hunter2" not in result

    def test_a_redacted_segment_at_the_end_of_a_nested_path_renders_the_marker(self) -> None:
        order = Order2("o-1", Card("4111", "123"))

        result = resolve("charging {order.card.cvv}", {"order": order})

        assert result == "charging [REDACTED]"
        assert "123" not in result

    def test_a_redacted_segment_in_the_middle_of_a_path_renders_the_marker(self) -> None:
        payment = Payment("p-1", Card("4111", "123"))

        result = resolve("charging {payment.card.number}", {"payment": payment})

        assert result == "charging [REDACTED]"
        assert "4111" not in result

    def test_an_unredacted_nested_path_still_survives_literally(self) -> None:
        """Nested *resolution* stays unsupported; only the redaction check walks the whole path."""
        order = Order2("o-1", Card("4111", "123"))

        assert resolve("card {order.card.number}", {"order": order}) == "card {order.card.number}"

    def test_a_placeholder_naming_no_parameter_stays_literal(self) -> None:
        assert resolve("charging {custmer.cvv}", {}) == "charging {custmer.cvv}"

    def test_a_property_the_owner_does_not_declare_stays_literal(self) -> None:
        result = resolve("order {order.password}", {"order": Order2("o-1", None)})

        assert result == "order {order.password}"


class Amount:
    """The same value as a plain class rather than a dataclass. Before the 2026-09-11 family fix
    this class's own ``__str__`` stood (a plain object with no ``__str__`` override was the only
    one introspected); now any object carrying instance state is introspected regardless of a
    custom ``__str__`` -- see ``test_a_plain_object_with_fields_narrates_structurally_too``
    below."""

    def __init__(self, currency: str, units: int) -> None:
        self.currency = currency
        self.units = units

    def __str__(self) -> str:
        return f"{self.currency} {self.units}.00"


@dataclass
class Priced:
    """A dataclass that names its own narration the supported way."""

    currency: str
    amount: int

    @narrative_summary
    def summary(self) -> str:
        return f"{self.currency} {self.amount}.00"


@dataclass
class Wide:
    """A dataclass whose redacted component sits past ``ValueRenderer``'s five-field cap: the
    safe rendering truncates it away, so the safe rendering carries no redaction marker at all.

    A security fuzz suite finding (the same defect class every runtime pins, 2026-09-02): the bug
    class this pins is the inference "no marker in the safe rendering" => "nothing is hidden, the
    value's own str()/repr() may stand". A truncated render has not seen the whole value, so it
    cannot answer that question either way.
    """

    one: str
    two: str
    three: str
    four: str
    five: str
    six: str = not_traced_field(default="")


@dataclass
class Node:
    """One link of a chain longer than ``ValueRenderer.MAX_DEPTH``."""

    next: object = None


class TestWholeObjectPlaceholderRedaction:
    """A security fuzz suite finding (fixed 2026-09-02): a whole-object placeholder (``{card}``,
    naming the object rather than a path into it) used to render the value's own
    ``str()``/``repr()`` unconditionally -- bypassing redaction entirely, since only the
    ``{card.cvv}`` *path* form ever consulted :func:`narrativetrace.redacted_paths.redacts`.
    Every non-scalar placeholder value now renders through
    :class:`~narrativetrace.rendering.ValueRenderer`, the one renderer that knows
    what is hidden, with no fallback to the value's own text."""

    def test_a_whole_object_placeholder_redacts_a_not_traced_field(self) -> None:
        result = resolve("charging {card}", {"card": Card("4111", "topsecret")})

        assert "topsecret" not in result
        assert "[REDACTED]" in result

    def test_a_plain_object_with_fields_narrates_structurally_too(self) -> None:
        """2026-09-11 family fix: a plain object exposing instance state is introspected
        field-by-field regardless of a custom ``__str__`` -- ``Amount``'s hand-written formatting
        is never consulted, the same as ``Card``/``Order`` above. Only a genuine leaf (no
        instance state at all) still trusts its own ``str()``."""
        result = resolve("transfer {amount}", {"amount": Amount("EUR", 10)})

        assert result == 'transfer Amount(currency="EUR", units=10)'

    def test_a_dataclass_narrates_structurally_rather_than_through_its_own_str(self) -> None:
        """Where the ruling stops: a *dataclass* narrates structurally (``ValueRenderer`` always
        introspects dataclasses), so a hand-written ``__str__`` on one is not consulted here --
        matching how the very same value is already rendered for traced arguments."""
        result = resolve("charging {card}", {"card": Card("4111", "123")})

        assert result == 'charging Card(number="4111", cvv=[REDACTED])'

    def test_a_narrative_summary_chooses_the_bytes_for_a_dataclass(self) -> None:
        result = resolve("transfer {amount}", {"amount": Priced("EUR", 10)})

        assert result == "transfer EUR 10.00"

    def test_a_redacted_component_past_the_renderers_field_cap_is_not_narrated_by_str(
        self,
    ) -> None:
        wide = Wide("1", "2", "3", "4", "5", "topsecret")

        result = resolve("audit {row}", {"row": wide})

        assert "topsecret" not in result

    def test_a_redacted_leaf_deeper_than_the_renderers_depth_cap_is_not_narrated_by_str(
        self,
    ) -> None:
        chain: object = Card("4111", "topsecret")
        for _ in range(40):
            chain = Node(chain)

        result = resolve("audit {row}", {"row": chain})

        assert "topsecret" not in result


class Rogue:
    """A value whose rendering blows up — a lazy proxy over a closed session, say."""

    def __str__(self) -> str:
        raise ValueError("__str__ exploded")


class NonStrStr:
    """``__str__`` returning a non-``str`` raises TypeError — the analogue of a null toString()."""

    def __str__(self) -> str:
        # noqa/ignore deliberate: this IS the defect under test — Python raises TypeError at the
        # call site when __str__ returns a non-str, which is what the guard must absorb.
        return None  # type: ignore[return-value]  # noqa: PLE0307


class Recursive:
    """A self-referential ``__str__`` — the analogue of Java's StackOverflowError case."""

    def __str__(self) -> str:
        return str(self)


class Wrapper:
    def __init__(self, value: object) -> None:
        self.value = value


class RogueNumber(int):
    """A ``Number`` subclass whose own ``__str__`` misbehaves -- a scalar goes straight to
    ``_scalar_text`` rather than through ``ValueRenderer``, so it needs its own hostile guard."""

    def __str__(self) -> str:
        raise ValueError("__str__ exploded")


class HostileNumber(int):
    """An ``int`` subclass whose ``__str__`` forges control characters/Markdown structure instead
    of throwing -- the scalar fast path must sanitise this, not merely survive it."""

    def __str__(self) -> str:
        return "1\n## forged\n"


class HostileEnum(Enum):
    ONE = "one"

    def __str__(self) -> str:
        return "one\n## forged\n"


class TestRogueStr:
    """``Rogue``/``NonStrStr``/``Recursive`` carry no instance state, so they stay leaves that
    trust ``str()`` (see ``ValueRenderer._has_instance_state``) -- routed here through
    :class:`~narrativetrace.rendering.ValueRenderer` (a non-scalar placeholder value always is),
    which degrades a raising leaf to the typed error marker (owner ruling, 2026-09-11):
    ``<error: <ExceptionTypeName>>``, never the value's own type name or the exception's message.
    """

    def test_simple_placeholder_degrades_to_typed_error_marker(self) -> None:
        assert (
            resolve("Processing {payload}", {"payload": Rogue()})
            == "Processing <error: ValueError>"
        )

    def test_a_scalar_whose_str_throws_degrades_to_type_marker(self) -> None:
        result = resolve("count {n}", {"n": RogueNumber(7)})

        assert result == "count <RogueNumber>"

    def test_property_placeholder_degrades_to_typed_error_marker(self) -> None:
        assert (
            resolve("Processing {w.value}", {"w": Wrapper(Rogue())})
            == "Processing <error: ValueError>"
        )

    def test_non_str_return_degrades_to_typed_error_marker(self) -> None:
        assert (
            resolve("Processing {payload}", {"payload": NonStrStr()})
            == "Processing <error: TypeError>"
        )

    def test_recursive_str_degrades_to_type_marker(self) -> None:
        assert (
            resolve("Processing {payload}", {"payload": Recursive()})
            == "Processing <error: RecursionError>"
        )

    def test_other_placeholders_still_resolve_around_a_rogue_value(self) -> None:
        values = {"payload": Rogue(), "id": 7}
        assert resolve("{id}: {payload}", values) == "7: <error: ValueError>"


class TestHostileScalarSanitizing:
    """Cross-runtime mirror (2026-09-04) of the Java ``TemplateParser`` ``instanceof Number ||
    Boolean`` scalar fast path bypassing ``ControlEscape``: this runtime's ``_scalar_text`` called
    bare ``str(value)`` for every scalar, so a hostile ``int``/``Enum`` subclass could inject a
    raw newline plus Markdown structure straight into resolved narration text, unsanitised."""

    def test_a_hostile_int_subclass_is_sanitised_not_trusted(self) -> None:
        result = resolve("count {n}", {"n": HostileNumber(1)})
        assert "\n" not in result
        assert "\\n" in result

    def test_a_hostile_enum_is_sanitised(self) -> None:
        result = resolve("status {s}", {"s": HostileEnum.ONE})
        assert "\n" not in result
        assert "\\n" in result

    def test_a_trusted_int_is_still_stringified_plainly(self) -> None:
        assert resolve("qty {n}", {"n": 3}) == "qty 3"


class TestEmptyPathSegment:
    """A security fuzz suite finding: Java's ``findAccessor`` indexed ``property.charAt(0)``
    with no empty-string guard, so a trailing/leading/doubled dot in a template path (an ordinary
    authoring typo) raised ``StringIndexOutOfBoundsException`` from the redaction walk, which
    calls it directly and bypasses the normal resolver's broad catch.

    Verified this runtime does **not** share the bug: ``_resolve_segment``'s ``getattr(owner, "")``
    already raises (caught) rather than indexing the empty string, so every corpus shape below
    already resolves to nothing instead of throwing. No production change; these pin the already-
    correct behaviour so a future refactor of ``template.py``/``redacted_paths.py`` cannot
    reintroduce the empty-segment crash."""

    def test_a_trailing_dot_resolves_to_nothing_instead_of_throwing(self) -> None:
        result = resolve("charging {card.}", {"card": Card("4111", "123")})
        assert result == "charging {card.}"

    def test_a_doubled_dot_resolves_to_nothing_instead_of_throwing(self) -> None:
        result = resolve("{card..cvv}", {"card": Card("4111", "123")})
        assert result == "{card..cvv}"

    def test_a_leading_dot_resolves_to_nothing_instead_of_throwing(self) -> None:
        result = resolve("{.cvv}", {"card": Card("4111", "123")})
        assert result == "{.cvv}"

    def test_a_path_that_is_only_a_separator_resolves_to_nothing_instead_of_throwing(
        self,
    ) -> None:
        assert resolve("{.}", {"card": Card("4111", "123")}) == "{.}"


class TestFindUnresolved:
    def test_finds_remaining_placeholders(self) -> None:
        assert find_unresolved("Greeting {name} and {other}") == ["name", "other"]

    def test_none_returns_empty(self) -> None:
        assert find_unresolved(None) == []

    def test_fully_resolved_returns_empty(self) -> None:
        assert find_unresolved("Greeting Alice") == []


class TestParseCacheIsBounded:
    """Adversarial-audit mirror (2026-09-02): the parsed-template cache is a process-lifetime
    dict keyed by a caller-supplied string (the template text) with no eviction, so resolving an
    unbounded number of distinct templates grows it without limit.
    """

    def test_resolving_many_distinct_templates_does_not_grow_the_cache_unbounded(self) -> None:
        for i in range(10_000):
            resolve(f"template {i} {{n}}", {"n": i})
        assert template_module._parse.cache_info().currsize <= 512

    def test_a_template_evicted_from_the_cache_still_resolves_correctly(self) -> None:
        resolve("hot {n}", {"n": "first"})
        for i in range(10_000):
            resolve(f"flood {i} {{n}}", {"n": i})
        assert resolve("hot {n}", {"n": "second"}) == "hot second"


class TestScalarPlaceholderRedactionAxes:
    """A bare ``{key}`` placeholder obeys both redaction axes (2026-09-04 family security fix):
    the key is asked of the deny-list exactly like a path segment, and text content renders
    through ``ValueRenderer.render_narration_text`` — value-shape redaction, control
    sanitising, the string cap — minus a captured string's quotation marks."""

    _JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZGEifQ.c2lnbmF0dXJl"

    def test_a_scalar_placeholder_naming_a_secret_is_redacted_like_a_field(self) -> None:
        resolved = resolve("login {password}", {"password": "hunter2"})
        assert resolved == "login [REDACTED]"
        assert "hunter2" not in resolved

    def test_a_credential_shaped_scalar_is_redacted_whatever_its_placeholder_is_called(
        self,
    ) -> None:
        resolved = resolve("issued {value}", {"value": self._JWT})
        assert resolved == "issued [REDACTED]"

    def test_a_text_placeholder_cannot_forge_a_line_with_a_raw_control_character(self) -> None:
        resolved = resolve("note: {comment}", {"comment": "ok\n## forged\r\x00"})
        assert "\n" not in resolved
        assert resolved == "note: ok\\n## forged\\r\\u0000"

    def test_a_text_placeholder_is_capped_the_way_a_captured_string_is(self) -> None:
        resolved = resolve("body {payload}", {"payload": "x" * 500})
        assert resolved == "body " + "x" * 200 + "…"

    def test_a_hostile_str_subclass_is_redacted_by_its_content_not_its_str(self) -> None:
        class Sneaky(str):
            def __str__(self) -> str:  # the content, not the lie, is what renders
                return "innocent"

        assert resolve("issued {value}", {"value": Sneaky(self._JWT)}) == "issued [REDACTED]"

    def test_a_secret_placeholder_with_no_value_stays_literal_so_the_typo_warning_survives(
        self,
    ) -> None:
        assert resolve("login {password}", {}) == "login {password}"

    def test_a_key_that_merely_contains_a_secret_word_is_redacted_too(self) -> None:
        assert resolve("using {api_token}", {"api_token": "tok-9"}) == "using [REDACTED]"

    def test_an_ordinary_scalar_placeholder_is_untouched_by_either_axis(self) -> None:
        assert resolve("order {order_id}", {"order_id": "ORD-7"}) == "order ORD-7"
