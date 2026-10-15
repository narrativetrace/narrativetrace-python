# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A card number (a 13-19 digit, Luhn-valid value) passed to a traced method is redacted BY VALUE
whatever the parameter is called — the checkout recipe's ``charge`` call, with no ``@not_traced``
and a parameter name no deny-list pattern matches.
"""

from __future__ import annotations

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.export import export, export_document
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.render.structural import StructuralTraceRenderer
from narrativetrace.trace_object import trace_object
from narrativetrace.tree import TraceTree

LUHN_VALID = "4111111111111111"
LUHN_INVALID = "4111111111111112"


class Payment:
    """No decorators, and ``reference`` matches no name pattern: only the value can give it away."""

    def charge(self, reference: str, amount_cents: int) -> str:
        return "paid"


def _captured(value: str) -> TraceTree:
    context = ContextVarNarrativeContext()
    trace_object(Payment(), context).charge(value, 1999)
    return context.capture_trace()


def _artifacts(value: str) -> list[str]:
    tree = _captured(value)
    metadata = TraceMetadata("Customer pays", ScenarioResult.SUCCESS)
    return [
        MarkdownRenderer().render_document(tree, metadata),
        IndentedTextRenderer().render(tree),
        ProseRenderer().render(tree),
        StructuralTraceRenderer().render(tree),
        export(tree),
        export_document(tree, metadata),
    ]


class TestACardNumberInAnInnocentlyNamedParameter:
    def test_the_captured_parameter_is_redacted_by_value(self) -> None:
        context = ContextVarNarrativeContext()
        trace_object(Payment(), context).charge(LUHN_VALID, 1999)

        reference, amount = context.capture_trace().roots[0].signature.parameters

        assert (reference.redacted, reference.rendered_value) == (True, "[REDACTED]")
        assert (amount.redacted, amount.rendered_value) == (False, "1999")

    def test_the_number_reaches_no_rendered_artifact(self) -> None:
        artifacts = _artifacts(LUHN_VALID)

        assert not any(LUHN_VALID in artifact for artifact in artifacts)
        assert all("1999" in artifact for artifact in artifacts[:3])

    def test_a_same_length_number_that_fails_the_luhn_check_stays_visible(self) -> None:
        assert LUHN_INVALID in IndentedTextRenderer().render(_captured(LUHN_INVALID))
