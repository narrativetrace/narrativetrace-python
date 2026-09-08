# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Who a captured tree is: one trace identity, resolved once, shared by every exporter.

``TraceIdentity``. A trace's correlation fields are a property of the
*capture*, not of the serialisation you happen to ask for, so both the chapter exporter
(:mod:`narrativetrace.chapter`) and the canonical mapper (:mod:`narrativetrace.tree_canonical`)
resolve them here. Left to each exporter, a chapter and its own ``.canonical.json`` could name two
different traces for one run — the defect Java found before this rule existed.

The rules, in order:

- **trace_id** — the tree already resolved it (adopt → inherit → generate, see
  :class:`~narrativetrace.tree.TraceTree`); only an *empty* tree arrives without one, and it takes
  a freshly generated id so its chapter still carries the field the schema requires.
- **nt.storyId** — the inherited span context's story, else the first root call's
  ``Class.method``, else :data:`UNKNOWN_CALL`. Never generated.
- **nt.chapterId** — the inherited span context's chapter, else the story.
- **nt.traceName** — derived from the resolved ``trace_id``, so the two cannot disagree.
- **service** — the inherited context's, else ``unknown_service:python``.

"Inherited" is the first span context found anywhere in the tree, depth-first: one tree is one
trace, so a real context at any depth answers for every node, and a node that lost its own context
is never stamped with a second trace id.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.canonical import service_or_unknown
from narrativetrace.ids import TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree

UNKNOWN_CALL = "unknown"
"""Stands in for the first root call's name when a tree has no roots to name it after."""


def root_call_name(roots: list[TraceNode]) -> str:
    """Returns the first root's ``Class.method``, or :data:`UNKNOWN_CALL` for an empty tree.

    The chapter title, the story id and the chapter id of a context-free capture are all this one
    string — deriving them separately is how they drift apart.
    """
    if not roots:
        return UNKNOWN_CALL
    signature = roots[0].signature
    return f"{signature.class_name}.{signature.method_name}"


@dataclass(frozen=True, slots=True)
class TraceIdentity:
    """The correlation fields every exporter of one tree must agree on.

    Build it with :func:`resolve_identity` rather than by hand; the constructor takes already
    resolved values and does not apply the fallback rules.
    """

    inherited: SpanContext | None
    trace_id: TraceId
    story_id: str
    chapter_id: str

    @property
    def trace_name(self) -> str:
        """The human-readable phrase for :attr:`trace_id`, so name and id always agree."""
        return self.trace_id.human_name()

    @property
    def service(self) -> str:
        """The inherited context's service, or ``unknown_service:python`` when nobody named one."""
        name = self.inherited.service_name if self.inherited is not None else None
        return service_or_unknown(name)


def resolve_identity(tree: TraceTree) -> TraceIdentity:
    """Resolves the one identity a tree's exporters share.

    Args:
        tree: The captured tree. Its own ``trace_id`` wins; an empty tree has none and is given a
            fresh one, because the field is required and there are no entries to disagree with it.

    Returns:
        The resolved :class:`TraceIdentity` — every field populated, none of them ``None``.

    Raises:
        ValueError: if ``tree`` is ``None`` — an absent tree is a caller bug, not an empty run.
    """
    if tree is None:
        raise ValueError("tree must not be None")
    inherited = tree.inherited_span_context
    story_id = _story_id(tree, inherited)
    identity = TraceIdentity(
        inherited=inherited,
        trace_id=_trace_id(tree),
        story_id=story_id,
        chapter_id=_chapter_id(inherited, story_id),
    )
    assert identity.story_id and identity.chapter_id, "story and chapter ids are never empty"
    return identity


def _trace_id(tree: TraceTree) -> TraceId:
    """Two rungs, not three: the tree already ran *adopt → inherit → generate* over its nodes, so
    only an empty tree — which has no context to inherit from either — arrives without an id."""
    if tree.trace_id is not None:
        return tree.trace_id
    return TraceId.generate()


def _story_id(tree: TraceTree, inherited: SpanContext | None) -> str:
    if inherited is not None and inherited.story_id is not None:
        return inherited.story_id
    return root_call_name(tree.roots)


def _chapter_id(inherited: SpanContext | None, story_id: str) -> str:
    if inherited is not None and inherited.chapter_id is not None:
        return inherited.chapter_id
    return story_id
