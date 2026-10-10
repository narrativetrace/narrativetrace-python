# Fixture: feedback-value-free

`feedback-false-positive`'s sources, byte for byte, plus one rendered trace somebody saved by hand
into `traces/` while working out the doctor's finding. It is a real rendering of this project's own
`PaymentService.charge` with both services traced: `auth_token` is `[REDACTED]` on the outer call,
and the same token reaches `GatewayClient.authorize` under the parameter name `gateway_ref`, which
the deny-list does not cover — so it renders in clear there. That value, `ghp_NTCANARY0001`, is the
canary the `value-free` case grades: it must reach no report, no URL and no command that files.

The file carries the renderer's own bytes (`MarkdownRenderer.render_document`), pinned by
`tests/test_feedback_eval_fixtures.py`: a hand-written stand-in for a generated artifact dodges
exactly the defect it exists to expose. Saved under `traces/`, not `build/`, because the runner
does not scaffold a fixture's `build/`.
