# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Detects generic or meaningless identifier tokens (data, info, temp, obj, foo).

``GenericTokenDetector`` — word lists byte-identical to the Java source. The tier maps
to a specificity score: meaningless 0.0, vague 0.2, typed-generic 0.5, not-generic 1.0.
"""

from __future__ import annotations

from enum import Enum

from narrativetrace_clarity.vocabulary import EMPTY, DomainVocabulary

_MEANINGLESS_PLACEHOLDERS = frozenset(
    {
        "foo",
        "bar",
        "baz",
        "qux",
        "quux",
        "temp",
        "tmp",
        "test",
        "dummy",
        "sample",
        "example",
        "xxx",
        "yyy",
        "zzz",
        "todo",
        "fixme",
    }
)

_VAGUE_WORDS = frozenset(
    {
        "data",
        "info",
        "object",
        "thing",
        "item",
        "element",
        "stuff",
        "result",
        "response",
        "output",
        "input",
        "value",
        "content",
        "payload",
        "resource",
        "record",
        "entry",
        "detail",
        "details",
        "entity",
        "bean",
        "model",
        "wrapper",
        "holder",
        "container",
        "bundle",
        "batch",
        "chunk",
        "block",
        "piece",
        "part",
        "unit",
        "instance",
        "param",
        "argument",
        "body",
        "obj",
        "val",
        "arg",
        "meta",
        "metadata",
        "blob",
        "document",
        "artifact",
        "messagebody",
        "dataset",
        "modeloutput",
        "modelinput",
    }
)

_TYPED_GENERIC_WORDS = frozenset(
    {
        "id",
        "name",
        "type",
        "status",
        "state",
        "count",
        "size",
        "length",
        "index",
        "key",
        "flag",
        "code",
        "text",
        "message",
        "label",
        "number",
        "amount",
        "total",
        "level",
        "mode",
        "kind",
        "category",
        "group",
        "list",
        "map",
        "set",
        "queue",
        "stack",
        "array",
        "collection",
        "table",
        "row",
        "column",
        "field",
        "property",
        "tag",
        "version",
        "timestamp",
        "date",
        "time",
        "duration",
        "interval",
        "timeout",
        "limit",
        "offset",
        "page",
        "sort",
        "order",
        "direction",
        "position",
        "priority",
        "weight",
        "rank",
        "score",
        "rating",
        "percentage",
        "ratio",
        "factor",
        "coefficient",
        "path",
        "url",
        "uri",
        "host",
        "port",
        "endpoint",
        "topic",
        "channel",
        "session",
        "token",
        "trace",
        "metric",
        "tenant",
    }
)


class Tier(Enum):
    """Generic-ness tiers, worst first."""

    MEANINGLESS = "MEANINGLESS"
    VAGUE = "VAGUE"
    TYPED_GENERIC = "TYPED_GENERIC"
    NOT_GENERIC = "NOT_GENERIC"


_TIER_SCORES = {
    Tier.MEANINGLESS: 0.0,
    Tier.VAGUE: 0.2,
    Tier.TYPED_GENERIC: 0.5,
    Tier.NOT_GENERIC: 1.0,
}


def detect(token: str, vocabulary: DomainVocabulary = EMPTY) -> tuple[Tier, float]:
    """Returns the (tier, specificity score) for a token.

    Meaningless placeholders are decided first, so committing ``temp`` or ``foo`` to a glossary
    cannot make them meaningful. Every other tier yields to the project: a declared noun is domain
    vocabulary by definition.
    """
    lower = token.lower()
    if _is_meaningless_single_letter(lower) or lower in _MEANINGLESS_PLACEHOLDERS:
        return Tier.MEANINGLESS, _TIER_SCORES[Tier.MEANINGLESS]
    if vocabulary.is_domain_noun(lower):
        return Tier.NOT_GENERIC, _TIER_SCORES[Tier.NOT_GENERIC]
    if lower in _VAGUE_WORDS:
        return Tier.VAGUE, _TIER_SCORES[Tier.VAGUE]
    if lower in _TYPED_GENERIC_WORDS:
        return Tier.TYPED_GENERIC, _TIER_SCORES[Tier.TYPED_GENERIC]
    return Tier.NOT_GENERIC, _TIER_SCORES[Tier.NOT_GENERIC]


def _is_meaningless_single_letter(lower: str) -> bool:
    return len(lower) == 1 and "a" <= lower <= "z"
