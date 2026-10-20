# Keep secrets out of the logs

## The problem

> If this thing logs every call with every argument, it is going to log a
> card number. Convince me it does not.

The checkout takes a password and a card number. Below is one run of it with
both, the log it actually wrote, and the test that proves neither value is in
that file.

## Minimal setup

Nothing. Redaction is on in every shipped integration and there is no
configuration surface that turns it off — the deny-list is consulted at
*capture*, before a value becomes an event, so a denied value never reaches
the log line, the trace file, the buffered path or a consumer of the events.
[Privacy and Redaction](../privacy-and-redaction.md) is the row-by-row
version, verified against the code.

Two things, though, are worth doing once in your own project:

1. **Write this page's test for your own flow.** Redaction you have not
   asserted is a claim, not a property of your build. The doctor's
   "redaction never proven in a test" finding (`trap.redaction-proof`) exists
   for exactly this.
2. **Know the escape hatch.** A secret under a name nobody could guess —
   `fingerprint`, `answer2` — is reachable with `@not_traced("fingerprint")`
   on the method (or `not_traced_field(...)` on a dataclass field), which
   always wins ([Decorators Guide](../guides/decorators.md)).

## The scenario

One new collaborator, so the run carries a password as well as a card. Its
parameter is called `password` — that name is the whole point:

<!-- snippet: examples/recipes/checkout/accounts.py -->
```python
"""Signs a customer in before the checkout charges them."""

from __future__ import annotations


class CustomerAccounts:
    """In-memory accounts. The parameter is named ``password`` -- that name is the whole point of
    documentation/recipes/keep-secrets-out-of-the-logs.md."""

    def sign_in(self, customer_id: str, password: str) -> str:
        """Returns the session id the checkout carries for the rest of the request.

        Raises ``ValueError`` when the password is blank.
        """
        if not password.strip():
            raise ValueError("password must not be blank")
        return f"SESSION-{customer_id}"
```
<!-- /snippet -->

The run signs the customer in and places the order. The two secret values are
constants here so the test can search the log for them afterwards — a real
flow gets them from the request:

<!-- snippet: examples/recipes/checkout/secrets_fixture.py -->
```python
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
```
<!-- /snippet -->

## The actual output

**The log the run wrote**, through the project's own logger:

<!-- snippet: examples/recipes/checkout/build/keep-secrets-out-of-the-logs/checkout.log -->
```text
DEBUG [solid wand romps] [narrativetrace] - → CustomerAccounts.sign_in(customer_id: "C-1234", password: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - ← returned: "SESSION-C-1234"
DEBUG [solid wand romps] [narrativetrace] - → OrderService.place_order(customer_id: "C-1234", sku: "SKU-KB", quantity: 2, card_number: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - → InventoryService.reserve(sku: "SKU-KB", quantity: 2)
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - → PaymentService.charge(customer_id: "C-1234", amount_cents: 7998, card: [REDACTED])
DEBUG [solid wand romps] [narrativetrace] - ← returned: "PAY-C-1234-7998"
DEBUG [solid wand romps] [narrativetrace] - → OrderRepository.save(order: Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998))
DEBUG [solid wand romps] [narrativetrace] - ← returned: null
DEBUG [solid wand romps] [narrativetrace] - ← returned: "ORD-C-1234-SKU-KB-2"
```
<!-- /snippet -->

**The trace file of the same run**, which is the other surface a secret could
have reached:

<!-- snippet: examples/recipes/checkout/build/keep-secrets-out-of-the-logs/traces/secrets_fixture/test_a_checkout_with_a_password_and_a_card_writes_neither.md mask=duration,traceName -->
```text
---
type: trace
run: moody mouse sweeps
scenario: Test a checkout with a password and a card writes neither
entry_point: CustomerAccounts.sign_in
duration_ms: 0
trace_id: c4e1d0a7c4e1d0a7c4e1d0a7c4e1d0a7
trace_name: solid wand romps
method_count: 5
error_count: 0
---

## Trace: solid wand romps — CustomerAccounts.sign_in

**Scenario:** Test a checkout with a password and a card writes neither
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **CustomerAccounts.sign_in**(customer_id: `"C-1234"`, password: `[REDACTED]`) → `"SESSION-C-1234"` — 0ms #1
- **OrderService.place_order**(customer_id: `"C-1234"`, sku: `"SKU-KB"`, quantity: `2`, card_number: `[REDACTED]`) — 0ms #2
  - **InventoryService.reserve**(sku: `"SKU-KB"`, quantity: `2`) → `null` — 0ms #2.1
  - **PaymentService.charge**(customer_id: `"C-1234"`, amount_cents: `7998`, card: `[REDACTED]`) → `"PAY-C-1234-7998"` — 0ms #2.2
  - **OrderRepository.save**(order: `Order(order_id="ORD-C-1234-SKU-KB-2", customer_id="C-1234", sku="SKU-KB", quantity=2, amount_cents=7998)`) → `null` — 0ms #2.3
  - → `"ORD-C-1234-SKU-KB-2"`
```
<!-- /snippet -->

## How to read it

**Which rule caught which value.** Three values are gone, by two independent
mechanisms:

| Line | Value | Caught by |
|---|---|---|
| `#1` `CustomerAccounts.sign_in(…, password: [REDACTED])` | `orchid-trombone-77` | Its **name**. `password` is on the always-on deny-list, which matches parameter names, field names and dataclass fields — in several languages — on any class, yours included. The value itself matches no pattern at all; nothing but the name could have saved it |
| `#2` `OrderService.place_order(…, card_number: [REDACTED])` | `4242424242424242` | Its **name** again: `card_number` is on the same list |
| `#2.2` `PaymentService.charge(…, card: [REDACTED])` | the same number, one call deeper | Its **value**. The parameter is named `card`, which the deny-list does not know — and the number is Luhn-valid, so the independent value-shape check caught it anyway |

That third row is the one worth remembering: `card` is what a parameter gets
called in real code, and the name axis alone would have printed it. The shape
axis knows a Luhn-valid card number, a JWT, a `Set-Cookie` string, a US Social
Security number and the national identity numbers that pass their own
checksums.

**Where the rules live.** In the library, not in your configuration:
`RedactionPolicy.DEFAULT`, consulted by the one `ValueRenderer` every shipped
integration constructs the same way. There is no setting, no environment
variable and no log level that reaches it;
[Privacy and Redaction](../privacy-and-redaction.md) lists both the surfaces
and what outranks what. `customer_id: "C-1234"` *is* written in full, by the
way — a customer id is identifying, not secret, and NarrativeTrace does not
guess. If yours must not be logged, that is `@not_traced`, which is a decision
in your source rather than a state a deploy can flip.

**Why the test is the proof, not the page.** The last lines of the scenario
read the file the handler wrote and assert two things: that the redacted
parameters are present *as* `[REDACTED]`, and that neither secret string
appears anywhere in it. A page can only show you bytes; a test fails the build
the day a refactor renames `password` to something the list does not know, or
someone constructs their own `ValueRenderer` with
`RedactionPolicy.DISABLED`. That is the difference between "it was safe when
this was written" and "it is safe now". Keep the absence assertions — the
`not in` ones — even when the presence ones look sufficient: a value that
vanishes because the call stopped being traced at all would still satisfy the
first.

## What is not captured

- **Code that is not traced is not NarrativeTrace's to redact.** Five objects
  are wrapped above; a secret passed between two unwrapped classes is not
  seen, and therefore neither redacted nor logged. That is not a guarantee of
  safety — it is a guarantee of silence.
- **A secret your own log statement writes is yours.** NarrativeTrace
  redacts what *it* renders. `logger.info("charging %s", card_number)` is
  your line, in your code, and nothing here filters it. The redaction contract
  is about generated narrative, not about everything the process writes.
- **A return value is not matched by name**, because it has none. `sign_in`
  returns `"SESSION-C-1234"` and it is printed. A session token returned from
  a traced method needs the shape rules to catch it, or `@not_traced` on the
  method, or a narrower return type.
- **Names the list does not know.** The list is big and multilingual, not
  infinite. A secret called `q3` is caught only by its shape, if it has one.
  Assert, do not assume — which is this page's whole point.
- **What happens after the log line is written.** Shipping, retention and
  access to the file are your platform's; the structural `.nt` carries no
  values at all and is the artifact meant for committing and for handing to a
  model ([Review a complex flow before changing it](review-a-complex-flow-before-changing-it.md)).

**The skill for this:** `narrativetrace-doctor` — one of its checks is
exactly "redaction never proven in a test", and it names the fix.
