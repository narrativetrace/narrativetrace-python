# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The ``init-prompt-fastapi-project`` grader's request-scope verdict, rehearsed BEFORE any trial on
a solved server's output and on every near miss the case exists to catch; each row asserts the
grader's REASON. Starting the real server against built wheels is rehearsed by hand (the case's
README), because it resolves and downloads packages."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "add-narrative-tracing"))

import run_the_server as grader

_A, _B = grader.IDS


def _trace(customer_id: str) -> str:
    return (
        f'InvoiceService.issue_invoice(customer_id: "{customer_id}", card_token: [REDACTED], '
        f'amount_cents: 4200) → "INV-{customer_id}-4200" — 0ms'
    )


_ACCESS = 'INFO:     127.0.0.1:5000 - "GET /invoices/{id} HTTP/1.1" 200 OK'


class TestVerdict:
    def test_each_request_printing_its_own_trace_passes(self) -> None:
        output = "\n".join([_trace(_A), _ACCESS.format(id=_A), _trace(_B), _ACCESS.format(id=_B)])
        assert grader.verdict(output, "InvoiceService", (200, 200)) is None

    def test_each_trace_printed_twice_stdout_and_logger_still_passes(self) -> None:
        output = "\n".join([_trace(_A), "log: " + _trace(_A), _trace(_B), "log: " + _trace(_B)])
        assert grader.verdict(output, "InvoiceService", (200, 200)) is None

    def test_a_shared_growing_trace_is_not_request_scoped(self) -> None:
        output = "\n".join([_trace(_A), _trace(_A), _trace(_B)])
        reason = grader.verdict(output, "InvoiceService", (200, 200))
        assert reason == (
            "expected each request's own trace, printed once per request; the ids were printed "
            f"{{'{_A}': 2, '{_B}': 1}} times -- an earlier request's call came back with a later "
            "one, so the trace is not request-scoped"
        )

    def test_no_trace_at_all_names_both_requests(self) -> None:
        output = "\n".join([_ACCESS.format(id=_A), _ACCESS.format(id=_B)])
        assert grader.verdict(output, "InvoiceService", (200, 200)) == (
            "expected a rendered trace line naming InvoiceService for each request; none for "
            f"{[_A, _B]}"
        )

    def test_a_trace_of_another_class_with_the_same_suffix_does_not_count(self) -> None:
        output = "\n".join([_trace(_A).replace("InvoiceService", "MyInvoiceService"), _trace(_B)])
        assert grader.verdict(output, "InvoiceService", (200, 200)) == (
            "expected a rendered trace line naming InvoiceService for each request; none for "
            f"{[_A]}"
        )

    @pytest.mark.parametrize("statuses", [(500, 200), (200, 404), (0, 0)])
    def test_a_request_that_did_not_answer_200_fails_first(self, statuses: tuple[int, int]) -> None:
        output = "\n".join([_trace(_A), _trace(_B)])
        assert grader.verdict(output, "InvoiceService", statuses) == (
            f"expected every request to answer 200, got {list(statuses)}"
        )


class TestMain:
    @pytest.mark.parametrize(
        "argv", [[], ["InvoiceService", "billing.api:app"], ["S", "m:app", "/invoices/x"]]
    )
    def test_a_malformed_command_line_is_a_usage_error(self, argv: list[str]) -> None:
        assert grader.main(argv) == 2
