# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Harvests glossary candidates from captured trace trees.

``GlossaryHarvester`` / ``HarvestCandidate``. INTENT: the v1 harvest sources are method
names (verb phrase plus object noun phrase), parameter names, class names (role suffix stripped),
and exception type names (``Exception``/``Error`` stripped). Observations are aggregated and
deterministically ordered; the harvester makes no merge decisions.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Threw
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import TreeWalk
from narrativetrace_glossary.context_resolver import UNASSIGNED_CONTEXT, resolve_context
from narrativetrace_glossary.models import Glossary, TermKind
from narrativetrace_glossary.normalizer import (
    TermCandidate,
    class_candidate,
    exception_candidate,
    method_candidates,
    parameter_candidate,
)

_TEXT_FIELDS = ("context", "phrase", "site", "identifier")
"""Fields of an observation that must carry text; blank text would name no code and no concept."""


@dataclass(frozen=True, slots=True)
class HarvestCandidate:
    """One aggregated observation of a normalized phrase at a code site.

    The bridge between traces and the glossary: the merger turns unseen ``(context, phrase)`` pairs
    into new terms, alias hits become vocabulary violations, and everything else is usage-report
    material only.
    """

    context: str
    phrase: str
    kind: TermKind
    site: str
    identifier: str
    occurrences: int = 1

    def __post_init__(self) -> None:
        for name in _TEXT_FIELDS:
            value: str = getattr(self, name)
            if not value.strip():
                raise ValueError(f"{name} must not be blank")
        if self.occurrences < 1:
            raise ValueError(f"occurrences must be at least 1: {self.occurrences}")


_KIND_ORDER = {kind: position for position, kind in enumerate(TermKind)}
"""Declaration order of :class:`TermKind`, so candidate ordering matches the Java enum ordinal."""

_Observations = dict[HarvestCandidate, int]
"""Distinct observations mapped to how often each was seen; the key carries ``occurrences=1``."""


def harvest_traces(
    trees: Sequence[TraceTree],
    *,
    glossary: Glossary,
    module_of: Callable[[str], str | None],
) -> tuple[HarvestCandidate, ...]:
    """Harvests every candidate observation from the given trace trees.

    Args:
        trees: trace trees of one run.
        glossary: supplies the bounded contexts observations are filed under.
        module_of: maps a node's simple class name to the dotted module path that declares it;
            an empty string or ``None`` files the observation under ``_unassigned``.

    Returns:
        Aggregated observations ordered by ``(context, phrase, kind, site, identifier)``, so the
        same run always produces the same output.

    Raises:
        TypeError: if ``glossary`` is not a :class:`Glossary` or ``module_of`` is not callable.
    """
    if not isinstance(glossary, Glossary):
        raise TypeError("glossary must be a Glossary")
    if not callable(module_of):
        raise TypeError("module_of must be callable")
    observations: _Observations = {}
    for tree in trees:
        for root in tree.roots:
            _walk(root, observations, glossary, module_of)
    counted = [replace(seen, occurrences=count) for seen, count in observations.items()]
    harvested = tuple(sorted(counted, key=_order))
    assert _invariant(harvested), "a harvest must be totally ordered and free of repeated keys"
    return harvested


def _invariant(candidates: Sequence[HarvestCandidate]) -> bool:
    """Returns whether one harvest's observations are internally consistent.

    Two rules make a harvest reproducible, and both are properties of the *collection* rather than
    of any one candidate: the observations are in the total order :func:`_order` defines, and no
    key repeats — a repeat would mean the same sighting was counted under two entries.
    """
    keys = [_order(candidate) for candidate in candidates]
    return keys == sorted(keys) and len(set(keys)) == len(keys)


def _order(candidate: HarvestCandidate) -> tuple[str, str, int, str, str]:
    """Total order over observations, so output never depends on the order trees were walked in.

    Divergence from Java, whose comparator stops at ``site``: two observations can agree on
    ``(context, phrase, kind, site)`` and differ only in the identifier they were normalized from
    (a method's object noun and a same-named parameter, say). Java breaks that tie by ``HashMap``
    iteration order, so its output churns run over run; adding ``identifier`` makes the key total.
    """
    return (
        candidate.context,
        candidate.phrase,
        _KIND_ORDER[candidate.kind],
        candidate.site,
        candidate.identifier,
    )


def _walk(
    node: TraceNode,
    observations: _Observations,
    glossary: Glossary,
    module_of: Callable[[str], str | None],
    walk: TreeWalk | None = None,
) -> None:
    walk = walk if walk is not None else TreeWalk()
    signature = node.signature
    class_name = signature.class_name
    context = _context_of(class_name, glossary, module_of)
    _harvest_class(context, class_name, observations)
    _harvest_method(context, signature, observations)
    _harvest_parameters(context, signature, observations)
    _harvest_exception(context, node, observations)
    if walk.stop_reason(node) is None:
        walk.enter(node)
        try:
            for child in node.children:
                _walk(child, observations, glossary, module_of, walk)
        finally:
            walk.exit(node)


def _context_of(class_name: str, glossary: Glossary, module_of: Callable[[str], str | None]) -> str:
    """Files a node under the context owning its module; a module nobody can name owns nothing."""
    module_path = module_of(class_name)
    if module_path is None:
        return UNASSIGNED_CONTEXT
    return resolve_context(glossary, module_path)


def _site(signature: MethodSignature) -> str:
    """Where an observation was made: the dotted ``Class.method`` pair naming the invocation."""
    return f"{signature.class_name}.{signature.method_name}"


def _harvest_class(context: str, class_name: str, observations: _Observations) -> None:
    if not class_name.isidentifier():
        return
    _observe(observations, context, class_candidate(class_name), class_name, class_name)


def _harvest_method(context: str, signature: MethodSignature, observations: _Observations) -> None:
    method_name = signature.method_name
    if not method_name.isidentifier():
        return
    for candidate in method_candidates(method_name):
        _observe(observations, context, candidate, _site(signature), method_name)


def _harvest_parameters(
    context: str, signature: MethodSignature, observations: _Observations
) -> None:
    site = _site(signature)
    for parameter in signature.parameters:
        if parameter.name.isidentifier():
            _observe(
                observations, context, parameter_candidate(parameter.name), site, parameter.name
            )


def _harvest_exception(context: str, node: TraceNode, observations: _Observations) -> None:
    """Failure vocabulary: the type name of what a node threw, minus its ``Error``/``Exception``."""
    if not isinstance(node.outcome, Threw):
        return
    type_name = type(node.outcome.exception).__name__
    if not type_name.isidentifier():
        return
    _observe(
        observations, context, exception_candidate(type_name), _site(node.signature), type_name
    )


def _observe(
    observations: _Observations,
    context: str,
    candidate: TermCandidate | None,
    site: str,
    identifier: str,
) -> None:
    """Counts one observation; a candidate normalization dropped entirely contributes nothing."""
    if candidate is None:
        return
    seen = HarvestCandidate(context, candidate.phrase, candidate.kind, site, identifier)
    observations[seen] = observations.get(seen, 0) + 1
