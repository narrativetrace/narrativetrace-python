# Security Policy

## Reporting a Vulnerability

Please do not open a public issue for a suspected vulnerability.

- **Preferred:** use GitHub's private vulnerability reporting — "Report a
  vulnerability" under this repository's **Security** tab.
- **Fallback:** email hello@narrativetrace.ai.

## Response Expectations

We aim to acknowledge new reports within 7 days. We practice coordinated
disclosure: please give us reasonable time to investigate and ship a fix
before any public disclosure.

## Supported Versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Scope

NarrativeTrace processes application data — method arguments, return
values, and other runtime state — into trace artifacts for humans and
language models to read. Redaction, injection-hardening, and the parsers
that walk that data are in scope and are actively tested; see
[`documentation/security-testing.md`](documentation/security-testing.md).
