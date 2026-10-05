# Fixture: existing-service

The `init-prompt-existing-project` case's fixture: a real, working Python project that does NOT
have NarrativeTrace yet — one service class with one method, a `main.py` that calls it, and a
`pyproject.toml` declaring neither `narrativetrace` nor anything else.

That shape is the published init prompt's step 2, second half: "Otherwise work inside the existing
project and trace one real service boundary." An agent given this directory must trace
`InvoiceService` itself, not add a demo class beside it — so the grader asserts both that the
program's own output names `InvoiceService` and that `src/billing/invoice_service.py` is still
there afterwards.

`customer_id`/`card_token` are deliberate: `card_token` is on the always-on deny-list, so the
first trace this project produces proves redaction without anyone asking for it.
