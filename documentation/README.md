# NarrativeTrace documentation

[English](README.md) | [Español](LEAME.md) | [Português](LEIAME.md) | [简体中文](自述文件.md)

The index of every document in this repository, in English. Each language above gets a
link once its own sibling index exists (`LEAME.md`, `LEIAME.md`, `自述文件.md`) — see
[`i18n/manifest.json`](i18n/manifest.json) for the declared language set and translation
status. Engineering-only documents (ADR logs, security/concurrency testing notes, dated
design notes) are English-only by convention and stay off every language's translated set.

## Start here

| Document | What it covers |
|---|---|
| [First 10 Minutes](first-10-minutes.md) | One tiny service, real output, from install to a redacted value |
| [Choosing an Integration](choosing-an-integration.md) | Which package you need, as a decision diagram |
| [Installation Guide](guides/installation.md) | Every package, what it adds |
| [Configuration Guide](guides/configuration.md) | Tracing levels, output settings, precedence chain |
| [Decorators Guide](guides/decorators.md) | `@narrated`, `@on_error`, `@not_traced`, the purity contract |
| [Privacy and Redaction](privacy-and-redaction.md) | The row-by-row redaction contract, verified against the code |
| [What to Commit](what-to-commit.md) | Which generated files are CI artifacts, and which (if any) are reviewed baselines |
| [Troubleshooting](troubleshooting.md) | Symptom → cause → fix for the failure modes people actually hit |

## Integrations

| Document | What it covers |
|---|---|
| [pytest Guide](guides/pytest.md) | The `narrative_trace` fixture, per-test artifacts, the clarity footer |
| [FastAPI / ASGI Guide](guides/fastapi-asgi.md) | Starlette/FastAPI middleware, W3C traceparent, the request accessor |
| [OpenTelemetry Guide](guides/opentelemetry.md) | The OTel span bridge: live listener and batch exporter |
| [Logging Guide](guides/logging.md) | The stdlib logging bridge and the structlog processor |

## Analysis and output

| Document | What it covers |
|---|---|
| [Clarity Guide](guides/clarity.md) | The scoring model, JUnit-equivalent integration, and the `clarityCheck`-style gate |
| [Feature Guide](feature-guide.md) | The canonical catalog: every feature, its tier, its status |

## Design and rationale

Engineering-only — the *why* behind load-bearing decisions. English-only by convention
(see the i18n terminology conventions' "What is never translated").

| Document | What it covers |
|---|---|
| [Security Testing](security-testing.md) | The hostile-corpus fuzz suite: targets, oracles, how a crash becomes a regression test |
| [Security Tooling](security-tooling.md) | Secrets scanning, SAST, dependency-vulnerability scanning: what runs when |
| [Concurrency Stress Testing](concurrency-stress.md) | The stress suite over the dual-path pipeline: invariants, how to run it |

## For AI agents and tools

- [`llms.txt`](llms.txt) — machine-readable index following the
  [llmstxt.org](https://llmstxt.org) convention.
- [`llms-full.md`](llms-full.md) — the complete reference in one file.
- [`i18n/manifest.json`](i18n/manifest.json) — the machine-readable declaration behind the
  language menu above: every translated language, where its directory/index/root file
  live, its completion status, and the set of user documents in scope for translation.
  `poe translation-check` (wired into `poe check`) reads it to enforce completeness,
  structural parity with the English source, and index/menu integrity; `poe
  translation-status` reads it to print the full coverage and review-status dashboard.

## Keeping this index honest

Adding or removing a document under `documentation/` means updating this file in the same
change. A document that is not listed here is invisible to anyone browsing the repository.
