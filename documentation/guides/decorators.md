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

Redact a parameter by name, or a field via class attribute / dataclass metadata:

```python
from dataclasses import dataclass, field
from narrativetrace import not_traced, not_traced_field

class AuthService:
    @not_traced("password")
    def login(self, username: str, password: str) -> Session:
        ...

@dataclass
class Credentials:
    username: str
    secret: str = not_traced_field(default="")   # or: __nt_not_traced__ = ("secret",)
```

Redacted values are replaced with a marker before rendering — they never reach a renderer,
exporter, or log.

## The purity contract — side effects during tracing

NarrativeTrace may invoke a small, fixed set of code paths on your objects while rendering
a trace. Keep those members **pure** — free of side effects such as lazy loading, access
counters, cache population, or I/O — exactly as you would for a debugger or a serializer.

What is invoked, and what is not:

- **Introspection enumerates stored data, not code.** Field names come from
  `dataclasses.fields()`, attrs metadata, a `NamedTuple`'s `_fields`, or the instance
  `__dict__` — so a computed `@property` (whose getter might count accesses or lazily load)
  is never enumerated and never runs during introspection. A `NamedTuple` is introspected by
  field name rather than rendered as an anonymous list of positional values, so a redacted
  field stays hidden the same way a dataclass field does.
- **What NarrativeTrace does invoke:** a custom `__str__`, a `@narrative_summary` method,
  and any property path you name in a `@narrated`/`@on_error` template — `{order.total}`
  resolves via `getattr`, so a `@property` named there *will* run its getter.
- **Invocation is bounded and isolated.** Output is capped (string length, collection
  items, depth); a raising `__str__` or getter can never fail the traced business call
  (templates fall back to the literal `{placeholder}`); values are rendered eagerly at the
  call site, so any side effect happens once, at a deterministic point. Futures and
  awaitables are never forced.

If a member cannot be pure, mark it `@not_traced` / `not_traced_field(...)` — a redacted
member's value is never read at all — or give the type a curated `__str__` /
`@narrative_summary` so you control exactly what is accessed. At `NARRATIVETRACE_LEVEL=OFF`
(and for parameter values at `SUMMARY`), no argument rendering happens at all.
