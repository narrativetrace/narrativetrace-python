# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What the proxy records beyond names and values: canonical schema 1.1/1.2 call identity.

`code.namespace` stays a simple class name because a trace is meant to be read, so the package,
the declared return type and the declared parameter types are what let a machine tell two
same-named methods apart. The raw `@narrated` template is captured beside the resolved narration
because a translated view needs the placeholders back.

Python has two annotation shapes and both matter here. This module uses
`from __future__ import annotations`, so its own annotations arrive as source text (`"str"`);
`live_annotation_support` deliberately omits that import, so its annotations arrive as classes and
render fully qualified (`builtins.str`). The capture records what is declared and never evaluates a
string annotation — evaluating one can import modules and raise, on a path whose only job is to
describe a call.
"""

from __future__ import annotations

from typing import Any

import pytest
from live_annotation_support import LiveLedger

from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.decorators import narrated, not_traced
from narrativetrace.levels import NarrativeTraceConfig, TracingLevel
from narrativetrace.signature import MethodSignature
from narrativetrace.trace_object import trace_object
from narrativetrace.tree import TraceTree


class Ledger:
    def post(self, customer_id: str, amount: int) -> bool:
        return True

    def unannotated(self, anything):  # type: ignore[no-untyped-def]
        return anything

    def returns_nothing(self) -> None:
        return None

    @narrated("posts {amount} for {customer_id}")
    def narrated_post(self, customer_id: str, amount: int) -> bool:
        return True

    @not_traced("secret")
    def store(self, name: str, secret: str) -> None:
        return None


@pytest.fixture
def context() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.DETAIL))


def _root(tree: TraceTree) -> MethodSignature:
    return tree.roots[0].signature


def _capture(context: ContextVarNarrativeContext, call: str, *args: Any) -> MethodSignature:
    getattr(trace_object(Ledger(), context), call)(*args)
    return _root(context.capture_trace())


class TestPackage:
    def test_records_the_module_of_the_traced_class(
        self, context: ContextVarNarrativeContext
    ) -> None:
        assert _capture(context, "post", "cust-1", 42).package_name == Ledger.__module__

    def test_a_display_name_override_does_not_change_the_package(
        self, context: ContextVarNarrativeContext
    ) -> None:
        """`class_name` is a display choice; the package is identity and must follow the type."""
        trace_object(Ledger(), context, class_name="Books").post("cust-1", 42)
        signature = _root(context.capture_trace())

        assert signature.class_name == "Books"
        assert signature.package_name == Ledger.__module__


class TestDeclaredTypesFromStringAnnotations:
    """This module's own classes: PEP 563 text, recorded verbatim."""

    def test_records_the_return_annotation_as_written(
        self, context: ContextVarNarrativeContext
    ) -> None:
        assert _capture(context, "post", "cust-1", 42).return_type == "bool"

    def test_records_the_parameter_annotations_as_written(
        self, context: ContextVarNarrativeContext
    ) -> None:
        parameters = _capture(context, "post", "cust-1", 42).parameters

        assert {p.name: p.type_name for p in parameters} == {
            "customer_id": "str",
            "amount": "int",
        }

    def test_a_none_return_is_pythons_void(self, context: ContextVarNarrativeContext) -> None:
        assert _capture(context, "returns_nothing").return_type == "None"

    def test_an_unannotated_parameter_declares_no_type(
        self, context: ContextVarNarrativeContext
    ) -> None:
        signature = _capture(context, "unannotated", 1)

        assert signature.return_type is None
        assert signature.parameters[0].type_name is None

    def test_a_redacted_parameter_still_declares_its_type(
        self, context: ContextVarNarrativeContext
    ) -> None:
        """Redaction hides the value, not which method ran."""
        parameters = _capture(context, "store", "k", "hunter2").parameters
        secret = next(p for p in parameters if p.name == "secret")

        assert secret.redacted is True
        assert secret.type_name == "str"

    def test_suppressing_values_below_detail_keeps_the_declared_types(self) -> None:
        context = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.NARRATIVE))

        parameters = _capture(context, "post", "cust-1", 42).parameters

        assert [p.rendered_value for p in parameters] == ["", ""]
        assert [p.type_name for p in parameters] == ["str", "int"]


class TestDeclaredTypesFromLiveAnnotations:
    """A module without the future import: annotations are classes, rendered fully qualified."""

    def test_a_class_annotation_renders_module_qualified(
        self, context: ContextVarNarrativeContext
    ) -> None:
        trace_object(LiveLedger(), context).post("cust-1", 42)
        signature = _root(context.capture_trace())

        assert signature.return_type == f"{LiveLedger.__module__}.Receipt"
        assert {p.name: p.type_name for p in signature.parameters} == {
            "customer_id": "builtins.str",
            "amount": "builtins.int",
        }


class TestNarrationTemplate:
    def test_keeps_the_raw_template_beside_the_resolved_narration(
        self, context: ContextVarNarrativeContext
    ) -> None:
        signature = _capture(context, "narrated_post", "cust-1", 42)

        assert signature.narration == "posts 42 for cust-1"
        assert signature.narration_template == "posts {amount} for {customer_id}"

    def test_an_undecorated_method_declares_no_template(
        self, context: ContextVarNarrativeContext
    ) -> None:
        assert _capture(context, "post", "cust-1", 42).narration_template is None


class TestThreadIdentity:
    def test_every_captured_node_records_the_thread_that_ran_it(
        self, context: ContextVarNarrativeContext
    ) -> None:
        trace_object(Ledger(), context).post("cust-1", 42)
        node = context.capture_trace().roots[0]

        assert node.thread is not None
        assert node.thread.name
        assert node.thread.thread_id > 0
        assert node.thread.virtual is False
