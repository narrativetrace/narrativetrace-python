# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Property tests: the attribute mapper never crashes and preserves scalar types."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st
from narrativetrace_otel import attributes

from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.values import BoolVal, FloatVal, IntVal, RenderedValue, StringVal


@given(rendered=st.text())
def test_string_inference_never_crashes(rendered: str) -> None:
    """Any rendered string produces exactly one attribute of a valid OTel type."""
    sig = MethodSignature("C", "m", [ParameterCapture("p", rendered)])
    attrs = attributes.build_event_attributes(sig, None)
    if rendered != "":
        value = attrs["narrative.param.p"]
        assert isinstance(value, str | bool | int | float)


_SCALARS = st.one_of(
    st.integers().map(IntVal),
    st.floats(allow_nan=False, allow_infinity=False).map(FloatVal),
    st.booleans().map(BoolVal),
    st.text().map(StringVal),
)


@given(value=_SCALARS)
def test_structured_scalar_round_trips_native_type(value: RenderedValue) -> None:
    """A structured scalar flattens to its native Python value verbatim."""
    sig = MethodSignature("C", "m", [ParameterCapture("p", "x", False, value)])
    attrs = attributes.build_event_attributes(sig, None)
    assert attrs["narrative.param.p"] == value.value  # type: ignore[attr-defined]
