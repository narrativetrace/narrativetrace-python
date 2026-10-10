# Fixture: fastapi-service

The `init-prompt-fastapi-project` case's fixture (Phase 6 D4): a real, working FastAPI service that
does NOT have NarrativeTrace yet — one service class with one method, one route that calls it, and
a `pyproject.toml` declaring `fastapi` and `uvicorn` and nothing else.

Run it with `uv run uvicorn billing.api:app`, then `GET /invoices/<customer_id>`.

What the case measures is the doctor as the run-time oracle: the published init prompt says
nothing about FastAPI, so the agent learns that this project needs `narrativetrace-asgi` and
`NarrativeTraceMiddleware` from the doctor's `config.asgi-middleware` finding (directly, or through
the `add-narrative-tracing` skill's framework step). The grader starts the server, sends two
requests and expects each request's own trace in the server's output — request-scoped, so the
first request's call is never printed again with the second.

`card_token` is deliberate: it is on the always-on deny-list, so the first trace proves redaction
without anyone asking for it.
