# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A function/method PARAMETER whose name alone matches the always-on deny-list is redacted --
with no ``@not_traced`` anywhere. Confirmed defect: ``trace_object._build_capture`` decided
redaction only from the explicit ``@not_traced`` decorator (``name in meta.not_traced_params``)
and never asked ``RedactionPolicy``/``should_redact`` at all, so ``process_payment(self, ...,
payment_token)`` rendered the token in cleartext everywhere -- Markdown, prose, JSON, the value
map templates read -- despite README.md/privacy-and-redaction.md promising an always-on deny-list
that "matches field **and parameter names**".

Every fixture here is deliberately undecorated: the pre-existing "redacted parameter" tests
(``test_trace_object.py``'s ``TestRedaction``, ``test_capture_identity.py``) all pair the
deny-listed name with an explicit ``@not_traced(...)``, which only ever proved the decorator
works. Do not add ``@not_traced`` to any fixture in this module -- that would defeat the point.
"""

from __future__ import annotations

from narrativetrace.chapter import export_chapter
from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.export import export, export_document
from narrativetrace.redaction import RedactionPolicy
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.rendering import ValueRenderer
from narrativetrace.signature import ParameterCapture
from narrativetrace.trace_object import trace_object
from narrativetrace.tree_canonical import export_canonical_entries

SECRET = "secret_payment_token_abc123"


class PaymentService:
    """No decorators anywhere -- every redaction here must come from the name-based deny-list
    alone."""

    def process_payment(self, policy_id: str, amount_cents: int, payment_token: str) -> bool:
        return True

    def process_payment_camel(self, policyId: str, amountCents: int, paymentToken: str) -> bool:
        return True

    def login(self, username: str, password: str) -> bool:
        return True

    def place_order(self, order_number: str, quantity: int) -> bool:
        return True

    def apply_internal_code(self, internal_code: str) -> bool:
        return True


def _capture_params(context: ContextVarNarrativeContext) -> dict[str, ParameterCapture]:
    return {p.name: p for p in context.capture_trace().roots[0].signature.parameters}


class TestParameterNameRedactedByDenyListAlone:
    """The confirmed leak: a parameter named for a secret, with no ``@not_traced``."""

    def test_password_parameter_is_redacted_by_name_alone(self) -> None:
        context = ContextVarNarrativeContext()
        trace_object(PaymentService(), context).login("bob", "hunter2")

        params = _capture_params(context)
        assert params["password"].redacted is True
        assert params["password"].rendered_value == "[REDACTED]"
        assert params["password"].structured_value is None

    def test_snake_case_payment_token_parameter_is_redacted_by_name_alone(self) -> None:
        context = ContextVarNarrativeContext()
        trace_object(PaymentService(), context).process_payment("plan-1", 500, SECRET)

        params = _capture_params(context)
        assert params["payment_token"].redacted is True
        assert params["payment_token"].rendered_value == "[REDACTED]"

    def test_camel_case_payment_token_parameter_is_redacted_by_name_alone(self) -> None:
        context = ContextVarNarrativeContext()
        trace_object(PaymentService(), context).process_payment_camel("plan-1", 500, SECRET)

        params = _capture_params(context)
        assert params["paymentToken"].redacted is True
        assert params["paymentToken"].rendered_value == "[REDACTED]"

    def test_ordinary_parameters_stay_visible(self) -> None:
        """Guard against over-redaction -- must pass both before and after the fix."""
        context = ContextVarNarrativeContext()
        trace_object(PaymentService(), context).place_order("ORD-42", 3)

        params = _capture_params(context)
        assert params["order_number"].redacted is False
        assert params["order_number"].rendered_value == '"ORD-42"'
        assert params["quantity"].redacted is False
        assert params["quantity"].rendered_value == "3"

    def test_self_is_never_captured_or_redacted(self) -> None:
        context = ContextVarNarrativeContext()
        trace_object(PaymentService(), context).login("bob", "hunter2")

        params = _capture_params(context)
        assert "self" not in params


class TestBuiltInVocabularyIsAFloorApplicationCodeCannotLower:
    """Monotonicity (owner ruling): every redaction mechanism, at every stage, may only WIDEN the
    redacted set, never narrow it. ``RedactionPolicy.of_patterns(...)`` replaces the built-in
    vocabulary entirely for its caller (``RedactionPolicy.DEFAULT`` is not consulted by
    ``should_redact`` on the resulting instance), and that policy reaches capture directly via
    ``ValueRenderer(redaction_policy=...)`` passed to ``trace_object(..., renderer=...)`` -- a
    public, reachable path. Without a floor, a caller who builds a narrower policy (by replacing
    the vocabulary rather than extending it) redacts LESS at the parameter-name axis than the
    built-in default would. The built-in vocabulary must act as an unconditional floor here,
    unioned with whatever the caller's policy adds -- never replaced by it.
    """

    def test_a_policy_that_drops_password_from_its_vocabulary_still_redacts_it_at_capture(
        self,
    ) -> None:
        narrowed = RedactionPolicy.of_patterns({"totally_unrelated_word"})
        renderer = ValueRenderer(redaction_policy=narrowed)
        context = ContextVarNarrativeContext()

        trace_object(PaymentService(), context, renderer=renderer).login("bob", "hunter2")

        params = _capture_params(context)
        assert params["password"].redacted is True
        assert params["password"].rendered_value == "[REDACTED]"

    def test_a_callers_own_additional_pattern_still_redacts_alongside_the_floor(self) -> None:
        """Union, not override: a caller's own extra pattern keeps working -- the floor adds to
        what a caller's policy catches, it does not replace it."""
        extended = RedactionPolicy.of_patterns({"internal_code"})
        renderer = ValueRenderer(redaction_policy=extended)
        context = ContextVarNarrativeContext()

        trace_object(PaymentService(), context, renderer=renderer).apply_internal_code("XYZ-42")

        params = _capture_params(context)
        assert params["internal_code"].redacted is True
        assert params["internal_code"].rendered_value == "[REDACTED]"


def _every_artifact(secret: str) -> list[str]:
    context = ContextVarNarrativeContext()
    trace_object(PaymentService(), context).process_payment("plan-1", 500, secret)
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


class TestParameterNameRedactionContainment:
    """Redaction holds across every renderer the port has -- Markdown, prose, JSON and the rest --
    not just the raw ``ParameterCapture`` the proxy builds."""

    def test_a_payment_token_parameter_reaches_no_rendered_artifact(self) -> None:
        artifacts = _every_artifact(SECRET)

        assert artifacts, "the test must actually produce artifacts to assert anything"
        assert not any(SECRET in artifact for artifact in artifacts)

    def test_the_redaction_marker_reaches_every_artifact_instead(self) -> None:
        artifacts = _every_artifact(SECRET)

        assert all("[REDACTED]" in artifact for artifact in artifacts)
