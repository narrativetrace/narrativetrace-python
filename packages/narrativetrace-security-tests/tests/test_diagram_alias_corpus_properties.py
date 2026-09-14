# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Mermaid's alias mode, driven by a class name -- the one route the shared hostile corpus never
reached before.

``mermaid-aliases`` has been in :data:`emitters.EMITTERS` since the corpus itself was built, so
every corpus *value* already drove ``render_with_aliases`` through the captured-value and
narration routes (``test_output_format_properties.py``, ``test_injection_containment_properties.
py``). What no per-commit test ever did was drive it through the *metadata* route -- a hostile
string as the class name itself, the only field
:func:`narrativetrace_diagrams.text.alias_token` ever turns into a bare, unquoted token. Only the
budgeted, non-per-commit Hypothesis/atheris sweep exercised that route, which is exactly why a
class literally named ``end`` slipped through: the corpus ran every commit and never once tried
it (found in the Java reference, 2026-09-13, mirrored here).

The oracle here is stricter than well-formedness alone: a well-formed diagram happily accepts a
participant line whose alias happens to be a Mermaid keyword, because well-formedness only checks
the *shape* of a ``participant`` statement, not what Mermaid's own grammar reserves -- ``end``
matches ``[A-Za-z0-9_]+`` just as well as ``end_`` does. Three assertions pin the actual contract:
(1) exactly one participant line per distinct class -- a collision silently merging two different
classes into one participant would still be well formed; (2) every alias token contains only
``[A-Za-z0-9_]``, Mermaid's own bare-token grammar; and (3) no alias token, lowercased, equals a
Mermaid sequence-diagram keyword. The reserved-word set below is kept *independent* of
``narrativetrace_diagrams.text``'s own set rather than imported -- a test that asks production
code for the very list it is being checked against cannot fail when that list is wrong.
"""

from __future__ import annotations

import re

import pytest
from hostile_corpus import CorpusCase, strings
from narrativetrace_diagrams.mermaid import MermaidSequenceDiagramRenderer

from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree

_BARE_ALIAS_TOKEN = re.compile(r"[A-Za-z0-9_]+")
_CORPUS_PREFIX = "diagram-alias-"

# Independently sourced from `sequenceDiagram.jison` (mermaid-js/mermaid, verified 2026-09-13),
# the same way `narrativetrace_diagrams.text` documents its own set -- see that module for the
# per-keyword lexer-rule citations.
_MERMAID_RESERVED_ALIASES = frozenset(
    {
        "sequencediagram",
        "participant",
        "actor",
        "create",
        "destroy",
        "box",
        "loop",
        "rect",
        "opt",
        "alt",
        "else",
        "par",
        "par_over",
        "and",
        "critical",
        "option",
        "break",
        "end",
        "links",
        "link",
        "properties",
        "details",
        "over",
        "note",
        "activate",
        "deactivate",
        "autonumber",
        "off",
        "title",
    }
)

_renderer = MermaidSequenceDiagramRenderer()


def _one_class_tree(class_name: str) -> TraceTree:
    node = TraceNode(MethodSignature(class_name, "run", []), [], Returned("true"))
    return TraceTree([node])


def _two_class_tree(caller_class_name: str, target_class_name: str) -> TraceTree:
    child = TraceNode(MethodSignature(target_class_name, "run", []), [], Returned("true"))
    root = TraceNode(MethodSignature(caller_class_name, "call", []), [child], Returned("true"))
    return TraceTree([root])


def _participant_lines(diagram: str) -> list[str]:
    return [
        line.strip() for line in diagram.splitlines() if line.strip().startswith("participant ")
    ]


def _assert_participant_count_and_clean_aliases(diagram: str, expected_participants: int) -> None:
    participant_lines = _participant_lines(diagram)
    assert len(participant_lines) == expected_participants, (
        f"exactly one participant line per distinct class: {diagram!r}"
    )
    for line in participant_lines:
        alias = line.removeprefix("participant ").split(" as ", 1)[0]
        assert _BARE_ALIAS_TOKEN.fullmatch(alias), (
            f"a participant alias containing anything but [A-Za-z0-9_]: {line!r}"
        )
        assert alias.lower() not in _MERMAID_RESERVED_ALIASES, (
            f"a participant alias that is a bare Mermaid keyword: {line!r}"
        )


_ALIAS_CORPUS_IDS = [c.id for c in strings() if c.id.startswith(_CORPUS_PREFIX)]


class TestDiagramAliasCorpusRows:
    def test_the_expected_corpus_rows_are_actually_present(self) -> None:
        # The property below silently tests nothing if a rename ever drops these ids.
        assert _ALIAS_CORPUS_IDS == [
            "diagram-alias-arrow",
            "diagram-alias-quote-collision",
            "diagram-alias-reserved-word",
            "diagram-alias-empty",
        ]

    @pytest.mark.parametrize(
        "case", [c for c in strings() if c.id.startswith(_CORPUS_PREFIX)], ids=str
    )
    def test_every_diagram_alias_corpus_case_produces_a_safe_participant(
        self, case: CorpusCase
    ) -> None:
        diagram = _renderer.render_with_aliases(_one_class_tree(case.value))
        _assert_participant_count_and_clean_aliases(diagram, 1)


def test_quote_and_apostrophe_class_names_that_sanitize_to_the_same_alias_stay_distinct_participants() -> (  # noqa: E501
    None
):
    # The collision `diagram-alias-quote-collision` names but cannot exercise alone: two
    # *different* classes (`a"b` and `a'b`) whose aliases sanitize to the same bare token (`ab`).
    # Disambiguation must still keep them as two participants, never silently merge them into one.
    diagram = _renderer.render_with_aliases(_two_class_tree('a"b', "a'b"))
    _assert_participant_count_and_clean_aliases(diagram, 2)
