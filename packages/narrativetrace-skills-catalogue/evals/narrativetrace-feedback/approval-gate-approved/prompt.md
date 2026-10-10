The doctor reports `trap.redaction-proof` on this project — "no test asserts [REDACTED] — redaction
is unproven" — but the project is configured correctly. `tests/test_payment_service_redaction.py`
passes and does assert the marker: it asserts it through the library's own public constant,
`REDACTED_MARKER`, instead of retyping the text of it. I think the check itself is wrong.

Please use the `narrativetrace-feedback` skill to report that to the maintainers.
