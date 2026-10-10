# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The two normalisations and checks a draft performs on a project's own text before the gate reads
it: the home-path rewrite, and whether a file really is a structural trace.
"""

from __future__ import annotations

import pytest

from narrativetrace_tooling.feedback.home_paths import to_tilde
from narrativetrace_tooling.feedback.structural_trace import looks_structural

_REAL_TRACE = """scenario: Weekend trip settles with three transfers

- TripSettlementService.record_expense(trip_name, expense)
  - ExpenseValidator.ensure_valid(expense)
  - TripLedger.record_expense(trip_name, expense)
- TripSettlementService.settle_trip(trip_name) → value
  - TripLedger.expenses_of(trip_name) → value
  ~ fork [2]
    - BalanceCalculator.compute_balances(expenses) → value
    - StockService.check() → value
"""
"""The published grammar's example as written before span ids — an id-free ``.approved.nt``
still committed in a project must keep reading as structural."""


class TestToTilde:
    @pytest.mark.parametrize(
        ("path", "rewritten"),
        [
            ("/Users/ada/work/orders", "~/work/orders"),
            ("/home/ada/work/orders", "~/work/orders"),
            ("C:\\Users\\ada\\work", "~\\work"),
            ("/Users/ada", "~"),
        ],
        ids=["macos", "linux", "windows", "no-trailing-segment"],
    )
    def test_rewrites_a_home_directory_and_keeps_what_follows_it(
        self, path: str, rewritten: str
    ) -> None:
        assert to_tilde(path) == rewritten

    @pytest.mark.parametrize(
        "path",
        ["/usr/share/ada/data", "/home", "build/narrativetrace", "~/work/orders"],
        ids=["not-a-home-root", "no-account-segment", "relative", "already-rewritten"],
    )
    def test_leaves_a_path_that_names_nobody_alone(self, path: str) -> None:
        """A rewrite that was eager here would turn an ordinary path into ``~`` and make the report
        wrong instead of safe."""
        assert to_tilde(path) == path

    def test_rewrites_every_occurrence_in_a_sentence(self) -> None:
        sentence = "copied /Users/ada/a.nt over /Users/ada/b.nt"

        assert to_tilde(sentence) == "copied ~/a.nt over ~/b.nt"

    def test_the_rewrite_is_idempotent(self) -> None:
        once = to_tilde("/Users/ada/work/orders")

        assert to_tilde(once) == once

    def test_reads_text_and_refuses_none(self) -> None:
        with pytest.raises(TypeError, match=r"never None"):
            to_tilde(None)  # type: ignore[arg-type]


class TestLooksStructural:
    def test_the_published_grammars_own_example_parses(self) -> None:
        assert looks_structural(_REAL_TRACE)

    @pytest.mark.parametrize(
        "content",
        [
            "scenario: Order is placed\n\n- OrderService.place_order(customer_id)\n",
            "scenario: Order is placed\n\n- OrderService.place_order(customer_id) → value\n",
            "scenario: Order is placed\n\n- Inventory.reserve(sku) !! ValueError\n",
            "scenario: Order is placed\n\n- Inventory.reserve(sku) ?? incomplete\n",
            "scenario: Order is placed\n\n- Inventory.reserve()\n",
            "scenario: Order is placed #2\n\n~ async [2]\n",
            "scenario: Order is placed\n\n~ fire-and-forget\n",
        ],
        ids=[
            "void-outcome",
            "returned",
            "threw",
            "incomplete",
            "no-parameters",
            "async-group",
            "fire-and-forget",
        ],
    )
    def test_every_shape_the_grammar_allows_parses(self, content: str) -> None:
        assert looks_structural(content)

    @pytest.mark.parametrize(
        "content",
        [
            "",
            "- OrderService.place_order(customer_id)\n",
            "scenario:\n\n- OrderService.place_order(customer_id)\n",
            'scenario: Order is placed\n\n- OrderService.place_order(customer_id: "C-1")\n',
            'scenario: Order is placed\n\n- OrderService.place_order(customer_id) → "ORD-1"\n',
            "scenario: Order is placed\n\n- place_order(customer_id)\n",
            "scenario: Order is placed\n\nINFO  starting up\n",
            "scenario: Order is placed\n\n- OrderService.place_order(customer_id) — 1ms\n",
            "scenario: Order is placed\n\n- a bullet with no call on it\n",
            "scenario: Order is placed\n\n- OrderService.place_order)customer_id(\n",
            "scenario: Order is placed\n\n~ fork [2\n",
        ],
        ids=[
            "empty",
            "no-header",
            "blank-scenario-name",
            "rendered-call",
            "rendered-outcome",
            "unqualified-call",
            "a-log-line",
            "a-duration",
            "a-bullet-with-no-parentheses",
            "parentheses-the-wrong-way-round",
            "an-unclosed-marker",
        ],
    )
    def test_anything_else_is_not_a_structural_trace(self, content: str) -> None:
        """A file that passed the value-free rules while not being a structural trace at all is not
        the attachment the report promises, and attaching it would put an unreviewed file shape
        into a public issue."""
        assert not looks_structural(content)

    @pytest.mark.parametrize(
        "content",
        [
            "scenario: Test\r\n\r\n- Service.method(a) → value\r\n",
            "scenario: Test\r\n\r\n- Service.method(a)\r\n~ fork [2]\r\n  - Other.method(b)\r\n",
            "scenario: Test\n\n- Service.method(a)  \n~ fork [2]  \n",
        ],
        ids=["crlf-calls-only", "crlf-with-a-marker", "trailing-spaces"],
    )
    def test_a_line_ending_is_not_part_of_the_grammar(self, content: str) -> None:
        """The format is specified LF, and this check is deliberately tolerant on READ anyway —
        because the alternative turned out to be worse than tolerance, and INCONSISTENT.

        Call lines were already stripped, so a CRLF trace of nothing but calls parsed; marker lines
        were matched whole, so the same trace with a ``~ fork [2]`` in it did not. A Windows
        checkout with ``core.autocrlf=true`` therefore had a committed ``.approved.nt`` judged "not
        a structural trace" — the attachment silently absent — depending on whether the scenario
        happened to use concurrency. Found by the milestone's adversarial pass, which asked the
        question and declined to assert an answer.
        """
        assert looks_structural(content)

    def test_but_an_indented_header_is_still_not_one(self) -> None:
        """The tolerance is for the END of a line only. Admitting leading whitespace would accept
        a header nested inside something else, which is a different file shape entirely."""
        assert not looks_structural("  scenario: Test\n\n- Service.method(a)\n")

    def test_a_header_with_nothing_under_it_is_still_a_structural_trace(self) -> None:
        """A scenario that traced nothing is empty, not malformed — and a report about "nothing was
        traced" is a report we want."""
        assert looks_structural("scenario: Order is placed\n")

    def test_reads_content_and_refuses_none(self) -> None:
        with pytest.raises(TypeError, match=r"never None"):
            looks_structural(None)  # type: ignore[arg-type]


class TestSpanIds:
    """The ``.nt`` opens every span line with a position-path id (``#1.3``) since D8: a position
    is not a value, so the grammar accepts it — and nothing else that starts with ``#``."""

    _WITH_IDS = (
        "scenario: Weekend trip settles\n\n"
        "#1 - TripSettlementService.settle_trip(trip_name) → value\n"
        "  #1.1 - TripLedger.expenses_of(trip_name) → value\n"
        "  ~ fork [2]\n"
        "    #1.2 - BalanceCalculator.compute_balances(expenses) → value\n"
        "    #1.3 - StockService.check() !! LookupError\n"
        "  #1.4 ~ fire-and-forget\n"
        "    #1.4.1 - Audit.log(event)\n"
    )

    def test_a_trace_whose_lines_open_with_span_ids_is_structural(self) -> None:
        assert looks_structural(self._WITH_IDS) is True

    def test_a_crlf_trace_with_span_ids_is_structural(self) -> None:
        assert looks_structural(self._WITH_IDS.replace("\n", "\r\n")) is True

    @pytest.mark.parametrize(
        "line",
        [
            "#1. - A.b()",
            "#.1 - A.b()",
            "#1a - A.b()",
            "# - A.b()",
            "#1 #2 - A.b()",
            "#1\t- A.b()",
            "#\u0661 - A.b()",
            "#1 - A.b(customer_id: 7)",
            "#1 ~ fork [2] #1",
            "- A.b() #1.1",
        ],
    )
    def test_a_malformed_id_or_a_value_beside_an_id_is_not(self, line: str) -> None:
        assert looks_structural(f"scenario: s\n\n{line}\n") is False

    def test_a_header_does_not_take_an_id(self) -> None:
        assert looks_structural("#1 scenario: s\n\n#1 - A.b()\n") is False


class TestEveryLineIsRead:
    """Adversarial pass: lines end at LF, CR or CRLF — a CR-only file hid a value-bearing call line
    inside the header's line, and only published markers are markers."""

    @pytest.mark.parametrize(
        "content",
        ["scenario: x\r- Main.run(secret: 1)\r", "scenario: x\r\r#1 - Main.run(secret: 1)\r"],
    )
    def test_a_cr_only_file_with_a_value_line_is_not_structural(self, content: str) -> None:
        assert looks_structural(content) is False

    def test_a_cr_only_trace_is_structural(self) -> None:
        assert looks_structural("scenario: x\r\r#1 - Main.run(amount)\r") is True

    @pytest.mark.parametrize(
        "marker", ["~ detached", "~ fork", "~ async [x]", "~ fire-and-forget [2]"]
    )
    def test_an_unpublished_marker_is_not_structural(self, marker: str) -> None:
        assert looks_structural(f"scenario: s\n\n{marker}\n") is False

    @pytest.mark.parametrize(
        "marker", ["~ fork [2]", "~ async [3]", "~ fire-and-forget", "#1 ~ fire-and-forget"]
    )
    def test_every_published_marker_is(self, marker: str) -> None:
        assert looks_structural(f"scenario: s\n\n  {marker}\n") is True
