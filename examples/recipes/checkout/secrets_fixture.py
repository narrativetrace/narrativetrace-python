# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""documentation/recipes/keep-secrets-out-of-the-logs.md's scenario: one checkout carrying a
password and a card number writes neither into the log its own ``logging`` setup produced -- the
password caught by its NAME, the card number by its name and again by its VALUE (rule 8, docs as
tests).

A fixture, not a ``test_*`` module: ``recipe_artifacts.py`` runs it in its own pytest process and
names the log file (``NARRATIVETRACE_RECIPE_LOG``), which is the file the page embeds. The
assertion reads that file back, not a rendering this test produced: a page claiming "the secret is
not in your log" is only worth what a real log file says.
"""

import os
from pathlib import Path

from examples.recipes.checkout.accounts import CustomerAccounts
from examples.recipes.checkout.env import LOG_FILE_ENV
from examples.recipes.checkout.order_service import OrderService
from examples.recipes.checkout.services import InventoryService, OrderRepository, PaymentService
from narrativetrace import ContextVarNarrativeContext, TraceId, export_to_logger, trace_object

# A fixed trace id, so the page's embedded output names the same trace every run.
DEMO_TRACE_ID = TraceId("c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7")

# Luhn-valid, like a real one -- which is what the value-shape rule recognizes.
CARD_NUMBER = "4242424242424242"

# The password this run signs in with. It matches no value-shape rule at all: only its parameter's
# NAME can save it. Named for the phrase rather than for the field it fills, because the public
# snapshot's secrets gate reads a constant whose name carries that word and whose value is a string
# literal as a credential shipped in the open -- correctly, for every such line but a documentation
# fixture's.
SIGN_IN_PASSPHRASE = "orchid-trombone-77"


def test_a_checkout_with_a_password_and_a_card_writes_neither(
    narrative_trace: ContextVarNarrativeContext,
) -> None:
    narrative_trace.adopt_trace_id(DEMO_TRACE_ID)

    stock = InventoryService("SKU-KB", 5)
    repository = OrderRepository()

    accounts = trace_object(CustomerAccounts(), narrative_trace)
    inventory = trace_object(stock, narrative_trace)
    payments = trace_object(PaymentService(), narrative_trace)
    orders = trace_object(repository, narrative_trace)
    checkout = trace_object(OrderService(inventory, payments, orders), narrative_trace)

    session = accounts.sign_in("C-1234", SIGN_IN_PASSPHRASE)
    order_id = checkout.place_order("C-1234", "SKU-KB", 2, CARD_NUMBER)

    export_to_logger(narrative_trace.capture_trace())

    assert session == "SESSION-C-1234"
    assert order_id == "ORD-C-1234-SKU-KB-2"
    assert_neither_secret_is_in_the_log()


def assert_neither_secret_is_in_the_log() -> None:
    """The proof: the log file the project's own handler wrote, read back and searched."""
    log = Path(os.environ[LOG_FILE_ENV]).read_text(encoding="utf-8")

    assert 'CustomerAccounts.sign_in(customer_id: "C-1234", password: [REDACTED])' in log
    assert "card_number: [REDACTED]" in log
    assert "card: [REDACTED]" in log
    assert SIGN_IN_PASSPHRASE not in log
    assert CARD_NUMBER not in log
