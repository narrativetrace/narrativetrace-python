# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Flattening a captured tree into canonical entries, and the identity a context-free tree lacks.

The `.canonical.json` artifact is derived from the tree after a run, not from the live event
stream, so it has to reconstruct span ids, trace identity and story/chapter ids that a plain
unit-test tree never carried. Span ids and story/chapter ids are *derived*, so they are
byte-stable across runs and runtimes; the trace id is *generated*, so a conformance normalizer folds
it (sequence per first appearance) before comparing goldens.
"""

from __future__ import annotations

import json

import pytest
from conformance import ENTRY_SCHEMA, validate_against

import narrativetrace
from narrativetrace.canonical import SCHEMA_VERSION, UNKNOWN_SERVICE
from narrativetrace.concurrency import ThreadIdentity
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree
from narrativetrace.tree_canonical import entries_from_tree, export_canonical_entries

MS = 1_000_000


def _sig(
    class_name: str = "OrderService", method_name: str = "place_order", **kw: object
) -> object:
    fields: dict[str, object] = {"class_name": class_name, "method_name": method_name}
    fields.update(kw)
    return MethodSignature(**fields)  # type: ignore[arg-type]


def _node(**kw: object) -> TraceNode:
    fields: dict[str, object] = {
        "signature": _sig(),
        "children": [],
        "outcome": Returned('"ok"'),
        "duration_nanos": 5 * MS,
        "start_time_nanos": 1_775_000_000_000 * MS,
    }
    fields.update(kw)
    return TraceNode(**fields)  # type: ignore[arg-type]


def _span(**kw: object) -> SpanContext:
    fields: dict[str, object] = {"trace_id": TraceId("0" * 32), "span_id": SpanId("a" * 16)}
    fields.update(kw)
    return SpanContext(**fields)  # type: ignore[arg-type]


class _DomainError(Exception):
    """An exception outside `builtins`, so `nt.exceptionPackage` cannot pass by coincidence."""


class TestFlattening:
    def test_each_node_yields_one_enter_and_one_exit_depth_first(self) -> None:
        child = _node(signature=_sig("Inventory", "reserve"))
        entries = entries_from_tree(TraceTree([_node(children=[child])]))

        assert [(e.nt_event_type, e.code_namespace) for e in entries] == [
            ("method_enter", "OrderService"),
            ("method_enter", "Inventory"),
            ("method_exit", "Inventory"),
            ("method_exit", "OrderService"),
        ]

    def test_an_exit_carries_the_nodes_real_namespace_unlike_an_exit_event(self) -> None:
        """The tree still knows its signature; an exit *event* only knows its span name."""
        entries = entries_from_tree(TraceTree([_node()]))

        assert entries[1].code_namespace == "OrderService"
        assert entries[1].code_function == "place_order"

    def test_an_empty_tree_yields_no_entries(self) -> None:
        assert entries_from_tree(TraceTree([])) == []

    def test_a_none_tree_is_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"\Atree must not be None\Z"):
            entries_from_tree(None)  # type: ignore[arg-type]

    def test_children_are_linked_to_their_parents_span_id(self) -> None:
        child = _node(signature=_sig("Inventory", "reserve"))
        entries = entries_from_tree(TraceTree([_node(children=[child])]))

        assert entries[1].parent_span_id == entries[0].span_id
        assert entries[0].parent_span_id is None

    def test_an_exit_names_the_same_parent_span_its_enter_did(self) -> None:
        """Enter and exit are a parallel pair; a parent lost on one half orphans half the trace."""
        child = _node(signature=_sig("Inventory", "reserve"))
        entries = entries_from_tree(TraceTree([_node(children=[child])]))

        assert entries[2].parent_span_id == entries[0].span_id
        assert entries[3].parent_span_id is None


class TestResolvedIdentity:
    def test_a_context_free_tree_gets_the_real_trace_id_its_tree_resolved(self) -> None:
        tree = TraceTree([_node()])

        entries = entries_from_tree(tree)

        assert entries[0].trace_id == str(tree.trace_id)
        assert entries[0].service == UNKNOWN_SERVICE

    def test_a_generated_trace_id_is_never_all_zeroes(self) -> None:
        """W3C defines an all-zero trace id as invalid, so a generated one must never be."""
        assert entries_from_tree(TraceTree([_node()]))[0].trace_id != "0" * 32

    def test_two_context_free_trees_are_told_apart_by_their_trace_ids(self) -> None:
        """The retired synthetic constant made two unrelated captures indistinguishable."""
        first = entries_from_tree(TraceTree([_node()]))[0]
        second = entries_from_tree(TraceTree([_node()]))[0]

        assert first.trace_id != second.trace_id
        assert first.nt_story_id == second.nt_story_id

    def test_every_entry_of_one_context_free_tree_names_the_same_trace(self) -> None:
        tree = TraceTree([_node(children=[_node(signature=_sig("Inventory", "reserve"))])])
        resolved = tree.trace_id
        assert resolved is not None

        entries = entries_from_tree(tree)

        assert {entry.trace_id for entry in entries} == {str(resolved)}
        assert {entry.nt_trace_name for entry in entries} == {resolved.human_name()}

    def test_re_flattening_one_tree_yields_the_same_trace_id(self) -> None:
        """Identity is resolved on the tree, so exporting twice cannot mint a second trace."""
        tree = TraceTree([_node()])

        assert entries_from_tree(tree)[0].trace_id == entries_from_tree(tree)[0].trace_id

    def test_span_ids_are_sequential_and_reproducible_without_a_context(self) -> None:
        child = _node(signature=_sig("Inventory", "reserve"))
        tree = TraceTree([_node(children=[child])])

        first = [e.span_id for e in entries_from_tree(tree)]

        assert first == ["0" * 15 + "1", "0" * 15 + "2", "0" * 15 + "2", "0" * 15 + "1"]
        assert [e.span_id for e in entries_from_tree(tree)] == first

    def test_a_context_free_tree_derives_story_and_chapter_from_its_first_root(self) -> None:
        entries = entries_from_tree(TraceTree([_node()]))

        assert entries[0].nt_story_id == "OrderService.place_order"
        assert entries[0].nt_chapter_id == "OrderService.place_order"

    def test_a_context_free_child_inherits_the_trees_real_trace_id(self) -> None:
        """One tree is one trace: a node that lost its context must not start a second one."""
        child = _node(signature=_sig("Inventory", "reserve"))
        entries = entries_from_tree(TraceTree([_node(children=[child], span_context=_span())]))

        assert entries[1].trace_id == "0" * 32
        assert entries[1].nt_trace_name == entries[0].nt_trace_name

    def test_a_real_context_found_only_deep_in_the_tree_still_answers_for_the_root(self) -> None:
        child = _node(signature=_sig("Inventory", "reserve"), span_context=_span())
        entries = entries_from_tree(TraceTree([_node(children=[child])]))

        assert entries[0].trace_id == "0" * 32

    def test_a_real_context_anywhere_answers_for_every_node_in_the_tree(self) -> None:
        """Inheritance beats generation, so a mixed tree stays one trace end to end."""
        spanned = _node(signature=_sig("Inventory", "reserve"), span_context=_span())
        bare = _node(signature=_sig("Ledger", "post"))
        tree = TraceTree([_node(children=[spanned, bare])])

        entries = entries_from_tree(tree)

        assert len(entries) == 6
        assert {entry.trace_id for entry in entries} == {"0" * 32}
        assert {entry.nt_trace_name for entry in entries} == {TraceId("0" * 32).human_name()}

    def test_a_nodes_own_story_id_beats_the_derived_one(self) -> None:
        entries = entries_from_tree(TraceTree([_node(span_context=_span(story_id="checkout"))]))

        assert entries[0].nt_story_id == "checkout"

    def test_a_nodes_own_context_beats_the_one_the_tree_inherited(self) -> None:
        """Two roots, two contexts: the tree inherits the *first*, but each node answers for itself.

        A single-root tree cannot show this — there its own context and the inherited one are the
        same object, so every "own beats derived" assertion passes either way.
        """
        first = _span(story_id="checkout", chapter_id="cart", service_name="checkout-api")
        second = _span(
            trace_id=TraceId("b" * 32),
            story_id="fulfilment",
            chapter_id="dispatch",
            service_name="inventory-api",
        )
        tree = TraceTree([_node(span_context=first), _node(span_context=second)])

        entries = entries_from_tree(tree)

        assert (entries[0].trace_id, entries[0].nt_story_id, entries[0].nt_chapter_id) == (
            "0" * 32,
            "checkout",
            "cart",
        )
        assert (entries[2].trace_id, entries[2].nt_story_id, entries[2].nt_chapter_id) == (
            "b" * 32,
            "fulfilment",
            "dispatch",
        )
        assert (entries[0].service, entries[2].service) == ("checkout-api", "inventory-api")


class TestResourceFields:
    """The service, host and process fields the effective span context supplies."""

    def test_every_resource_field_travels_from_the_effective_context(self) -> None:
        context = _span(
            service_name="checkout-api",
            environment="staging",
            host_name="node-7",
            process_pid=4242,
            runtime_version="3.12.4",
        )

        entry = entries_from_tree(TraceTree([_node(span_context=context)]))[0]

        assert entry.service == "checkout-api"
        assert entry.environment == "staging"
        assert entry.host_name == "node-7"
        assert entry.process_pid == 4242
        assert entry.process_runtime_version == "3.12.4"

    def test_a_context_free_node_borrows_the_resource_fields_the_tree_inherited(self) -> None:
        """One tree is one service: a node that lost its context is not a second host."""
        spanned = _node(span_context=_span(service_name="checkout-api", host_name="node-7"))
        bare = _node(signature=_sig("Ledger", "post"))

        entries = entries_from_tree(TraceTree([_node(children=[spanned, bare])]))

        assert {entry.service for entry in entries} == {"checkout-api"}
        assert {entry.host_name for entry in entries} == {"node-7"}

    def test_a_context_that_named_no_service_reports_unknown_not_a_blank(self) -> None:
        entry = entries_from_tree(TraceTree([_node(span_context=_span(host_name="node-7"))]))[0]

        assert entry.service == UNKNOWN_SERVICE
        assert entry.environment is None


class TestIdentityFields:
    def test_an_enter_carries_the_package_return_type_and_parameter_types(self) -> None:
        signature = _sig(
            parameters=[ParameterCapture("amount", "42", False, None, "builtins.int")],
            package_name="acme.billing",
            return_type="acme.billing.Receipt",
        )
        entries = entries_from_tree(TraceTree([_node(signature=signature)]))

        assert entries[0].nt_package == "acme.billing"
        assert entries[0].nt_return_type == "acme.billing.Receipt"
        assert entries[0].nt_parameters is not None
        assert entries[0].nt_parameters[0].type_name == "builtins.int"

    def test_an_enter_carries_the_raw_narration_template_not_the_resolved_text(self) -> None:
        signature = _sig(narration="charged 42", narration_template="charged {amount}")
        entries = entries_from_tree(TraceTree([_node(signature=signature)]))

        assert entries[0].nt_narration_template == "charged {amount}"

    def test_a_redacted_parameter_never_leaks_its_value(self) -> None:
        signature = _sig(parameters=[ParameterCapture("pw", "hunter2", True)])
        entries = entries_from_tree(TraceTree([_node(signature=signature)]))

        assert entries[0].nt_parameters is not None
        assert entries[0].nt_parameters[0].value == "[REDACTED]"

    def test_thread_identity_travels_from_the_node(self) -> None:
        entries = entries_from_tree(TraceTree([_node(thread=ThreadIdentity("worker-3", 42))]))

        assert (entries[0].thread_name, entries[0].thread_id) == ("worker-3", 42)
        assert entries[0].nt_thread_virtual is False

    def test_a_node_without_thread_identity_reports_null_not_a_guess(self) -> None:
        entries = entries_from_tree(TraceTree([_node()]))

        assert entries[0].thread_name is None
        assert entries[0].nt_thread_virtual is None

    def test_a_throw_carries_the_exception_package_beside_its_simple_type(self) -> None:
        entries = entries_from_tree(TraceTree([_node(outcome=Threw(ValueError("boom")))]))

        assert entries[1].exception_type == "ValueError"
        assert entries[1].nt_exception_package == "builtins"
        assert entries[1].nt_outcome == "failure"
        assert entries[1].level == "error"

    def test_a_domain_exceptions_package_is_its_own_module_not_builtins(self) -> None:
        """`builtins` is also what a mis-read of the outcome yields, so it proves little alone."""
        entries = entries_from_tree(TraceTree([_node(outcome=Threw(_DomainError("nope")))]))

        assert entries[1].nt_exception_package == _DomainError.__module__
        assert entries[1].nt_exception_package != "builtins"

    def test_a_throw_reads_as_the_exception_in_the_exit_message_and_its_text(self) -> None:
        entries = entries_from_tree(TraceTree([_node(outcome=Threw(ValueError("boom")))]))

        assert entries[1].message == "!! ValueError: boom"
        assert entries[1].exception_message == "boom"

    def test_an_enter_message_names_the_call_it_opens(self) -> None:
        entries = entries_from_tree(TraceTree([_node()]))

        assert entries[0].message == "→ OrderService.place_order"
        assert entries[1].message == "← OrderService.place_order"

    def test_an_exit_carries_the_rendered_return_value_and_the_duration(self) -> None:
        node = _node(outcome=Returned('"ok"'), duration_nanos=7 * MS)
        entries = entries_from_tree(TraceTree([node]))

        assert entries[1].nt_return_value == '"ok"'
        assert entries[1].duration_ms == 7
        assert entries[0].nt_return_value is None

    def test_an_unfinished_node_is_incomplete(self) -> None:
        entries = entries_from_tree(TraceTree([_node(outcome=Incomplete())]))

        assert entries[1].nt_outcome == "incomplete"

    def test_every_entry_stamps_the_one_schema_version(self) -> None:
        entries = entries_from_tree(TraceTree([_node()]))

        assert {e.nt_schema_version for e in entries} == {SCHEMA_VERSION}


class TestTimestamps:
    """A tree has no wall-clock anchor, so a monotonic reading is read as millis since the epoch.

    The exact spelling is the contract: `.canonical.json` files are compared byte for byte across
    runtimes, so the offset suffix, the millisecond precision and the truncation rule are all pinned
    rather than merely "looks like a date".
    """

    def test_an_enter_is_stamped_with_the_nodes_start_as_a_utc_instant(self) -> None:
        entries = entries_from_tree(TraceTree([_node(start_time_nanos=1_775_000_000_000 * MS)]))

        assert entries[0].timestamp == "2026-03-31T23:33:20.000Z"

    def test_an_exit_is_stamped_with_the_start_plus_the_duration(self) -> None:
        node = _node(start_time_nanos=1_775_000_000_000 * MS, duration_nanos=5 * MS)

        entries = entries_from_tree(TraceTree([node]))

        assert entries[1].timestamp == "2026-03-31T23:33:20.005Z"

    def test_a_sub_millisecond_reading_is_truncated_rather_than_rounded_up(self) -> None:
        """Java divides integer nanos by a million; rounding here would break byte comparison."""
        node = _node(start_time_nanos=999_600, duration_nanos=0)

        entries = entries_from_tree(TraceTree([node]))

        assert entries[0].timestamp == "1970-01-01T00:00:00.000Z"


class TestArtifact:
    def test_renders_a_json_array_of_entries(self) -> None:
        document = json.loads(export_canonical_entries(TraceTree([_node()])))

        assert isinstance(document, list)
        assert [e["nt.eventType"] for e in document] == ["method_enter", "method_exit"]

    def test_an_empty_tree_renders_an_empty_array(self) -> None:
        assert export_canonical_entries(TraceTree([])) == "[]"

    def test_every_entry_validates_against_the_canonical_entry_schema(self) -> None:
        child = _node(
            signature=_sig(
                "Inventory",
                "reserve",
                parameters=[ParameterCapture("sku", '"s-1"', False, None, "builtins.str")],
                package_name="acme.inventory",
                return_type="None",
            ),
            outcome=Threw(ValueError("out of stock")),
            thread=ThreadIdentity("worker-1", 7),
        )
        tree = TraceTree([_node(children=[child], span_context=_span(service_name="orders"))])

        for entry in json.loads(export_canonical_entries(tree)):
            validate_against(entry, ENTRY_SCHEMA)

    def test_a_context_free_trees_entries_also_validate(self) -> None:
        """Eager generation exists precisely so this passes: `trace_id` is required."""
        for entry in json.loads(export_canonical_entries(TraceTree([_node()]))):
            validate_against(entry, ENTRY_SCHEMA)


class TestPublicSurface:
    def test_is_reachable_from_the_distribution_root(self) -> None:
        document = json.loads(narrativetrace.export_canonical_entries(TraceTree([_node()])))

        assert [e["nt.eventType"] for e in document] == ["method_enter", "method_exit"]
        assert "export_canonical_entries" in narrativetrace.__all__


class TestDepthAndCycleBounds:
    """Security-suite mirror (2026-09-04): flattening used unbounded native recursion with no
    depth bound or cycle guard -- both a cycle and a pathologically deep chain crashed with an
    uncaught RecursionError."""

    def test_a_self_referential_node_does_not_crash_flattening(self) -> None:
        node = _node()
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        entries = json.loads(export_canonical_entries(TraceTree([node])))
        assert len(entries) >= 2

    def test_a_ten_thousand_deep_chain_is_truncated_not_crashed(self) -> None:
        node = _node()
        for _ in range(10_000):
            node = _node(children=[node])
        entries = json.loads(export_canonical_entries(TraceTree([node])))
        assert 2 < len(entries) < 2000
