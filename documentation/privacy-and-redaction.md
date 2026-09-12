# Privacy and redaction

This library runs inside your process and writes files your team will share — CI artifacts,
production log lines. This page is the row-by-row version of that contract: what redacts, where
it does and does not reach, and what NarrativeTrace guarantees versus what it does not claim at
all. Verified directly against `packages/narrativetrace/src/narrativetrace/redaction.py` and
`template.py`, not inferred from other docs.

## Redaction, surface by surface

| Surface | Can disable built-in redaction? |
|---|---|
| pytest plugin output | No |
| ASGI middleware (request/user metadata export) | No |
| OpenTelemetry bridge | No |
| structlog processor / stdlib logging bridge | No |
| A custom `ValueRenderer` your own code constructs | Yes — only by passing `RedactionPolicy.DISABLED` to `trace_object(obj, context, renderer=ValueRenderer(redaction_policy=RedactionPolicy.DISABLED))` explicitly |
| `@not_traced` / `not_traced_field(...)` | Not applicable — it is the thing doing the redacting, and it always wins |

Every shipped integration renders values through the same `ValueRenderer`/`RedactionPolicy`
mechanism `trace_object` uses by default (`RedactionPolicy.DEFAULT`) — none of them expose a
configuration flag, environment variable, or plugin setting that reaches `DISABLED`. The only way
to get there is application code that constructs its own `ValueRenderer` and passes it in — a
deliberate, reviewable act in your own source, not a state a deploy can silently flip.

## What the deny-list catches, and what outranks it

Two independent redaction mechanisms apply to every reflectively-rendered value:

1. **`@not_traced("param")` / `not_traced_field(...)` / `__nt_not_traced__`** — always redacts,
   unconditionally, regardless of policy.
2. **The name-based deny-list** (`RedactionPolicy.DEFAULT`) — a case- and accent-insensitive
   substring match against field/parameter names, **multilingual and always on, with no locale to
   select**: English (`password`, `secret`, `token`, `cvv`, `ssn`, `apikey`, `cardnumber`,
   `sessionid`, `passphrase`, `otp`, `bearer`, and more) sits beside Spanish, Portuguese, French,
   German and Chinese words (`contraseña`, `senha`, `motDePasse`, `passwort`, `密码`, and more) —
   `pan`/`iban` and eight non-English words match on identifier-token boundaries instead of as
   raw substrings, specifically so `companyName` or
   `japaneseAddress` are not swept in — plus a second, independent check on the *shape* of the
   value itself: a JWT, a `Set-Cookie` string, a card-number-shaped digit run, or a national
   identity number (Chilean RUT, Brazilian CPF/CNPJ, Spanish DNI/NIE, French NIR, Chinese resident
   id, US SSN) that passes its own checksum or structural rule — a US SSN carries no check digit,
   so the SSA's own never-issued area/group/serial values do that job instead — so a bearer token
   or an id number passed under an unrecognized name is still caught.

A `NamedTuple` is introspected by field name rather than rendered as an anonymous positional
tuple, so a redacted field inside one stays hidden the same way a dataclass field does — redaction
survives that one container deep. And it wins over a narration template that names it:
`{param.property}` in `@narrated`/`@on_error` resolves a path to a redacted member as
`[REDACTED]`, at every depth along the path, never the literal value.

**A composite's own stringification is never trusted** *(since 0.1.2, unreleased)*. Any object carrying instance
state — a dataclass, an attrs class, a `NamedTuple`, or a plain object with a populated
`__dict__`/`__slots__` — is introspected field-by-field regardless of whether it also defines a
custom `__str__`/`__repr__`; that hand-written method is never consulted for it. Before this fix,
`ValueRenderer` trusted a plain class's own `__str__` outright the moment it overrode the default,
so a hand-written `__str__` that interpolated a sensitive field — directly, or transitively
through a nested object's own `__str__` — reached output completely unmediated, past the
deny-list, depth caps, everything. A dict/map **key** had the identical gap: it used to be a bare,
unmediated `str(key)`, so a sensitive object used as a key leaked unconditionally regardless of
what its value held. Both are now introspected and redaction-checked exactly like an ordinary
value — only a genuine leaf (no instance state at all: a number, a string, a stateless helper
class, a payload-free `Enum` member) still trusts its own `str()`. `@narrative_summary` is
unaffected and remains the supported way to give a composite a curated one-line rendering instead
of the field-by-field default.

When a `@narrative_summary` method, a custom `__str__`, or a field's own getter raises *(since
0.1.2, unreleased)*, that one part renders `<error: <TypeName>>` — the exception's own type name
(`<error: ValueError>`,
`<error: RecursionError>`) substituted for that part only. The exception's *message* is
deliberately never rendered, because a message can carry the very value that failed to render;
only the type name reaches output, never `str(exc)`.

**One documented narrowness, recorded rather than fixed.** Template placeholder resolution
(`{param}`, `{param.property}`) always checks values against `RedactionPolicy.DEFAULT` — the
policy is not threaded through from a custom `ValueRenderer` you pass to `trace_object`. In
practice this only matters if you also build a custom or disabled policy: plain parameter and
return-value rendering honors that custom policy, but a `@narrated`/`@on_error` template resolving
the same value still checks the default deny-list underneath it. `@not_traced` is unaffected — it
always redacts regardless of which policy is in force.

Full detail and worked examples: [Decorators Guide](guides/decorators.md).

## Guarantees

- **Tracing failures are isolated from host execution.** Recording is exception-isolated on every
  path; a throwing `__str__`, a full buffer, or a broken log handler never changes what your
  method returns or throws.
- **Output cannot be forged.** Rendered values, exception messages, and narration text pass
  through control-character and surrogate escaping before they reach a log line, a console
  renderer, or a Markdown document — so a value cannot inject a fake log line or break the
  artifact's formatting.
- **The buffered analysis path may shed events, but it always reports loss.** It is a fixed-size
  ring (65,536 slots by default — `BufferedEventConsumer`'s `buffer_capacity` constructor
  parameter, for code that builds its own pipeline) that overwrites the oldest event under
  sustained load rather than growing without bound or blocking the caller; a run that lost events
  prints the count on its own `Incomplete:` suite-footer line instead of silently under-reporting.
- **Introspection reads stored data, not code.** Field names come from `dataclasses.fields()`,
  attrs metadata, a `NamedTuple`'s `_fields`, or the instance `__dict__` — a computed `@property`
  getter is never enumerated and never runs during introspection.

## Non-guarantees

- **No "zero overhead" claim.** Tracing does work, and work costs something — see the
  [README's Performance section](../README.md#performance).
- **No private-method tracing.** `trace_object` only intercepts public attribute access
  (`__getattr__`); a name starting with `_` is never wrapped, and dunder methods (`__str__`,
  `__eq__`, …) are resolved on the type and never reach the wrapper either — so a wrapped object's
  `str()`/`repr()`/`==`/`isinstance()` silently stop reflecting the original object, with no marker
  or unwrap API to detect the wrap from outside.
- **No automatic tracing of an object you did not explicitly wrap.** There is no import hook, no
  bytecode instrumentation, and no framework-wide auto-wrap shipped today — see
  [Choosing an Integration](choosing-an-integration.md).
- **Redaction is name- and shape-based, not a data-flow analysis.** A sensitive value stored under
  a name the deny-list does not recognize, and that does not match a known secret shape, is not
  redacted unless you mark it explicitly.
- **No redaction of test names.** A test's display name — including a `@pytest.mark.parametrize`
  id (`test_finds_it[KAYAK]`) — is developer-authored/runner-generated identifier text, not a
  captured value: it reaches the `narrativetrace-pytest` artifact's `scenario:`/`**Scenario:**`
  header and its filename verbatim (humanized, never redacted). No deny-list is consulted for it,
  and this is by design (cross-port structural-header contract): this runtime does not ship a
  value-free structural artifact yet — [Feature Guide](feature-guide.md) states it plainly, "the
  pytest plugin writes one full-detail file per test" — so its one per-test artifact is the
  value-carrying kind that keeps the display name everywhere. Keep secrets out of `parametrize`
  ids the same way you would out of a `@narrated`/`@on_error` template.

## The production loss model, visually

The two halves of the dual-path pipeline (product decision record PY-002) carry opposite
obligations by design:

```text
synchronous log path (stdlib logging, inline on the caller thread)
   must not fail the host application
   durable — this is the record

buffered analysis path (bounded ring, drained by a background thread)
   may shed events under load, and always says so
   must never block the caller
   must never grow past its bound (65,536 slots by default)
   best-effort — this is analysis, not audit
```

Losing the buffer loses analysis fidelity — captured trees, clarity scoring, OTel spans — for
events shed during that window. Losing the log stream loses the record. That asymmetry is why they
are two paths with two different failure behaviors, rather than one path with a single trade-off.

## What this page does not cover

What happens when NarrativeTrace stacks with AOP-style proxies, contract libraries, or another
tool wrapping the same objects follows two invariants — one trace frame per business-boundary
crossing, and no outcome that depends on wrapper order — covered in the
[README's Privacy and safety section](../README.md#privacy-and-safety). Every tracing-level
and output-format knob, including how `NARRATIVETRACE_LEVEL` gates capture before any rendering
happens, is the [Configuration Guide](guides/configuration.md).
