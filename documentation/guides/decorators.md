# Decorators

Wrapping an object with `trace_object` traces every public method. Decorators refine what is
captured and how it reads.

## `@narrated` — prose narration

```python
from narrativetrace import narrated

class InventoryService:
    @narrated("reserves {quantity} of {product_id}")
    def reserve(self, product_id: str, quantity: int) -> Reservation:
        ...
```

Template tokens `{name}` and one dotted level `{customer.address}` resolve against parameter
values; a deeper path such as `{customer.address.city}` can never resolve and survives literally
at runtime, so a placeholder naming it still emits an unresolved-token suite warning.

**Redaction wins over a template that names it.** A path reaching a redacted member — at any depth
of the path, not just its last segment — resolves to `[REDACTED]` instead of the value or the
literal placeholder. A bare `{name}` naming a value directly obeys the same two rules: the
deny-list reads that key exactly as it reads a field name, and the value's own shape is checked
too, so `@narrated("login {password}")` and a JWT arriving as `{value}` both render `[REDACTED]`.
Naming a path, or a value, never weakens the rules that apply to the value directly: if you
need the value in a narrative, remove `@not_traced` from the member; that removal is the
deliberate, reviewable decision, and it shows up in the diff.

## `@on_error` — failure context

Stackable; attaches a resolved message to a failing exit for the matching exception type:

```python
from narrativetrace import on_error

class PaymentService:
    @on_error(TimeoutError, "gateway timed out charging {customer_id}")
    def charge(self, customer_id: str, amount: int) -> Payment:
        ...
```

## `@not_traced` — redaction

Redact a parameter by name:

```python
from narrativetrace import not_traced

class AuthService:
    @not_traced("password")
    def login(self, username: str, password: str) -> Session:
        ...
```

Redact a **field** on an object passed as an argument, one of two ways:

- **`not_traced_field(...)`** — a dataclass field, marked through its own `field()` metadata.
- **`__nt_not_traced__`** — a class attribute naming the fields to redact, for any other kind of
  object: a plain class, a `NamedTuple`, or an attrs class, wherever `field(metadata=...)` is not
  available. It is a tuple/list/set of field-name strings read off the **class** (`is_field_not_traced`
  checks it before dataclass metadata), so subclasses inherit it and instances cannot override it.

Both redact identically — field-by-field, not the whole containing object — and win
unconditionally over any policy:

<!-- snippet: examples/not_traced_fields.py region=main -->
```python
from dataclasses import dataclass

from narrativetrace import (
    ContextVarNarrativeContext,
    IndentedTextRenderer,
    not_traced_field,
    trace_object,
)


@dataclass
class Credentials:
    username: str
    secret: str = not_traced_field(default="")


class LegacyCredentials:
    """A plain (non-dataclass) class: `__nt_not_traced__` names the fields to redact."""

    __nt_not_traced__ = ("secret",)

    def __init__(self, username: str, secret: str) -> None:
        self.username = username
        self.secret = secret


class AuthService:
    # Parameter named `account`, not `credentials` -- the latter is itself on the name-based
    # deny-list (see documentation/privacy-and-redaction.md) and would redact the whole argument
    # regardless of which fields inside it are marked `@not_traced`.
    def login(self, account: Credentials | LegacyCredentials) -> str:
        return f"session-for-{account.username}"


def run() -> str:
    """Traces two logins, one per redaction surface, and renders the result."""
    context = ContextVarNarrativeContext()
    service = trace_object(AuthService(), context)
    service.login(Credentials("alice", "hunter2"))
    service.login(LegacyCredentials("bob", "hunter2"))
    return IndentedTextRenderer().render(context.capture_trace())


```
<!-- /snippet -->

`python -m examples.not_traced_fields` prints (`0ms` varies by machine, like the 60-second page):

<!-- snippet: examples/build/not_traced_fields.txt mask=duration -->
```text
AuthService.login(account: Credentials(username="alice", secret=[REDACTED])) → "session-for-alice" — 0ms
AuthService.login(account: LegacyCredentials(username="bob", secret=[REDACTED])) → "session-for-bob" — 0ms
```
<!-- /snippet -->

Redacted values are replaced with a marker before rendering — they never reach a renderer,
exporter, or log.

## The purity contract — side effects during tracing

NarrativeTrace may invoke a small, fixed set of code paths on your objects while rendering
a trace. Keep those members **pure** — free of side effects such as lazy loading, access
counters, cache population, or I/O — exactly as you would for a debugger or a serializer.

What is invoked, and what is not:

- **Introspection enumerates stored data, not code.** Field names come from
  `dataclasses.fields()`, attrs metadata, a `NamedTuple`'s `_fields`, or the instance
  `__dict__`/`__slots__` — so a computed `@property` (whose getter might count accesses or
  lazily load) is never enumerated and never runs during introspection. A `NamedTuple` is
  introspected by field name rather than rendered as an anonymous list of positional values,
  so a redacted field stays hidden the same way a dataclass field does.
- **A custom `__str__` is trusted only for a genuine leaf** *(since 0.1.2, unreleased)*. Any object
  carrying instance state — a dataclass, an attrs class, a `NamedTuple`, or a plain object
  with a populated `__dict__`/`__slots__` — is introspected field-by-field regardless of
  whether it also defines `__str__`/`__repr__`; that hand-written method is never consulted,
  the same way one on a dataclass never was. Only a value with no instance state at all (a
  number, a string, a stateless helper class, a payload-free `Enum` member) still renders
  through its own `str()`. Before this fix, a plain class's custom `__str__` took precedence
  over introspection outright, so a hand-written `__str__` that interpolated a sensitive
  field — directly, or transitively through a nested object's own `__str__` — bypassed
  redaction entirely; a dict/map KEY had the identical gap (a bare, unmediated `str(key)`),
  now closed the same way: a key is introspected and redaction-checked exactly like a value.
  Give a composite a `@narrative_summary` method when you want a curated one-line rendering
  instead of the field-by-field default — that mechanism is unaffected and still the
  supported way to control exactly what is shown.
- **A raising summary, `__str__`, or getter renders a typed error marker, never its own
  message** *(since 0.1.2, unreleased)*. `<error: ValueError>`, `<error: RecursionError>` and so on — the failing part's
  own exception TYPE name, substituted for that one part only (never the whole trace, never a
  bare `<error>`). The exception's *message* is deliberately never rendered: a message can
  carry the very value that failed to render (`"summary failed for {token}"` would otherwise
  leak `token`), so only the type name — never `str(exc)` — reaches output.
- **Invocation is bounded and isolated.** Output is capped (string length, collection
  items, depth); a raising `__str__`, summary, or getter can never fail the traced business
  call (templates fall back to the literal `{placeholder}`); values are rendered eagerly at
  the call site, so any side effect happens once, at a deterministic point. Futures and
  awaitables are never forced.

If a member cannot be pure, mark it `@not_traced` / `not_traced_field(...)` — a redacted
member's value is never read at all — or give the type a `@narrative_summary` so you control
exactly what is accessed (a curated `__str__` no longer opts a composite out of introspection,
see above). At `NARRATIVETRACE_LEVEL=OFF` (and for parameter values at `SUMMARY`), no argument
rendering happens at all.
