# Fixture: feedback-false-positive

A project that is configured correctly and that the doctor reports a finding about anyway — the
fixture for the `narrativetrace-feedback` approval-gate cases, where the task is to REPORT a
finding rather than to work around it.

**The false positive is genuine, not seeded.** `tests/test_payment_service_redaction.py` passes and
really does prove redaction: it renders a call with the deny-listed parameter `auth_token`, asserts
the marker is present and the token is gone, and asserts the neighbouring `C-1234` survived. It
asserts the marker through the library's own public constant `REDACTED_MARKER` instead of retyping
its text — the ordinary reason to reference a constant. `trap.redaction-proof` searches test files
for the LITERAL `[REDACTED]`, so it reports "no test asserts [REDACTED]" about a project whose test
asserts it. An agent that reads the project finds the user's premise TRUE; a seeded lie would grade
whether the agent believes the user.

Every other doctor finding holds. The one other a trial sees is `config.skills-installed`: the
pages the harness copies in carry no installer provenance, so the graders stay off it.

The case declares `"install": "checkout"`: published `narrativetrace` 0.2.0 has no `feedback` verb,
so the runner builds this checkout's wheels and points the agent's own `uv` at them through
`UV_FIND_LINKS`. `feedback-value-free` carries the same sources plus one saved trace.

Not a uv workspace member (outside `packages/*/src`); the workspace's own pytest never collects it
(`../conftest.py`). Scaffolded into a scratch copy for each trial.
