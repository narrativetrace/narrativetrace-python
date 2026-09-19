# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Turns a declarative hostile-corpus graph shape (``graphs.json``) into a live Python object
graph. The ``HostileGraphs``/``HostileMembers`` builder -- the corpus README's own words: "the
builder that turns a declarative graph shape into a live object graph is the only per-runtime code."

Several JDK wrapper types this corpus names have no Python analogue this runtime's ``ValueRenderer``
treats specially (no ``Optional``/``AtomicReference``/``AtomicReferenceArray``/``Map.Entry`` type
exists in Python's object model; only ``concurrent.futures.Future`` is special-cased). Mapped onto
the nearest construct that still requires the renderer to descend one level and still goes through
a real, already-tested code path:

* ``optional`` -> a single-element list: this runtime's own idiom for "one item, one level deeper"
  (see ``test_rendering.py``'s ``_wrap``).
* ``atomicReference`` -> ``_Box`` (a one-field dataclass): the nearest opaque single-value holder
  that still goes through object introspection.
* ``atomicReferenceArray`` -> a list: Python has no indexed holder distinct from a list.
* ``entryValue``/``entryKey`` -> ``_Entry`` (a ``NamedTuple``): the nearest "named pair", and a
  ``NamedTuple`` is itself a tested redaction seam here.
* ``list``/``array`` -> a list; ``map`` -> a dict: direct.
* ``record``/``holder`` -> ``_Box``: a dataclass is the closest analogue to a Java record.
* ``future`` -> ``concurrent.futures.Future``: direct, the renderer special-cases this exact type.
* ``mapKey`` (self-in-map-key) -> a fixed-hash proxy referencing the map back: Python dict keys
  must be hashable, so a dict cannot literally be its own key the way a pathological Java
  ``hashCode`` allows.

Four kinds pin native stringification -- the channel where no annotation and no deny-list is ever
consulted, because the type's own ``__str__`` stands in for the walk: ``curatedToString`` (a
composite whose hand-written ``__str__`` interpolates its own deny-listed field),
``curatedToStringNested`` (the same leak one level down, through a holder the outer class merely
prints), ``mapKey`` (that composite used as a dict KEY, where text is hardest to avoid) and
``throwingSummary`` (the one sanctioned curated hook raising, with the secret in the exception's
own message -- the part must render a typed, value-free marker). Their sentinel sits behind a
deny-listed field NAME (``password``) rather than an annotation, which is the corpus README's
documented exception to ``payload: "secret-record"``'s usual planting shape.

Four more kinds (owner ruling, 2026-09-12: the platform-type carve-out) exercise
``ValueRenderer``'s identity test for a type the platform itself defines: ``platformValue`` (a
live ``pathlib.PurePosixPath``, well-formedness only), ``platformNameRedacted`` (the deny-list
by NAME wins before the carve-out is ever consulted), ``platformLookalike`` (a user class named
like a platform type -- identity is never decided by name), and ``platformSubclass`` (a genuine
user subclass of a platform type, walked like any other application type since a subclass's own
``__module__`` is never inherited from its stdlib base).

Two more kinds (owner ruling, 2026-09-18: the abstract-base refinement) exercise the rendering
rule against an ABSTRACT platform base rather than a concrete one: ``abstractMapSubclassOverride``
(a ``collections.abc.Mapping`` subclass whose overridden ``items()`` counts its calls and refuses)
and ``abstractCollectionSubclassOverride`` (the same for ``collections.abc.Collection``'s
``__iter__``). Unlike ``dict``/``list`` -- which carry real backing state the renderer can read
through the platform ancestor -- an abc base stores nothing of its own, so the honest read is
plain object introspection of the subclass's own fields; the override is never the extension
point and must never run.

One more member, ``fieldlessAbstractSubclassToStringDoor`` (master corpus update, 2026-09-18,
gap 2 from pair #5 I's report, mirrors Java's
``HostileMembers.FieldlessAbstractSubclassToStringDoor``): a FIELDLESS subclass of the ABSTRACT
platform base ``collections.abc.Collection``. In Java, ``AbstractCollection`` installs its OWN
``toString()`` that walks ``iterator()`` internally, so a fieldless subclass -- trusted by
``rendersItsOwnString`` to stand behind its own text purely because it declares no field -- still
leaks through that inherited ``toString()``. Checked empirically for this port (there is no
Python analogue to trust or distrust without checking): none of ``collections.abc``'s
``Container``/``Iterable``/``Sized``/``Collection`` overrides ``__str__``/``__repr__`` --
``collections.abc.Collection.__str__ is object.__str__`` holds -- so a fieldless instance's
default stringification is ``object``'s own inert ``<module.ClassName object at 0x...>``, which
never touches ``__iter__``. There is no toString-door in Python's abc hierarchy to close, and the
inference behind the door is gone as well: declaring no field earns a value no trust here, so a
fieldless instance renders as its type name and no string conversion of its own -- inherited or
declared -- is called at all. Mirrors the Java fixture's shape (a class-level, not instance-level,
spy counter: an instance-field spy would defeat the fieldless precondition itself) rather than its
outcome, which does not port.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import pathlib
import time
import uuid
from collections.abc import Callable, Iterator
from concurrent.futures import Future
from typing import NamedTuple

from hostile_corpus import GraphCase

from narrativetrace.markers import (
    NOT_TRACED_METADATA,
    narrative_summary,
    not_traced_field,
)


@dataclasses.dataclass
class SecretRecord:
    """A record with a ``@not_traced`` component -- the plantable sentinel-carrying payload."""

    label: str
    secret: str = not_traced_field(default="")


@dataclasses.dataclass
class _Box:
    value: object = None


class _Entry(NamedTuple):
    key: object
    value: object


@dataclasses.dataclass
class _Node:
    """A ring/self-reference node: a pointer plus a co-located secret."""

    next: object = None
    secret: str = not_traced_field(default="")


class _SelfKeyProxy:
    """See the module docstring's ``mapKey`` row: a fixed-hash stand-in for "the map is its own
    key", which Python's hashability rule forbids literally."""

    __slots__ = ("owner",)

    def __init__(self) -> None:
        self.owner: object = None

    def __hash__(self) -> int:
        return 0


class _DynamicFields:
    """A plain object introspected by ``vars()`` -- lets ``manyFields`` build an arbitrary
    field count without a fixed dataclass definition."""


class _ToStringThrows:
    def __str__(self) -> str:
        raise RuntimeError("hostile toString")


class _ToStringThrowsWithPayload:
    def __init__(self, secret: object) -> None:
        self._secret = secret

    def __str__(self) -> str:
        raise RuntimeError(f"hostile toString: {self._secret}")


class _ToStringRecurses:
    def __str__(self) -> str:
        return str(self)


class _ToStringBlocks:
    def __str__(self) -> str:
        time.sleep(0.05)
        return "slow"


class _ToStringHuge:
    def __str__(self) -> str:
        return "x" * 1_000_000


class _ToStringNull:
    def __str__(self) -> str:
        return None  # type: ignore[return-value]  # noqa: PLE0307


class _NumberHostileToString(int):
    """An ``int`` subclass whose ``__str__`` is a forged narrative line, not a number -- the shape
    ``ValueRenderer``'s numeric fast path used to trust unsanitised because ``int``/``float`` are
    fast-pathed scalar types. Carries a newline (log/Markdown-line forgery), a Markdown fence, JSON
    object structure and the two non-JSON floating-point spellings, all in one payload so a single
    case exercises every renderer's scalar-numeric path at once (mirrors Java
    ``HostileMembers.NumberHostileToString``).

    Scalar, so never introspected field-by-field the way ``_ToStringThrows`` and its siblings are
    -- the redaction oracle does not apply to it, only the structure-forging one does.
    """

    def __str__(self) -> str:
        return '1\n```\n{"outcome": "success"}\nNaN Infinity -Infinity\n```'


class _HashCodeThrows:
    def __hash__(self) -> int:
        raise RuntimeError("hostile hashCode")


class _EqualsThrows:
    def __hash__(self) -> int:
        return 0

    def __eq__(self, other: object) -> bool:
        raise RuntimeError("hostile equals")


@dataclasses.dataclass
class _GetterThrows:
    @property
    def value(self) -> str:
        raise RuntimeError("hostile getter")


@dataclasses.dataclass
class _AccessorThrows:
    @property
    def value(self) -> str:
        raise RuntimeError("hostile accessor")


@dataclasses.dataclass
class _CountingAccessor:
    """Record-accessor analogue for the rendering rule (owner ruling 2026-09-17, "rendering reads
    state, never runs behaviour"): a side effect instead of a failure -- ``held`` counts its own
    calls rather than raising. The target reads the dataclass FIELD ``_held`` directly
    (``dataclasses.fields()`` plus plain ``getattr``), so the counter must never move.

    ``calls`` is ``@not_traced`` so its own rendered text stays the constant ``[REDACTED]`` marker
    rather than a live count -- otherwise two renders of the same instance would print two
    different numbers and this row would counterfeit a failure of the unrelated
    ``test_rendering_a_secret_graph_is_idempotent`` property, which renders every corpus row
    carrying a secret twice and compares the text. Mirrors Java's
    ``HostileMembers.CountingAccessor``."""

    _held: object
    # `dataclasses.field` directly, not the `not_traced_field` wrapper: ruff's RUF009 cannot see
    # through the wrapper to confirm a `default_factory` (rather than a shared mutable `default`)
    # is what is actually being passed, and flags it as an unrecognized mutable default.
    calls: list[int] = dataclasses.field(default_factory=lambda: [0], metadata=NOT_TRACED_METADATA)

    @property
    def held(self) -> object:
        self.calls[0] += 1
        return self._held


class _SideEffectingIteratorList(list[object]):
    """A platform-collection (``list``) subclass whose overridden ``__iter__`` both counts its own
    calls and refuses -- same rule: the target reads ``list``'s own backing state through the
    platform ancestor (``list.__iter__`` bound to this instance), never this override. Mirrors
    Java's ``HostileMembers.SideEffectingIteratorList``."""

    def __init__(self, held: object) -> None:
        super().__init__([held])
        self.iterator_calls = 0

    def __iter__(self) -> Iterator[object]:
        self.iterator_calls += 1
        raise NotImplementedError("__iter__ must never be called by rendering")


class _LookalikeCollection(collections.abc.Collection[object]):
    """A user ``Collection`` implemented from scratch -- not a platform-collection subclass, so it
    carries no platform-ancestor state to fall back on. Same rule: the target must never enumerate
    it by calling its own ``__iter__``; it renders as an object instead. Mirrors Java's
    ``HostileMembers.LookalikeCollection``."""

    def __init__(self, held: object) -> None:
        self._backing = [held]
        self.iterator_calls = 0

    def __iter__(self) -> Iterator[object]:
        self.iterator_calls += 1
        raise NotImplementedError("__iter__ must never be called by rendering")

    def __len__(self) -> int:
        return len(self._backing)

    def __contains__(self, item: object) -> bool:
        return item in self._backing


class _AbstractMapSubclassOverride(collections.abc.Mapping[object, object]):
    """Python's honest twin of Java's ``AbstractMap`` subclass (owner ruling 2026-09-18, the
    abstract-base refinement): a subclass of the ABSTRACT platform base
    ``collections.abc.Mapping``, whose overridden ``items()`` counts its own calls and refuses.
    ``Mapping`` itself has no stored state of its own -- unlike a concrete platform base such as
    ``dict`` -- so the target must read the subclass's OWN ``__dict__`` fields (``label``,
    ``held``) through plain object introspection, never call through to ``items()``. Mirrors
    Java's ``HostileMembers.AbstractMapSubclassOverride``."""

    def __init__(self, held: object) -> None:
        self.label = "abstract-map"
        self.held = held
        self.items_calls = 0

    def __getitem__(self, key: object) -> object:
        raise NotImplementedError

    def __iter__(self) -> Iterator[object]:
        raise NotImplementedError

    def __len__(self) -> int:
        return 0

    def items(self) -> collections.abc.ItemsView[object, object]:
        self.items_calls += 1
        raise NotImplementedError("items() must never be called by rendering")


class _AbstractCollectionSubclassOverride(collections.abc.Collection[object]):
    """Same reasoning for the other ABSTRACT platform base, ``collections.abc.Collection``: an
    overridden ``__iter__`` that counts its own calls and refuses. Mirrors Java's
    ``HostileMembers.AbstractCollectionSubclassOverride``."""

    def __init__(self, held: object) -> None:
        self.label = "abstract-collection"
        self.held = held
        self.iterator_calls = 0

    def __iter__(self) -> Iterator[object]:
        self.iterator_calls += 1
        raise NotImplementedError("__iter__ must never be called by rendering")

    def __len__(self) -> int:
        return 0

    def __contains__(self, item: object) -> bool:
        return False


class _FieldlessAbstractSubclassToStringDoor(collections.abc.Collection[object]):
    """Python's honest twin of Java's fieldless ``AbstractCollection`` subclass (master corpus
    update, 2026-09-18, gap 2 from pair #5 I's report) -- see the module docstring.
    Takes no ``held`` payload, unlike every other ``hostileMember`` fixture: the whole point of
    this shape is to carry zero instance state, and accepting a constructor argument only to
    discard it would still read as a stored field to a careless refactor.

    ``iterator_calls`` is a CLASS attribute, not an instance one, mirroring Java's ``static
    AtomicInteger ITERATOR_CALLS``: an instance-field spy would populate ``__dict__`` and defeat
    the very fieldless precondition (``_has_instance_state`` must stay ``False``) this fixture
    exists to hold. Callers reset it (``iterator_calls = 0`` on the class) before use."""

    iterator_calls: int = 0

    def __iter__(self) -> Iterator[object]:
        type(self).iterator_calls += 1
        raise NotImplementedError("__iter__ must never be called by rendering")

    def __len__(self) -> int:
        return 3

    def __contains__(self, item: object) -> bool:
        return False


@dataclasses.dataclass
class _TokenBox:
    """A field named ``token`` -- the deny-list must win before the platform-type carve-out
    (owner ruling, 2026-09-12) is ever consulted for the value the field holds."""

    token: object = None


class _FakePath:
    """Named like a platform type on purpose: the identity test must never look at a class's OWN
    name, only at where it is actually defined -- this class lives in this security-tests module,
    not ``pathlib``, so it is walked, not trusted, however platform-sounding its name looks."""

    def __init__(self, inner: object) -> None:
        self.inner = inner

    def __str__(self) -> str:
        return f"Path({self.inner})"


class _SubclassedUUID(uuid.UUID):
    """A genuine user subclass of a platform type: a subclass's own ``__module__`` is wherever
    *it* is defined, never inherited from its stdlib base, so it must be walked like any other
    application type carrying state. ``object.__setattr__`` bypasses ``UUID``'s own immutability
    guard, which blocks ordinary attribute assignment even for a subclass-introduced field."""

    inner: object

    def __init__(self, inner: object) -> None:
        super().__init__(int=0)
        object.__setattr__(self, "inner", inner)

    def __str__(self) -> str:
        return f"{super().__str__()}::{self.inner}"


class _CuratedToString:
    """A class with a deny-listed field and a hand-written ``__str__`` that interpolates it: the
    field name says "never show this" and the curated text shows it anyway. Mirrors Java's
    ``HostileMembers.CuratedToString``. Rendering reads STATE (owner ruling 2026-09-17), so this
    ``__str__`` is never the renderer's source of text for a composite."""

    def __init__(self, password: str) -> None:
        self.username = "ada"
        self.password = password

    def __str__(self) -> str:
        return f"Login{{username={self.username}, password={self.password}}}"


class _CuratedToStringNested:
    """No sensitive field of its own; its curated ``__str__`` interpolates a nested holder that
    has one, so the leak is invisible to every name-based test. Deliberately a plain class, not a
    dataclass: a dataclass's generated ``__repr__`` would be a different mechanism than the
    hand-written stringification this row is about. Mirrors Java's
    ``HostileMembers.CuratedToStringNested``."""

    def __init__(self, holder: object) -> None:
        self.session_id = "session-7"
        self.holder = holder

    def __str__(self) -> str:
        return f"Session{{id={self.session_id}, holder={self.holder}}}"


class _SensitiveKey:
    """A composite carrying a deny-listed field, built to be used as a dict KEY -- a key has to
    become text before it is printed, the one place native stringification is hardest to avoid, so
    it carries a curated ``__str__`` too. Hashed by its non-secret field only, so the secret never
    reaches ``hash()`` either. Mirrors ``HostileMembers.SensitiveKey``."""

    def __init__(self, password: str) -> None:
        self.username = "ada"
        self.password = password

    def __hash__(self) -> int:
        return hash(self.username)

    def __str__(self) -> str:
        return f"Key{{username={self.username}, password={self.password}}}"


class _ThrowingSummary:
    """A holder whose ``@narrative_summary`` raises, with the payload in the exception message.
    The summary marker is the one opt-in to curated rendering left, so its failure mode is part of
    the contract: the traced call succeeds, the failed part renders a typed, value-free marker, and
    the message reaches no output. Mirrors ``HostileMembers.ThrowingSummary``."""

    def __init__(self, held: object) -> None:
        self.held = held

    @narrative_summary
    def describe(self) -> str:
        """Never returns; the renderer must degrade to a typed, value-free marker."""
        secret = self.held.secret if isinstance(self.held, SecretRecord) else self.held
        raise RuntimeError(f"cannot summarise {secret}")


def _secret_text(payload: object) -> str:
    return payload.secret if isinstance(payload, SecretRecord) else str(payload)


def _sensitive_map_key(payload: object) -> dict[object, object]:
    return {_SensitiveKey(_secret_text(payload)): "visible-value"}


def _platform_name_redacted(payload: object) -> object:
    return _TokenBox(pathlib.PurePosixPath(f"/var/secrets/{_secret_text(payload)}"))


def _hostile_key_names(payload: object) -> dict[object, object]:
    zero_width, cyrillic_a = chr(0x200B), chr(0x0430)
    return {zero_width: "invisible", f"{cyrillic_a}pikey": payload}


_HOSTILE_MEMBERS: dict[str, Callable[[object], object]] = {
    "toStringThrows": lambda _p: _ToStringThrows(),
    "toStringThrowsWithPayload": _ToStringThrowsWithPayload,
    "toStringRecurses": lambda _p: _ToStringRecurses(),
    "toStringBlocks": lambda _p: _ToStringBlocks(),
    "toStringHuge": lambda _p: _ToStringHuge(),
    "toStringNull": lambda _p: _ToStringNull(),
    "numberHostileToString": lambda _p: _NumberHostileToString(1),
    "hashCodeThrows": lambda _p: _HashCodeThrows(),
    "equalsThrows": lambda _p: _EqualsThrows(),
    "getterThrows": lambda _p: _GetterThrows(),
    "accessorThrows": lambda _p: _AccessorThrows(),
    "hostileKeyNames": _hostile_key_names,
    "countingAccessor": _CountingAccessor,
    "sideEffectingIteratorList": _SideEffectingIteratorList,
    "lookalikeCollection": _LookalikeCollection,
    "abstractMapSubclassOverride": _AbstractMapSubclassOverride,
    "abstractCollectionSubclassOverride": _AbstractCollectionSubclassOverride,
    "fieldlessAbstractSubclassToStringDoor": lambda _p: _FieldlessAbstractSubclassToStringDoor(),
}


def _completed_future(value: object) -> Future[object]:
    future: Future[object] = Future()
    future.set_result(value)
    return future


_LAYER_BUILDERS: dict[str, Callable[[object], object]] = {
    "optional": lambda p: [p],
    "atomicReference": _Box,
    "atomicReferenceArray": lambda p: [p],
    "entryValue": lambda p: _Entry("k", p),
    "entryKey": lambda p: _Entry(p, "v"),
    "list": lambda p: [p],
    "array": lambda p: [p],
    "map": lambda p: {"item": p},
    "record": _Box,
    "future": _completed_future,
    "holder": _Box,
}


def _apply_layers(layers: tuple[str, ...], payload: object) -> object:
    for layer in layers:
        payload = _LAYER_BUILDERS[layer](payload)
    return payload


def _payload_for(case: GraphCase, sentinel: str) -> object:
    if case.payload == "secret-record":
        return SecretRecord("item", sentinel)
    if case.payload == "plain-text":
        return sentinel
    return None


def _width(case: GraphCase, payload: object) -> object:
    n = case.n or 0
    container = case.container or "list"
    if n <= 0:
        return {} if container == "map" else []
    filler = n - 1
    if container == "map":
        entries: dict[object, object] = {f"k{i}": None for i in range(filler)}
        entries[f"k{filler}"] = payload
        return entries
    return [None] * filler + [payload]


def _cycle(n: int, payload: object) -> object:
    nodes = [_Node() for _ in range(max(n, 1))]
    for i, node in enumerate(nodes):
        node.next = nodes[(i + 1) % len(nodes)]
    if isinstance(payload, SecretRecord):
        nodes[0].secret = payload.secret
    return nodes[0]


def _self_in_collection(container: str, payload: object) -> object:
    if container == "map":
        holder: dict[object, object] = {"item": payload}
        holder["self"] = holder
        return holder
    if container == "mapKey":
        proxy = _SelfKeyProxy()
        holder = {proxy: payload}
        proxy.owner = holder
        return holder
    if container == "entry":
        entry = _Box(payload)
        entry.value = _Entry("k", entry)
        return entry
    items: list[object] = [payload]
    items.append(items)
    return items


def _many_fields(n: int, payload: object) -> object:
    obj = _DynamicFields()
    for i in range(max(n - 1, 0)):
        setattr(obj, f"f{i}", i)
    setattr(obj, f"f{max(n - 1, 0)}", payload)
    return obj


def _throwable(case: GraphCase, payload: object) -> BaseException:
    if case.state == "suppressed":
        exc = RuntimeError("primary")
        exc.add_note(str(payload) if payload is not None else "suppressed")
        return exc
    message = payload if isinstance(payload, str) else "exception"
    exc = RuntimeError(message)
    for _ in range(case.n or 0):
        wrapper = RuntimeError("wrapping")
        wrapper.__cause__ = exc
        exc = wrapper
    return exc


_KIND_BUILDERS: dict[str, Callable[[GraphCase, object], object]] = {
    "repeatLayer": lambda c, p: _apply_layers(((c.layer or "holder"),) * (c.n or 0), p),
    "width": _width,
    "cycle": lambda c, p: _cycle(c.n or 1, p),
    "selfInCollection": lambda c, p: _self_in_collection(c.container or "list", p),
    "diamond": lambda c, p: [p, p],
    "hostileMember": lambda c, p: _HOSTILE_MEMBERS[c.member or ""](p),
    "manyFields": lambda c, p: _many_fields(c.n or 0, p),
    "emptyContainers": lambda c, p: [[], {}, [], {"a": []}, [{}]],
    "future": lambda c, p: _future_by_state(c.state or "pending", p),
    "throwable": _throwable,
    "curatedToString": lambda c, p: _CuratedToString(_secret_text(p)),
    "curatedToStringNested": lambda c, p: _CuratedToStringNested(p),
    "mapKey": lambda c, p: _sensitive_map_key(p),
    "throwingSummary": lambda c, p: _ThrowingSummary(p),
    "platformValue": lambda c, p: pathlib.PurePosixPath(f"/var/lib/{p}"),
    "platformNameRedacted": lambda c, p: _platform_name_redacted(p),
    "platformLookalike": lambda c, p: _FakePath(p),
    "platformSubclass": lambda c, p: _SubclassedUUID(p),
}


def _future_by_state(state: str, payload: object) -> Future[object]:
    future: Future[object] = Future()
    if state == "failed":
        future.set_exception(RuntimeError(str(payload)))
    elif state == "cancelled":
        future.cancel()
    return future


def build(case: GraphCase, sentinel: str) -> object:
    """Builds the live object graph ``case`` declares, planting ``sentinel`` wherever the corpus
    says ``payload: "secret-record"`` (or as plain exception-message text for ``"plain-text"``)."""
    payload = _payload_for(case, sentinel)
    if case.layers is not None:
        return _apply_layers(case.layers, payload)
    return _KIND_BUILDERS[case.kind or ""](case, payload)


# ---------------------------------------------------------------------- #
# Template-corpus fixtures (templates.json's ``values`` field)             #
# ---------------------------------------------------------------------- #
# The shared ``HostileGraphs.templateValues`` cases: named object graphs a
# ``TemplateCase`` resolves against, each planting ``sentinel`` at the one
# position its template names.


@dataclasses.dataclass
class _TemplateCard:
    """The dogfood shape: a payment card whose verification code is annotated out of narration."""

    number: str
    cvv: str = not_traced_field(default="")


@dataclasses.dataclass
class _TemplateOrder:
    """A card one level down, so a template can name a redacted segment mid-path."""

    id: str
    card: _TemplateCard


class _Credentials:
    """A bean whose property names the deny-list knows, with no annotation involved -- ``secret``
    matches the deny-list by name exactly as ``password`` does."""

    def __init__(self, name: str, password: str) -> None:
        self.name = name
        self.password = password

    @property
    def secret(self) -> str:
        return self.password


@dataclasses.dataclass
class _DepthFour:
    """The redacted leaf of the ``deep`` template fixture."""

    secret: str = not_traced_field(default="")


@dataclasses.dataclass
class _DepthThree:
    d: _DepthFour


@dataclasses.dataclass
class _DepthTwo:
    c: _DepthThree


@dataclasses.dataclass
class _DepthOne:
    """Four objects deep, so ``{a.b.c.d.secret}`` names a redacted leaf and nothing shorter."""

    b: _DepthTwo


@dataclasses.dataclass
class _TemplateUnicode:
    """A path whose segments are valid identifiers outside ASCII."""

    naïve: str  # noqa: PLC2401 -- the non-ASCII identifier is the case under test
    secret: str = not_traced_field(default="")


@dataclasses.dataclass
class _TemplateWide:
    """A redacted component past ``ValueRenderer``'s five-field cap: the safe rendering truncates
    the component away, so it carries no redaction marker at all -- the shape ``fuzzTemplate``
    found leaking on 2026-09-02."""

    one: str
    two: str
    three: str
    four: str
    five: str
    six: str = not_traced_field(default="")


@dataclasses.dataclass
class _TemplateLink:
    """One link of a chain longer than ``ValueRenderer.MAX_DEPTH``."""

    next: object = None


def _template_chain(sentinel: str) -> object:
    link: object = _TemplateCard("4111", sentinel)
    for _ in range(40):
        link = _TemplateLink(link)
    return link


def _jwt(sentinel: str) -> str:
    """A JWT whose payload segment is the sentinel, so the value axis has a shape to recognise
    and the containment oracle still knows which bytes must not appear. The key holding it is
    ``value``, deliberately a name no deny-list knows -- under ``token`` the name axis would
    answer first and the case would prove nothing about the shape."""
    return f"eyJhbGciOiJIUzI1NiJ9.{sentinel}.c2lnbmF0dXJl"


_TEMPLATE_VALUE_BUILDERS: dict[str, Callable[[str], dict[str, object]]] = {
    "card": lambda s: {"card": _TemplateCard("4111", s)},
    "user": lambda s: {"user": _Credentials("ada", s)},
    "order": lambda s: {"order": _TemplateOrder("order-42", _TemplateCard("4000", s))},
    "deep": lambda s: {"a": _DepthOne(_DepthTwo(_DepthThree(_DepthFour(s))))},
    "unicode": lambda s: {"café": _TemplateUnicode("plain", s)},
    "wide": lambda s: {"wide": _TemplateWide("1", "2", "3", "4", "5", s)},
    "chain": lambda s: {"chain": _template_chain(s)},
    "password-scalar": lambda s: {"password": s},
    "jwt-scalar": lambda s: {"value": _jwt(s)},
    # `newline-scalar` is the one fixture here carrying no sentinel: its value is not secret and
    # is meant to be shown; what must not survive is its raw line break, and a containment oracle
    # cannot say that. The escaping is pinned by the template-parser's own tests.
    "newline-scalar": lambda _s: {"comment": "note" + chr(0x000A) + "## forged"},
}


def template_values(name: str | None, sentinel: str) -> dict[str, object]:
    """Builds the named value map a ``TemplateCase`` resolves against, planting ``sentinel`` at
    the position its template names."""
    builder = _TEMPLATE_VALUE_BUILDERS.get(name or "card")
    if builder is None:
        raise ValueError(f"unknown template fixture: {name}")
    return builder(sentinel)
