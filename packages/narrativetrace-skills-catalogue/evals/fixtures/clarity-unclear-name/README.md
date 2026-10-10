# Fixture: clarity-unclear-name

The `add-narrativetrace-clarity` happy-path case's fixture: a small Python service that WORKS and
whose names say little about what it does. `OrderService.proc(d, x)` places an order,
`OrderService.calc(val, tmp)` prices one, `InvoiceFormatter.fmt(o)` writes an invoice line.

It is a git repository when a trial starts (`case.json` declares `"vcs": "git"`), declares no
NarrativeTrace dependency (adding the clarity gate is the agent's job), and carries a test that
calls `proc` BY KEYWORD, so a rename that moves the definition but not its callers fails the
project's own suite rather than slipping through.

Left as it is, the gate flags it: seven HIGH issues, and `OrderService` and `InvoiceFormatter`
score 0.47 and 0.44. `tests/test_clarity_eval_fixture.py` holds that, and holds that a solved copy
(`place_order(customer_id, quantity)`, `total_price(unit_price, quantity)`,
`format_invoice(order_id)`) passes the case's gate with every test still green.
