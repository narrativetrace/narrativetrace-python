# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A redacted attribute never appears in any rendered artifact, at any depth or through any
container shape (the template-resolution family). Values are rendered once at capture (the
Contract-Augmented TDD convention), so every renderer/exporter here reads the same pre-rendered
strings -- this pins the containment property at the artifact level rather than trusting that
architecture claim alone.
"""

from __future__ import annotations

from typing import NamedTuple

from narrativetrace.chapter import export_chapter
from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.export import export, export_document
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.trace_object import trace_object
from narrativetrace.tree_canonical import export_canonical_entries

SECRET = "hunter2-do-not-leak"


class Card(NamedTuple):
    number: str
    cvv: str


Card.__nt_not_traced__ = ("cvv",)  # type: ignore[attr-defined]


class PaymentService:
    def charge(self, card: Card, amount: int) -> bool:
        return True


def _every_artifact(secret: str) -> list[str]:
    context = ContextVarNarrativeContext()
    trace_object(PaymentService(), context).charge(Card("4111", secret), 500)
    tree = context.capture_trace()
    metadata = TraceMetadata("Customer pays", ScenarioResult.SUCCESS)

    return [
        MarkdownRenderer().render_document(tree, metadata),
        IndentedTextRenderer().render(tree),
        ProseRenderer().render(tree),
        export(tree),
        export_document(tree, metadata),
        export_canonical_entries(tree),
        export_chapter(tree, metadata),
    ]


class TestRedactedValueContainment:
    def test_a_named_tuple_secret_reaches_no_rendered_artifact(self) -> None:
        artifacts = _every_artifact(SECRET)

        assert artifacts, "the test must actually produce artifacts to assert anything"
        assert not any(SECRET in artifact for artifact in artifacts)

    def test_the_redaction_marker_reaches_every_artifact_instead(self) -> None:
        artifacts = _every_artifact(SECRET)

        assert all("[REDACTED]" in artifact for artifact in artifacts)


class UnnamedCard(NamedTuple):
    number: str
    note: str  # an ordinary, unmarked field -- only the value's shape hides it


class UnlabeledPaymentService:
    def charge(self, card: UnnamedCard, amount: int) -> bool:
        return True


_PAN = "4111111111111111"


class TestValueShapeMaskingContainment:
    """Adversarial-audit mirror (2026-09-02): a PAN-shaped value must not reach any rendered
    artifact even under a field name (``note``) that matches no name-based pattern -- only the
    value's own structure hides it."""

    def _every_artifact_with_pan_in_note(self) -> list[str]:
        context = ContextVarNarrativeContext()
        trace_object(UnlabeledPaymentService(), context).charge(UnnamedCard("4111", _PAN), 500)
        tree = context.capture_trace()
        metadata = TraceMetadata("Customer pays", ScenarioResult.SUCCESS)

        return [
            MarkdownRenderer().render_document(tree, metadata),
            IndentedTextRenderer().render(tree),
            ProseRenderer().render(tree),
            export(tree),
            export_document(tree, metadata),
            export_canonical_entries(tree),
            export_chapter(tree, metadata),
        ]

    def test_a_pan_shaped_value_under_an_unmarked_field_reaches_no_rendered_artifact(self) -> None:
        artifacts = self._every_artifact_with_pan_in_note()

        assert artifacts, "the test must actually produce artifacts to assert anything"
        assert not any(_PAN in artifact for artifact in artifacts)

    def test_the_redaction_marker_reaches_every_artifact_instead(self) -> None:
        artifacts = self._every_artifact_with_pan_in_note()

        assert all("[REDACTED]" in artifact for artifact in artifacts)
