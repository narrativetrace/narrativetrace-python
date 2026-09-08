# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Pins the attribute mapper's typed flattening and string-inference fallback to Java."""

from __future__ import annotations

from narrativetrace_otel import attributes
from opentelemetry.trace import Tracer
from otel_harness import Harness

from narrativetrace.context_export import MAX_LENGTH
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.metadata import ClientIp, HttpRoute
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext
from narrativetrace.values import (
    BoolVal,
    FloatVal,
    InstantVal,
    IntVal,
    ListVal,
    NullVal,
    ObjectVal,
    StringVal,
)


def _span_attrs(tracer: Tracer, param: ParameterCapture) -> dict[str, object]:
    span = tracer.start_span("probe")
    attributes.set_span_attributes(MethodSignature("C", "m", [param]), span)
    span.end()
    return dict(getattr(span, "attributes", None) or {})


class TestStringInferenceFallback:
    def test_quoted_string_is_stripped(self, otel: Harness) -> None:
        attrs = _span_attrs(otel.tracer, ParameterCapture("name", '"Alice"'))
        assert attrs["narrative.param.name"] == "Alice"

    def test_integer_string_becomes_int(self, otel: Harness) -> None:
        attrs = _span_attrs(otel.tracer, ParameterCapture("count", "42"))
        assert attrs["narrative.param.count"] == 42
        assert isinstance(attrs["narrative.param.count"], int)

    def test_float_string_becomes_float(self, otel: Harness) -> None:
        attrs = _span_attrs(otel.tracer, ParameterCapture("rate", "3.14"))
        assert attrs["narrative.param.rate"] == 3.14

    def test_true_and_false_become_bool(self, otel: Harness) -> None:
        assert _span_attrs(otel.tracer, ParameterCapture("f", "true"))["narrative.param.f"] is True
        assert (
            _span_attrs(otel.tracer, ParameterCapture("f", "false"))["narrative.param.f"] is False
        )

    def test_unparseable_stays_string(self, otel: Harness) -> None:
        attrs = _span_attrs(otel.tracer, ParameterCapture("label", "some-text"))
        assert attrs["narrative.param.label"] == "some-text"


class TestStructuredFlattening:
    def test_instant_val_uses_epoch_millis(self, otel: Harness) -> None:
        param = ParameterCapture("ts", "2025-03-16", False, InstantVal(1742134981123))
        attrs = _span_attrs(otel.tracer, param)
        assert attrs["narrative.param.ts"] == 1742134981123

    def test_null_val_is_skipped(self, otel: Harness) -> None:
        attrs = _span_attrs(otel.tracer, ParameterCapture("x", "null", False, NullVal()))
        assert "narrative.param.x" not in attrs

    def test_object_flattens_to_depth_three(self, otel: Harness) -> None:
        deep = ObjectVal("L3", {"deep": StringVal("too-deep")})
        level2 = ObjectVal("L2", {"c": deep})
        level1 = ObjectVal("L1", {"b": level2})
        attrs = _span_attrs(otel.tracer, ParameterCapture("obj", "...", False, level1))
        assert attrs["narrative.param.obj.b.c.deep"] == "too-deep"

    def test_object_deeper_than_three_is_skipped(self, otel: Harness) -> None:
        l4 = ObjectVal("L4", {"x": StringVal("v")})
        l3 = ObjectVal("L3", {"d": l4})
        l2 = ObjectVal("L2", {"c": l3})
        l1 = ObjectVal("L1", {"b": l2})
        attrs = _span_attrs(otel.tracer, ParameterCapture("obj", "...", False, l1))
        assert not any(k.endswith(".x") for k in attrs)

    def test_homogeneous_int_list_is_array(self, otel: Harness) -> None:
        lv = ListVal([IntVal(1), IntVal(2)])
        attrs = _span_attrs(otel.tracer, ParameterCapture("ids", "...", False, lv))
        assert attrs["narrative.param.ids"] == (1, 2)

    def test_homogeneous_string_list_is_array(self, otel: Harness) -> None:
        lv = ListVal([StringVal("a"), StringVal("b")])
        attrs = _span_attrs(otel.tracer, ParameterCapture("tags", "...", False, lv))
        assert attrs["narrative.param.tags"] == ("a", "b")

    def test_homogeneous_bool_list_is_array(self, otel: Harness) -> None:
        lv = ListVal([BoolVal(True), BoolVal(False)])
        attrs = _span_attrs(otel.tracer, ParameterCapture("flags", "...", False, lv))
        assert attrs["narrative.param.flags"] == (True, False)

    def test_homogeneous_float_list_is_array(self, otel: Harness) -> None:
        lv = ListVal([FloatVal(1.1), FloatVal(2.2)])
        attrs = _span_attrs(otel.tracer, ParameterCapture("rates", "...", False, lv))
        assert attrs["narrative.param.rates"] == (1.1, 2.2)

    def test_empty_list_is_skipped(self, otel: Harness) -> None:
        attrs = _span_attrs(otel.tracer, ParameterCapture("items", "...", False, ListVal([])))
        assert "narrative.param.items" not in attrs

    def test_heterogeneous_list_is_skipped(self, otel: Harness) -> None:
        lv = ListVal([IntVal(1), StringVal("a")])
        attrs = _span_attrs(otel.tracer, ParameterCapture("mix", "...", False, lv))
        assert "narrative.param.mix" not in attrs


class TestSkipping:
    def test_redacted_param_is_skipped(self, otel: Harness) -> None:
        attrs = _span_attrs(otel.tracer, ParameterCapture("pwd", "secret", True))
        assert "narrative.param.pwd" not in attrs

    def test_empty_rendered_value_is_skipped(self, otel: Harness) -> None:
        attrs = _span_attrs(otel.tracer, ParameterCapture("x", ""))
        assert "narrative.param.x" not in attrs


class TestEventAttributes:
    def test_typed_param_and_outcome(self) -> None:
        sig = MethodSignature("C", "m", [ParameterCapture("count", "42", False, IntVal(42))])
        attrs = attributes.build_event_attributes(sig, Returned("ok"))
        assert attrs["narrative.param.count"] == 42
        assert attrs["narrative.outcome"] == "ok"

    def test_threw_outcome_prefixed_with_error(self) -> None:
        attrs = attributes.build_event_attributes(
            MethodSignature("C", "m"), Threw(ValueError("boom"))
        )
        assert attrs["narrative.outcome"] == "error: boom"

    def test_fallback_typed_param_without_structured(self) -> None:
        sig = MethodSignature("C", "m", [ParameterCapture("n", "99")])
        attrs = attributes.build_event_attributes(sig, Returned("ok"))
        assert attrs["narrative.param.n"] == 99

    def test_redacted_param_skipped_in_event(self) -> None:
        sig = MethodSignature("C", "m", [ParameterCapture("pwd", "x", True)])
        attrs = attributes.build_event_attributes(sig, Returned("ok"))
        assert "narrative.param.pwd" not in attrs

    def test_list_param_skipped_in_event(self) -> None:
        lv = ListVal([IntVal(1), IntVal(2)])
        sig = MethodSignature("C", "m", [ParameterCapture("ids", "...", False, lv)])
        attrs = attributes.build_event_attributes(sig, Returned("ok"))
        assert "narrative.param.ids" not in attrs


class TestTraceLevelAttributeNormalization:
    """Adversarial-audit mirror (2026-09-02): a value set programmatically (bypassing the HTTP
    middleware's own normalisation) still gets control-stripped and length-capped here, since this
    mapper is the last point before it becomes a telemetry attribute."""

    def _sc(self, **fields: object) -> SpanContext:
        return SpanContext(trace_id=TraceId("0" * 32), span_id=SpanId("a" * 16), **fields)  # type: ignore[arg-type]

    def test_a_newline_in_the_route_is_escaped(self, otel: Harness) -> None:
        span = otel.tracer.start_span("probe")
        attributes.set_trace_level_attributes(
            self._sc(http_route=HttpRoute.of("/orders\nFAKE LOG LINE")), span
        )
        span.end()
        assert otel.attrs(span)["narrative.http.route"] == "/orders\\nFAKE LOG LINE"

    def test_a_long_client_ip_field_is_capped(self, otel: Harness) -> None:
        span = otel.tracer.start_span("probe")
        attributes.set_trace_level_attributes(self._sc(client_ip=ClientIp.of("x" * 1000)), span)
        span.end()
        result = otel.attrs(span)["narrative.client_ip"]
        assert isinstance(result, str)
        assert len(result) == MAX_LENGTH + 1

    def test_an_ordinary_route_is_unchanged(self, otel: Harness) -> None:
        span = otel.tracer.start_span("probe")
        attributes.set_trace_level_attributes(self._sc(http_route=HttpRoute.of("/orders/42")), span)
        span.end()
        assert otel.attrs(span)["narrative.http.route"] == "/orders/42"
