# Fixture: existing-service-pytest

The `existing-service` project plus a pytest suite, and still NO NarrativeTrace: one service class
with one method, a `main.py` that calls it, and `tests/test_invoice_service.py` testing it. `pytest`
is a dev dependency; `narrativetrace` and `narrativetrace-pytest` are not — adding them is the
agent's job.

It is the `add-narrative-tracing/existing-service` case's fixture: a project WITH tests, so the
install page's first trace is one existing test through the test integration, and the grader asks
for that test's `.md` and `.nt` files under the integration's output directory
(`narrative-traces/`, the plugin's default).
