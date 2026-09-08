# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for MethodSignature and ParameterCapture."""

from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.values import IntVal


def test_parameter_capture_defaults() -> None:
    cap = ParameterCapture("orderId", "42")
    assert cap.name == "orderId"
    assert cap.rendered_value == "42"
    assert cap.redacted is False
    assert cap.structured_value is None


def test_parameter_capture_with_structured_value() -> None:
    cap = ParameterCapture("orderId", "42", redacted=False, structured_value=IntVal(42))
    assert cap.structured_value == IntVal(42)


def test_method_signature_defaults() -> None:
    sig = MethodSignature("OrderService", "placeOrder", [ParameterCapture("id", "1")])
    assert sig.class_name == "OrderService"
    assert sig.method_name == "placeOrder"
    assert len(sig.parameters) == 1
    assert sig.narration is None
    assert sig.error_context is None


def test_method_signature_carries_narration_and_error_context() -> None:
    sig = MethodSignature(
        "OrderService",
        "placeOrder",
        [],
        narration="Placing order 1",
        error_context="failed to place order",
    )
    assert sig.narration == "Placing order 1"
    assert sig.error_context == "failed to place order"
