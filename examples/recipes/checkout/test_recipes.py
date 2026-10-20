# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Proves every page under ``documentation/recipes/`` (rule 8, docs as tests): each claim a page
makes about a run is asserted here against what a real run of the page's scenario wrote, and the
checkout those scenarios share behaves as the pages say.

The runs themselves are ``recipe_artifacts.write_artifacts()`` -- one pytest process per fixture
module, with ``narrativetrace-pytest`` loaded -- done once per process.
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path

import pytest
from narrativetrace_otel import OtelTraceEventListener
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from examples.recipes.checkout import order_service, services
from examples.recipes.checkout.domain import PaymentDeclinedError
from examples.recipes.checkout.observability_fixture import NarratedAndExportedStore
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.order_service_without_release import OrderServiceWithoutRelease
from examples.recipes.checkout.recipe_artifacts import (
    ACROSS_SERVICES,
    ACROSS_THREADS,
    ADD_LOGGING,
    APPROVED_DIR,
    COST,
    DEBUG,
    KEEP_OUT_OF_LOGS,
    OBSERVABILITY,
    REFACTORING,
    REVIEW_FLOW,
    TEST_FAILURE,
    RecipeRuns,
    page_dir,
    write_artifacts,
)
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import (
    ContextVarNarrativeContext,
    LoggingTraceConsumer,
    NarrativeTraceConfig,
    TracingLevel,
    trace_object,
)

_FIXED = "test_the_stock_is_released_when_the_card_is_declined"
_STALE = "test_the_customer_gets_an_order_id_for_their_keyboards"
_BUYS_TWO = "test_a_customer_buys_two_keyboards"
_DECLINED = "test_a_declined_card_saves_no_order"


@pytest.fixture(scope="module")
def runs() -> RecipeRuns:
    return write_artifacts()


def _narrative(slug: str, fixture: str, test: str, *, under: str = "") -> str:
    path = page_dir(slug) / under / "traces" / f"{fixture}_fixture" / f"{test}.md"
    return path.read_text(encoding="utf-8")


def _checkout() -> tuple[OrderService, InventoryService, OrderRepository]:
    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()
    return OrderService(stock, PaymentService(), repository), stock, repository


class TestTheCheckoutTheRecipesShare:
    def test_a_successful_order_reserves_charges_and_saves(self) -> None:
        checkout, stock, repository = _checkout()

        order_id = checkout.place_order("C-1", "SKU-KB", 2, "4242424242424242")

        assert order_id == "ORD-C-1-SKU-KB-2"
        assert stock.available_units("SKU-KB") == 3
        assert [order.amount_cents for order in repository.saved()] == [7998]

    def test_a_declined_card_releases_the_stock_and_saves_nothing(self) -> None:
        checkout, stock, repository = _checkout()

        with pytest.raises(PaymentDeclinedError):
            checkout.place_order("C-1", "SKU-KB", 2, PaymentService.DECLINING_CARD)

        assert stock.available_units("SKU-KB") == 5
        assert repository.saved() == []

    def test_the_checkout_before_the_fix_leaves_the_stock_reserved(self) -> None:
        stock = InventoryService("SKU-KB", 5)
        repository = OrderRepository()
        checkout = OrderServiceWithoutRelease(stock, PaymentService(), repository)

        with pytest.raises(PaymentDeclinedError):
            checkout.place_order("C-1", "SKU-KB", 2, PaymentService.DECLINING_CARD)

        assert stock.available_units("SKU-KB") == 3

    def test_asking_for_more_than_the_stock_raises_and_reserves_nothing(self) -> None:
        checkout, stock, repository = _checkout()

        with pytest.raises(ValueError, match=r"\Anot enough stock for SKU-KB\Z"):
            checkout.place_order("C-1", "SKU-KB", 6, "4242424242424242")

        assert stock.available_units("SKU-KB") == 5
        assert repository.saved() == []

    def test_an_unknown_sku_has_no_units(self) -> None:
        assert InventoryService("SKU-KB", 5).available_units("SKU-XX") == 0

    def test_the_saved_list_is_a_copy(self) -> None:
        checkout, _, repository = _checkout()
        checkout.place_order("C-1", "SKU-KB", 1, "4242424242424242")

        repository.saved().clear()

        assert len(repository.saved()) == 1


class TestAddLoggingToThisService:
    def test_the_checkout_writes_no_log_statement_of_its_own(self) -> None:
        for module in (order_service, services):
            assert "logging" not in inspect.getsource(module)

    def test_every_call_reaches_the_projects_own_logger_with_names_and_values(
        self, runs: RecipeRuns
    ) -> None:
        assert runs.add_logging.exit_code == 0

        log = (page_dir(ADD_LOGGING) / "checkout.log").read_text(encoding="utf-8").splitlines()

        prefix = "DEBUG [solid wand romps] [narrativetrace] - "
        assert log == [
            prefix + line
            for line in (
                '→ OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, '
                "card_number: [REDACTED])",
                '→ InventoryService.reserve(sku: "SKU-KB", quantity: 2)',
                "← returned: null",
                '→ PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, '
                "card: [REDACTED])",
                '← returned: "PAY-C-1234-7998"',
                '→ OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", '
                'customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))',
                "← returned: null",
                '← returned: "ORD-C-1234-SKU-KB-2"',
            )
        ]

    def test_the_card_number_never_reaches_the_log_by_name_or_by_value(
        self, runs: RecipeRuns
    ) -> None:
        log = (page_dir(ADD_LOGGING) / "checkout.log").read_text(encoding="utf-8")

        assert runs.add_logging.exit_code == 0
        assert "4242424242424242" not in log


class TestHelpMeDebugAndFixThisBug:
    def test_the_reproduction_fails_only_against_the_code_before_the_fix(
        self, runs: RecipeRuns
    ) -> None:
        assert runs.debug.exit_code == 1
        (failure,) = runs.debug.verdicts
        assert failure.test == f"{_FIXED}_before_the_fix"
        assert failure.when == "call"
        assert failure.message.startswith("assert 3 == 5")

    def test_the_failing_narrative_shows_reserve_then_a_throwing_charge_and_no_release(
        self, runs: RecipeRuns
    ) -> None:
        before = _narrative(DEBUG, "declined_payment", f"{_FIXED}_before_the_fix")

        assert runs.debug.exit_code == 1
        assert "**Result:** FAILED" in before
        assert "InventoryService.reserve" in before
        assert "❌ `PaymentDeclinedError`: card declined by the issuer" in before
        assert "InventoryService.release" not in before

    def test_the_fixed_narrative_releases_between_the_charge_and_the_failure(
        self, runs: RecipeRuns
    ) -> None:
        fixed = _narrative(DEBUG, "declined_payment", _FIXED)

        assert runs.debug.exit_code == 1
        assert "**Result:** PASSED" in fixed
        assert fixed.index("PaymentService.charge") < fixed.index("InventoryService.release")

    def test_the_card_number_is_redacted_by_value_under_a_name_the_deny_list_does_not_know(
        self, runs: RecipeRuns
    ) -> None:
        fixed = _narrative(DEBUG, "declined_payment", _FIXED)

        assert runs.debug.exit_code == 1
        assert "card: `[REDACTED]`" in fixed
        assert PaymentService.DECLINING_CARD not in fixed

    def test_the_committed_baseline_still_pins_the_fixed_flow(self, runs: RecipeRuns) -> None:
        assert runs.debug_under_approval.exit_code == 0
        assert runs.debug_under_approval.verdicts == []
        approved = page_dir(DEBUG) / "approved" / "declined_payment_fixture"
        assert list(approved.glob("*.received.nt")) == []

    def test_the_committed_baseline_is_exactly_the_structure_the_fixed_run_wrote(
        self, runs: RecipeRuns
    ) -> None:
        name = f"declined_payment_fixture/{_FIXED}"
        written = page_dir(DEBUG) / "structural" / f"{name}.nt"
        committed = APPROVED_DIR / f"{name}.approved.nt"

        assert runs.debug.exit_code == 1
        assert committed.read_text(encoding="utf-8") == written.read_text(encoding="utf-8")


class TestWhyDidThisTestFail:
    def test_the_failing_run_reports_the_assertion_and_writes_its_own_narrative(
        self, runs: RecipeRuns
    ) -> None:
        assert runs.test_failure.exit_code == 1
        (failure,) = runs.test_failure.verdicts
        assert failure.test == _STALE
        assert "ORD-C-1234-SKU-KB-1" in failure.message
        assert "ORD-C-1234-SKU-KB-2" in failure.message

    def test_every_span_agrees_and_nothing_threw(self, runs: RecipeRuns) -> None:
        narrative = _narrative(TEST_FAILURE, "stale_expectation", _STALE)

        assert runs.test_failure.exit_code == 1
        assert "**Result:** FAILED" in narrative
        assert "error_count: 0" in narrative
        assert "quantity: `2`" in narrative
        assert "amount_cents: `7998`" in narrative

    def test_the_recorded_assertion_text_is_the_runners_message_and_nothing_else(
        self, runs: RecipeRuns
    ) -> None:
        recorded = (page_dir(TEST_FAILURE) / "assertion-failure.txt").read_text(encoding="utf-8")

        assert runs.test_failure.exit_code == 1
        assert recorded == runs.test_failure.verdicts[0].message.strip() + "\n"


class TestReviewAComplexFlowBeforeChangingIt:
    def test_detail_carries_the_values_and_summary_carries_the_shape(
        self, runs: RecipeRuns
    ) -> None:
        detail = _narrative(REVIEW_FLOW, "checkout_review", _BUYS_TWO, under="detail")
        summary = _narrative(REVIEW_FLOW, "checkout_review", _BUYS_TWO, under="summary")

        assert (runs.review_detail.exit_code, runs.review_summary.exit_code) == (0, 0)
        assert "quantity: `2`" in detail
        assert "amount_cents: `7998`" in detail
        assert "[REDACTED]" in detail
        assert "amount_cents: `7998`" not in summary
        assert '→ `"ORD-C-1234-SKU-KB-2"`' in summary

    def test_the_structural_trace_of_the_same_run_carries_no_values(self, runs: RecipeRuns) -> None:
        path = (
            page_dir(REVIEW_FLOW)
            / "detail"
            / "structural"
            / "checkout_review_fixture"
            / f"{_BUYS_TWO}.nt"
        )

        structural = path.read_text(encoding="utf-8")

        assert runs.review_detail.exit_code == 0
        assert "OrderService.place_order(customer_id, sku, quantity, card_number)" in structural
        for value in ("C-1234", "SKU-KB", "7998", "REDACTED"):
            assert value not in structural

    def test_the_log_of_the_same_flow_carries_the_values_the_structural_trace_lacks(
        self, runs: RecipeRuns
    ) -> None:
        log = (page_dir(REVIEW_FLOW) / "detail" / "checkout.log").read_text(encoding="utf-8")

        assert runs.review_detail.exit_code == 0
        assert len(log.splitlines()) == 8
        assert "amount_cents: 7998" in log


class TestReviewARefactoringDidBehaviourChange:
    def test_the_committed_baseline_matches_the_shipped_checkout(self, runs: RecipeRuns) -> None:
        assert runs.refactoring_as_shipped.exit_code == 0
        assert runs.refactoring_as_shipped.verdicts == []
        approved = page_dir(REFACTORING) / "approved-as-shipped" / "refactored_checkout_fixture"
        assert list(approved.glob("*.received.nt")) == []

    def test_dropping_the_release_is_rejected_by_a_diff_that_names_it(
        self, runs: RecipeRuns
    ) -> None:
        run = runs.refactoring_dropped_the_release

        assert run.exit_code == 1
        (rejection,) = run.verdicts
        assert rejection.message.splitlines()[0] == (
            "Structure changed against the approved trace (-1 call InventoryService.release):"
        )
        assert "-  #1.3 - InventoryService.release(sku, quantity)" in rejection.message

    def test_the_tests_own_assertions_still_pass_and_only_the_approval_fails(
        self, runs: RecipeRuns
    ) -> None:
        (rejection,) = runs.refactoring_dropped_the_release.verdicts

        assert (rejection.test, rejection.when) == (_DECLINED, "teardown")

    def test_the_rejected_structure_is_offered_for_review_beside_the_baseline(
        self, runs: RecipeRuns
    ) -> None:
        folder = (
            page_dir(REFACTORING)
            / "approved-after-the-refactoring"
            / ("refactored_checkout_fixture")
        )
        received = folder / f"{_DECLINED}.received.nt"

        assert runs.refactoring_dropped_the_release.exit_code == 1
        assert "InventoryService.release" not in received.read_text(encoding="utf-8")
        assert (folder / f"{_DECLINED}.approved.nt").is_file()

    def test_the_rejection_message_names_a_repository_relative_received_path(
        self, runs: RecipeRuns
    ) -> None:
        recorded = (page_dir(REFACTORING) / "approval-rejection.txt").read_text(encoding="utf-8")

        assert runs.refactoring_dropped_the_release.exit_code == 1
        assert (
            "Received: examples/recipes/checkout/build/review-a-refactoring-did-behaviour-change/"
            "approved-after-the-refactoring/refactored_checkout_fixture/"
            f"{_DECLINED}.received.nt\n"
        ) in recorded


_TRACE = "c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7"


class TestFollowOneRequestAcrossServices:
    def test_the_payment_services_root_adopts_the_trace_the_header_named(
        self, runs: RecipeRuns
    ) -> None:
        # The proof is the fixture's own assertions (it fails the run if the trace id did not
        # cross the wire); the exit code is the page's "this was asserted" claim.
        assert runs.across_services.exit_code == 0
        assert runs.across_services.verdicts == []

    def test_both_services_lines_carry_the_one_trace_id_and_differ_by_logger(
        self, runs: RecipeRuns
    ) -> None:
        log = (page_dir(ACROSS_SERVICES) / "checkout.log").read_text(encoding="utf-8")

        assert runs.across_services.exit_code == 0
        caller, callee = "DEBUG [narrativetrace] ", "DEBUG [narrativetrace.payments] "
        assert [line.split(" - ")[0] for line in log.splitlines()] == [
            *[f"{caller}[{_TRACE}]"] * 4,
            *[f"{callee}[{_TRACE}]"] * 2,
            *[f"{caller}[{_TRACE}]"] * 4,
        ]

    def test_the_card_never_reaches_either_services_lines(self, runs: RecipeRuns) -> None:
        log = (page_dir(ACROSS_SERVICES) / "checkout.log").read_text(encoding="utf-8")

        assert runs.across_services.exit_code == 0
        assert "4242424242424242" not in log
        assert log.count("card: [REDACTED]") == 2

    def test_the_callers_structural_trace_has_the_four_calls_and_no_values(
        self, runs: RecipeRuns
    ) -> None:
        structural = (page_dir(ACROSS_SERVICES) / "checkout.nt").read_text(encoding="utf-8")

        assert runs.across_services.exit_code == 0
        assert structural == (
            "scenario: A customer checks out against the payment service\n"
            "\n"
            "#1 - OrderService.place_order(customer_id, sku, quantity, card_number) → value\n"
            "  #1.1 - InventoryService.reserve(sku, quantity) → value\n"
            "  #1.2 - PaymentService.charge(customer_id, amount_cents, card) → value\n"
            "  #1.3 - OrderRepository.save(order) → value\n"
        )

    def test_the_payment_services_narrative_is_its_own_one_span_tree(
        self, runs: RecipeRuns
    ) -> None:
        narrative = (page_dir(ACROSS_SERVICES) / "payment-service.md").read_text(encoding="utf-8")

        assert runs.across_services.exit_code == 0
        assert narrative.startswith(
            '- **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, '
            'card: `[REDACTED]`) → `"PAY-C-1234-7998"`'
        )
        assert narrative.count("#") == 1


class TestKeepSecretsOutOfTheLogs:
    def test_the_run_passes_its_own_read_back_of_the_log(self, runs: RecipeRuns) -> None:
        # The proof is the fixture's absence assertions over the file its logger wrote.
        assert runs.secrets.exit_code == 0
        assert runs.secrets.verdicts == []

    def test_the_three_secret_bearing_parameters_are_redacted_and_the_rest_is_written(
        self, runs: RecipeRuns
    ) -> None:
        log = (page_dir(KEEP_OUT_OF_LOGS) / "checkout.log").read_text(encoding="utf-8").splitlines()

        assert runs.secrets.exit_code == 0
        assert len(log) == 10
        assert log[0].endswith(
            '→ CustomerAccounts.sign_in(customer_id: "C-1234", password: [REDACTED])'
        )
        assert log[2].endswith(
            '→ OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, '
            "card_number: [REDACTED])"
        )
        assert log[5].endswith(
            '→ PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])'
        )

    def test_neither_secret_is_in_the_log_or_the_trace_file(self, runs: RecipeRuns) -> None:
        log = (page_dir(KEEP_OUT_OF_LOGS) / "checkout.log").read_text(encoding="utf-8")
        narrative = _narrative(
            KEEP_OUT_OF_LOGS, "secrets", "test_a_checkout_with_a_password_and_a_card_writes_neither"
        )

        assert runs.secrets.exit_code == 0
        for surface in (log, narrative):
            assert "orchid-trombone-77" not in surface
            assert "4242424242424242" not in surface
        assert narrative.count("[REDACTED]") == 3

    def test_the_customer_id_is_written_in_full_because_it_is_not_a_secret(
        self, runs: RecipeRuns
    ) -> None:
        log = (page_dir(KEEP_OUT_OF_LOGS) / "checkout.log").read_text(encoding="utf-8")

        assert runs.secrets.exit_code == 0
        assert log.count('customer_id: "C-1234"') == 3


class TestFollowAFlowAcrossThreads:
    def test_the_run_passes_its_own_proof_that_the_children_came_home(
        self, runs: RecipeRuns
    ) -> None:
        # The proof is the fixture's assertions: each child carries the root's trace id, names the
        # root as its parent, and records the worker thread it ran on.
        assert runs.across_threads.exit_code == 0
        assert runs.across_threads.verdicts == []

    def test_the_workers_lines_carry_the_customers_trace_id_on_the_workers_thread(
        self, runs: RecipeRuns
    ) -> None:
        log = (page_dir(ACROSS_THREADS) / "checkout.log").read_text(encoding="utf-8")

        assert runs.across_threads.exit_code == 0
        trace = f"[{_TRACE}] - "
        assert f"[checkout-worker_0] [narrativetrace] {trace}→ InventoryService.reserve" in log
        assert f"[checkout-worker_0] [narrativetrace] {trace}→ FraudCheckService.approve" in log
        assert "[MainThread] [narrativetrace] [] - ⑂ fork group created [groupId: fork-1]" in log
        assert (
            "[MainThread] [narrativetrace] [] - ⑃ fork joined [groupId: fork-1, members: 2]" in log
        )

    def test_each_child_is_logged_twice_but_recorded_once(self, runs: RecipeRuns) -> None:
        log = (page_dir(ACROSS_THREADS) / "checkout.log").read_text(encoding="utf-8")
        structural = (page_dir(ACROSS_THREADS) / "checkout.nt").read_text(encoding="utf-8")

        assert runs.across_threads.exit_code == 0
        assert log.count("→ InventoryService.reserve") == 2
        assert structural.count("InventoryService.reserve") == 1
        assert "  ~ fork [2]\n" in structural

    def test_a_task_submitted_without_the_handover_runs_under_a_trace_id_nobody_is_searching_for(
        self, runs: RecipeRuns
    ) -> None:
        # The fixture asserts the worker's trace id differs from the caller's and that the
        # caller's captured trace has no reserve; here, that the lines say the same.
        assert runs.without_handover.exit_code == 0
        log = (page_dir(ACROSS_THREADS) / "no-handover" / "checkout.log").read_text(
            encoding="utf-8"
        )
        assert f"[{_TRACE}]" not in log
        assert "[checkout-worker_0] [narrativetrace] [" in log


class TestSendTracesToTheObservabilityStackYouAlreadyRun:
    def test_the_run_passes_its_own_span_tree_redaction_and_typing_assertions(
        self, runs: RecipeRuns
    ) -> None:
        assert runs.observability.exit_code == 0
        assert runs.observability.verdicts == []

    def test_the_log_lines_are_the_narration_the_logger_always_wrote(
        self, runs: RecipeRuns
    ) -> None:
        log = (page_dir(OBSERVABILITY) / "checkout.log").read_text(encoding="utf-8")

        assert runs.observability.exit_code == 0
        assert len(log.splitlines()) == 8
        assert all(
            line.startswith("DEBUG [solid wand romps] [narrativetrace] - ")
            for line in log.splitlines()
        )
        assert "4242424242424242" not in log

    def test_the_exported_spans_name_the_root_as_every_childs_parent_and_carry_no_card(
        self, runs: RecipeRuns
    ) -> None:
        dump = (page_dir(OBSERVABILITY) / "exported-spans.txt").read_text(encoding="utf-8")

        assert runs.observability.exit_code == 0
        assert dump.count("  parent: OrderService.place_order\n") == 3
        assert dump.count("  parent: (none — this is the root)\n") == 1
        assert "narrative.param.card" not in dump
        assert "4242424242424242" not in dump

    def test_summary_exports_the_same_spans_without_parameter_attributes_and_off_exports_none(
        self,
    ) -> None:
        summary = _exported_spans_at(TracingLevel.SUMMARY)

        assert len(summary) == 4
        assert not any(
            key.startswith("narrative.param.") for span in summary for key in span.attributes or {}
        )
        assert _exported_spans_at(TracingLevel.OFF) == ()


def _exported_spans_at(level: TracingLevel) -> tuple[ReadableSpan, ...]:
    """One checkout through the page's composed store, at ``level``."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    store = NarratedAndExportedStore(
        LoggingTraceConsumer(logging.getLogger("narrativetrace-test")),
        OtelTraceEventListener(provider.get_tracer("narrativetrace")),
    )
    context = ContextVarNarrativeContext(NarrativeTraceConfig(level), store=store)
    checkout = trace_object(
        OrderService(
            trace_object(InventoryService("SKU-KB", 5), context),
            trace_object(PaymentService(), context),
            trace_object(OrderRepository(), context),
        ),
        context,
    )
    checkout.place_order("C-1", "SKU-KB", 2, "4242424242424242")
    return exporter.get_finished_spans()


_DECLINED_TRACE = Path("traces/declined_payment_fixture") / f"{_FIXED}.md"
_REVIEW_TRACE = Path("traces/checkout_review_fixture") / f"{_BUYS_TWO}.md"


class TestTraceInProductionWithoutTheCost:
    def test_errors_keeps_the_failed_run_whole_including_the_calls_that_returned(
        self, runs: RecipeRuns
    ) -> None:
        errors = (page_dir(COST) / "errors" / _DECLINED_TRACE).read_text(encoding="utf-8")

        assert runs.cost_errors.exit_code == 0
        for call in (
            "OrderService.place_order",
            "InventoryService.reserve",
            "PaymentService.charge",
            "InventoryService.release",
        ):
            assert call in errors
        assert "error_count: 2" in errors

    def test_a_successful_run_writes_no_artifact_at_errors_and_does_at_detail(
        self, runs: RecipeRuns
    ) -> None:
        # The control: the same path IS written when the level keeps successful runs, so the
        # absence is the level's doing and not a path that was never right.
        assert runs.cost_detail_successful.exit_code == 0
        assert runs.cost_errors_successful.exit_code == 0
        assert (page_dir(COST) / "detail-successful" / _REVIEW_TRACE).is_file()
        assert not (page_dir(COST) / "errors-successful" / _REVIEW_TRACE).exists()

    def test_detail_carries_the_values_errors_suppresses(self, runs: RecipeRuns) -> None:
        detail = (page_dir(COST) / "detail" / _DECLINED_TRACE).read_text(encoding="utf-8")
        errors = (page_dir(COST) / "errors" / _DECLINED_TRACE).read_text(encoding="utf-8")

        assert (runs.cost_detail.exit_code, runs.cost_errors.exit_code) == (0, 0)
        assert 'customer_id: `"C-1234"`' in detail
        assert "customer_id: ``" in errors
        assert "C-1234" not in errors

    def test_both_levels_still_redact_the_card_number(self, runs: RecipeRuns) -> None:
        detail = (page_dir(COST) / "detail" / _DECLINED_TRACE).read_text(encoding="utf-8")
        errors = (page_dir(COST) / "errors" / _DECLINED_TRACE).read_text(encoding="utf-8")

        assert (runs.cost_detail.exit_code, runs.cost_errors.exit_code) == (0, 0)
        for narrative in (detail, errors):
            assert "[REDACTED]" in narrative
            assert PaymentService.DECLINING_CARD not in narrative

    def test_off_creates_no_event_at_all(self) -> None:
        context = ContextVarNarrativeContext(NarrativeTraceConfig(TracingLevel.OFF))
        stock = InventoryService("SKU-KB", 5)
        inventory = trace_object(stock, context)

        inventory.reserve("SKU-KB", 2)

        assert stock.available_units("SKU-KB") == 3
        assert context.capture_trace().is_empty
