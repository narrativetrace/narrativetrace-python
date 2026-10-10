# billing

Checkout for the billing service. Invoices are issued in euro; a card is charged in its own
currency, converted at today's rate.

- `billing.checkout_service.CheckoutService.checkout` issues the invoice, looks up the card's
  currency in `CustomerDirectory`, converts the amount with a `CurrencyConverter` and authorizes and
  confirms the converted amount through `PaymentGateway`.
- `billing.rate_table_converter.RateTableConverter` converts with the rates `DailyRates` publishes.

```bash
uv run pytest
```

NarrativeTrace is installed: `tests/test_checkout_flow.py` drives a whole checkout through the real
collaborators with the `narrative_trace` fixture, so a run writes its trace under
`narrative-traces/`.
