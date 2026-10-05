# Fixture: redaction-gap

A deliberately incomplete project: `trace_object` wraps a call carrying a deny-listed parameter
name (`payment_token`) and there is no test asserting `[REDACTED]` anywhere. `narrativetrace
doctor` must report `trap.redaction-proof` failing; the deviation case
(`../../narrativetrace-doctor/deviation-redaction-gap/`) checks that the skill correctly surfaces
this and tells the agent what to do about it, rather than assuming redaction "just works" because
the parameter name is suggestive.

Not a uv workspace member (outside `packages/*`) — the eval runner scaffolds it into a scratch
directory and installs the published `narrativetrace` package fresh, the same way a real consumer
would.
