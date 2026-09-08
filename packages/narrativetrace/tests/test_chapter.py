# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the chapter-level canonical export (``chapter.schema.json``)."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from conformance import (
    CHAPTER_SCHEMA,
    CHAPTER_TREE_SCHEMA,
    validate_against,
    validate_json_text,
)

import narrativetrace
from narrativetrace.canonical import SCHEMA_VERSION
from narrativetrace.chapter import export_chapter
from narrativetrace.export import export_document
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw, TraceOutcome
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import MethodSignature
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree

MS = 1_000_000
TRACE = TraceId("0" * 32)


@pytest.fixture
def host_timezone() -> Iterator[Callable[[str], None]]:
    """Switches the process timezone for one test and restores the original on teardown."""
    original = os.environ.get("TZ")

    def _set(name: str) -> None:
        os.environ["TZ"] = name
        time.tzset()

    yield _set
    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()


def _span(**kw: object) -> SpanContext:
    return SpanContext(trace_id=TRACE, span_id=SpanId("a" * 16), **kw)  # type: ignore[arg-type]


def _root(**kw: object) -> TraceNode:
    defaults: dict[str, object] = {
        "signature": MethodSignature("OrderService", "place_order", []),
        "children": [],
        "outcome": Returned('"ok"'),
        "duration_nanos": 251 * MS,
        "span_context": _span(service_name="order-service"),
    }
    defaults.update(kw)
    return TraceNode(**defaults)  # type: ignore[arg-type]


def _chapter(
    *roots: TraceNode,
    result: ScenarioResult = ScenarioResult.SUCCESS,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    tree = TraceTree(list(roots))
    doc: dict[str, Any] = json.loads(
        export_chapter(tree, TraceMetadata("Customer places order", result), clock=clock)
    )
    return doc


class TestSchemaFields:
    def test_carries_the_chapter_discriminator_and_schema_version(self) -> None:
        doc = _chapter(_root())
        assert doc["nt.entryType"] == "chapter"
        assert doc["nt.schemaVersion"] == SCHEMA_VERSION

    def test_title_is_the_root_class_and_method(self) -> None:
        doc = _chapter(_root())
        assert doc["nt.title"] == "OrderService.place_order"


class TestOutcome:
    @pytest.mark.parametrize(
        ("outcome", "expected"),
        [
            (Returned('"ok"'), "success"),
            (Threw(RuntimeError("boom")), "failure"),
            (Incomplete(), "partial"),
            (None, "success"),
        ],
    )
    def test_maps_the_root_outcome(self, outcome: TraceOutcome | None, expected: str) -> None:
        doc = _chapter(_root(outcome=outcome))
        assert doc["nt.outcome"] == expected

    @pytest.mark.parametrize(
        ("outcome", "expected"),
        [
            (Returned('"ok"'), "info"),
            (Threw(RuntimeError("boom")), "error"),
            (Incomplete(), "info"),
        ],
    )
    def test_only_a_failed_chapter_logs_at_error_level(
        self, outcome: TraceOutcome, expected: str
    ) -> None:
        doc = _chapter(_root(outcome=outcome))
        assert doc["level"] == expected


class TestMessage:
    def test_summarises_title_duration_and_outcome(self) -> None:
        doc = _chapter(_root())
        assert doc["message"] == "Chapter complete: OrderService.place_order [251ms] success"

    def test_empty_tree_summarises_an_unknown_zero_duration_chapter(self) -> None:
        doc = _chapter()
        assert doc["message"] == "Chapter complete: unknown [0ms] success"


class TestCorrelation:
    def test_carries_the_root_span_correlation_fields(self) -> None:
        span = _span(
            service_name="order-service",
            story_id="OrderService.place_order",
            chapter_id="OrderService.place_order#1",
        )
        doc = _chapter(_root(span_context=span))
        assert doc["service"] == "order-service"
        assert doc["trace_id"] == "0" * 32
        assert doc["nt.storyId"] == "OrderService.place_order"
        assert doc["nt.chapterId"] == "OrderService.place_order#1"
        assert doc["nt.traceName"] == "red fox runs"

    def test_derives_every_correlation_field_when_no_root_carries_a_span(self) -> None:
        """Identity is generated eagerly (owner decision 2026-08-30), never omitted.

        `service` falls back, `trace_id` is generated, and story and chapter are derived from the
        first root call — so a chapter captured without a span still satisfies the schema.
        """
        doc = _chapter(_root(span_context=None))
        assert doc["service"] == "unknown_service:python"
        assert doc["trace_id"] != "0" * 32
        assert len(doc["trace_id"]) == 32
        assert doc["nt.storyId"] == "OrderService.place_order"
        assert doc["nt.chapterId"] == "OrderService.place_order"
        assert doc["nt.traceName"] == TraceId(doc["trace_id"]).human_name()

    def test_derives_the_correlation_fields_the_span_leaves_unset(self) -> None:
        doc = _chapter(_root(span_context=_span()))
        assert doc["trace_id"] == "0" * 32
        assert doc["nt.traceName"] == "red fox runs"
        assert doc["service"] == "unknown_service:python"
        assert doc["nt.storyId"] == "OrderService.place_order"
        assert doc["nt.chapterId"] == "OrderService.place_order"

    def test_an_empty_tree_falls_back_to_the_unknown_story_its_title_uses(self) -> None:
        doc = _chapter()
        assert doc["nt.title"] == "unknown"
        assert doc["nt.storyId"] == "unknown"
        assert doc["nt.chapterId"] == "unknown"
        assert len(doc["trace_id"]) == 32

    def test_takes_correlation_from_the_first_root_that_has_a_span(self) -> None:
        first = _root(span_context=None)
        second = _root(span_context=_span(service_name="second-service"))
        doc = _chapter(first, second)
        assert doc["service"] == "second-service"
        assert doc["nt.title"] == "OrderService.place_order"

    def test_a_span_found_only_deep_in_the_tree_answers_for_the_chapter(self) -> None:
        """One tree is one trace: the mixed-tree rule reaches service and trace id alike."""
        deep = _root(span_context=_span(service_name="deep-service", story_id="checkout"))
        doc = _chapter(_root(span_context=None, children=[deep]))
        assert doc["service"] == "deep-service"
        assert doc["trace_id"] == "0" * 32
        assert doc["nt.storyId"] == "checkout"


class TestTotals:
    def test_total_duration_is_the_root_duration_in_millis(self) -> None:
        doc = _chapter(_root())
        assert doc["nt.totalDurationMs"] == 251

    def test_total_duration_is_omitted_for_an_empty_tree(self) -> None:
        doc = _chapter()
        assert "nt.totalDurationMs" not in doc

    def test_entry_count_includes_every_nested_descendant(self) -> None:
        grandchild = _root(signature=MethodSignature("Repo", "save", []), span_context=None)
        child = _root(
            signature=MethodSignature("Svc", "inner", []),
            children=[grandchild],
            span_context=None,
        )
        doc = _chapter(_root(children=[child]))
        assert doc["nt.entryCount"] == 3

    def test_entry_count_is_zero_for_an_empty_tree(self) -> None:
        doc = _chapter()
        assert doc["nt.entryCount"] == 0

    def test_entry_count_spans_every_root(self) -> None:
        doc = _chapter(_root(), _root(span_context=None))
        assert doc["nt.entryCount"] == 2


class TestDepthAndCycleBounds:
    """Security-suite mirror (2026-09-04): entry counting used unbounded native recursion with no
    depth bound or cycle guard -- both a cycle and a pathologically deep chain crashed with an
    uncaught RecursionError."""

    def test_a_self_referential_node_does_not_crash_the_entry_count(self) -> None:
        node = _root(children=[])
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        assert _chapter(node)["nt.entryCount"] >= 1

    def test_a_ten_thousand_deep_chain_is_truncated_not_crashed(self) -> None:
        node = _root(children=[], span_context=None)
        for _ in range(10_000):
            node = _root(children=[node], span_context=None)
        assert 1 < _chapter(node)["nt.entryCount"] < 1000


class TestEmbeddedTree:
    def test_completion_status_is_complete(self) -> None:
        doc = _chapter(_root())
        assert doc["nt.completionStatus"] == "complete"

    def test_chapter_tree_embeds_the_full_document_as_a_json_string(self) -> None:
        root = _root()
        doc = _chapter(root)
        assert isinstance(doc["nt.chapterTree"], str)
        embedded = json.loads(doc["nt.chapterTree"])
        assert embedded == json.loads(
            export_document(
                TraceTree([root]), TraceMetadata("Customer places order", ScenarioResult.SUCCESS)
            )
        )

    def test_chapter_tree_carries_the_nested_event_stream(self) -> None:
        child = _root(signature=MethodSignature("Svc", "inner", []), span_context=None)
        doc = _chapter(_root(children=[child]))
        embedded = json.loads(doc["nt.chapterTree"])
        assert [e["type"] for e in embedded["events"]] == ["enter", "enter", "exit", "exit"]
        assert embedded["scenario"]["name"] == "Customer places order"


class TestTimestamp:
    def test_stamps_the_clock_reading_with_millisecond_precision(self) -> None:
        reading = datetime(2026, 8, 13, 12, 34, 56, 789_500, tzinfo=UTC)
        doc = _chapter(_root(), clock=lambda: reading)
        assert doc["timestamp"] == "2026-08-13T12:34:56.789Z"

    def test_normalises_a_non_utc_clock_reading_to_utc(self) -> None:
        reading = datetime(2026, 8, 13, 15, 34, 56, tzinfo=timezone(timedelta(hours=3)))
        doc = _chapter(_root(), clock=lambda: reading)
        assert doc["timestamp"] == "2026-08-13T12:34:56.000Z"

    def test_defaults_to_the_current_utc_time(self) -> None:
        before = datetime.now(UTC).replace(microsecond=0)
        doc = _chapter(_root())
        stamped = datetime.fromisoformat(doc["timestamp"])
        assert before <= stamped <= datetime.now(UTC)

    def test_normalises_a_dst_aware_zone_reading(self) -> None:
        reading = datetime(2026, 8, 13, 8, 34, 56, tzinfo=ZoneInfo("America/New_York"))
        doc = _chapter(_root(), clock=lambda: reading)
        assert doc["timestamp"] == "2026-08-13T12:34:56.000Z"

    @pytest.mark.skipif(not hasattr(time, "tzset"), reason="TZ switching needs POSIX tzset")
    def test_stamps_utc_even_when_the_host_zone_is_not_utc(
        self, host_timezone: Callable[[str], None]
    ) -> None:
        host_timezone("America/New_York")
        reading = datetime(2026, 8, 13, 12, 34, 56, tzinfo=UTC)
        doc = _chapter(_root(), clock=lambda: reading)
        assert doc["timestamp"] == "2026-08-13T12:34:56.000Z"


class TestPublicSurface:
    def test_is_reachable_from_the_distribution_root(self) -> None:
        doc = json.loads(
            narrativetrace.export_chapter_json(
                TraceTree([_root()]), TraceMetadata("Customer places order", ScenarioResult.SUCCESS)
            )
        )
        assert doc["nt.entryType"] == "chapter"
        assert "export_chapter_json" in narrativetrace.__all__


class TestFieldOrder:
    def test_emits_fields_in_the_java_exporter_order(self) -> None:
        doc = _chapter(_root(span_context=_span(service_name="s", story_id="a", chapter_id="b")))
        assert list(doc) == [
            "timestamp",
            "level",
            "message",
            "service",
            "trace_id",
            "nt.entryType",
            "nt.storyId",
            "nt.chapterId",
            "nt.title",
            "nt.outcome",
            "nt.completionStatus",
            "nt.traceName",
            "nt.schemaVersion",
            "nt.totalDurationMs",
            "nt.entryCount",
            "nt.chapterTree",
        ]


class TestWireFormat:
    def test_is_pretty_printed_with_two_space_indentation(self) -> None:
        raw = export_chapter(TraceTree([_root()]), TraceMetadata("s", ScenarioResult.SUCCESS))
        assert raw.startswith('{\n  "timestamp": ')
        assert '\n  "nt.entryType": "chapter"' in raw
        assert '\n   "' not in raw
        assert raw.endswith("\n}")

    def test_emits_non_ascii_literally_rather_than_escaped(self) -> None:
        root = _root(signature=MethodSignature("Pedido", "año", []))
        raw = export_chapter(TraceTree([root]), TraceMetadata("s", ScenarioResult.SUCCESS))
        assert "Pedido.año" in raw
        assert "\\u00f1" not in raw


class TestHostileInput:
    def test_control_characters_and_quotes_round_trip_through_both_json_layers(self) -> None:
        hostile = 'Order\x01\b"Service"\\'
        root = _root(signature=MethodSignature(hostile, "place_order", []))
        doc = _chapter(root)
        assert doc["nt.title"] == f"{hostile}.place_order"
        embedded = json.loads(doc["nt.chapterTree"])
        assert embedded["events"][0]["className"] == hostile

    def test_non_ascii_survives_both_json_layers(self) -> None:
        root = _root(signature=MethodSignature("Pedido", "año_naïve_🎉", []))
        doc = _chapter(root)
        assert doc["nt.title"] == "Pedido.año_naïve_🎉"
        embedded = json.loads(doc["nt.chapterTree"])
        assert embedded["events"][0]["methodName"] == "año_naïve_🎉"


class TestGuards:
    def test_rejects_a_clock_reading_without_a_timezone(self) -> None:
        naive = datetime(2026, 8, 13, 12, 34, 56)
        with pytest.raises(ValueError, match=r"\Aclock must return a timezone-aware datetime\Z"):
            export_chapter(
                TraceTree([]), TraceMetadata("s", ScenarioResult.SUCCESS), clock=lambda: naive
            )

    def test_rejects_a_missing_tree(self) -> None:
        with pytest.raises(ValueError, match=r"\Atree must not be None\Z"):
            export_chapter(None, TraceMetadata("s", ScenarioResult.SUCCESS))  # type: ignore[arg-type]

    def test_rejects_missing_metadata(self) -> None:
        with pytest.raises(ValueError, match=r"\Ametadata must not be None\Z"):
            export_chapter(TraceTree([]), None)  # type: ignore[arg-type]


class TestSchemaConformance:
    def test_a_chapter_from_a_fully_correlated_tree_satisfies_chapter_schema(self) -> None:
        span = _span(service_name="order-service", story_id="checkout", chapter_id="ch-1")

        validate_against(_chapter(_root(span_context=span)), CHAPTER_SCHEMA)

    def test_the_embedded_chapter_tree_satisfies_chapter_tree_schema(self) -> None:
        doc = _chapter(_root(span_context=_span(service_name="order-service")))

        validate_json_text(doc["nt.chapterTree"], CHAPTER_TREE_SCHEMA)

    def test_a_span_less_tree_satisfies_chapter_schema_because_identity_is_generated(self) -> None:
        """The inversion of a pinned divergence: `trace_id`, `nt.storyId` and `nt.chapterId` are
        `required`, and eager generation (owner decision 2026-08-30) is what supplies them."""
        validate_against(_chapter(_root(span_context=None)), CHAPTER_SCHEMA)

    def test_an_empty_trees_chapter_also_satisfies_chapter_schema(self) -> None:
        """The tree keeps no id, so the required one comes from the generate rung at export."""
        validate_against(_chapter(), CHAPTER_SCHEMA)
