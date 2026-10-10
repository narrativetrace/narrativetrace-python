# billing

Checkout for the billing service: issue the invoice, take the card payment, record it.

- `billing.checkout_service.CheckoutService.checkout` issues the invoice through `InvoiceService`
  and runs the payment through shopkit's `CheckoutFlow` against our `PaymentGateway`.
- Side effects of a successful payment hang off shopkit's checkout hooks — `billing.compose` is
  where they are registered (the ledger entry today). Register a new one there.
- `billing.late_fees.fee_for` prices an overdue invoice.

```bash
uv run pytest
```

NarrativeTrace is installed: `tests/test_checkout_flow.py` drives a whole checkout through the real
collaborators with the `narrative_trace` fixture, so a run writes its trace under
`narrative-traces/`.
