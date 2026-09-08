# The hostile corpus

Seven JSON fixtures describing input that a NarrativeTrace runtime does not
control: values a traced method returned, headers a stranger sent, templates an
author wrote, object graphs a third-party DTO produced, instruction-shaped text
aimed at whatever reads the narrative afterwards, the names the artifacts are
written under, and the sensitive-field vocabulary the redaction default is
measured against.

**This directory is the cross-runtime corpus.** Every NarrativeTrace runtime
copies these files verbatim — the way the conformance schemas are copied — so
the same case hits all five renderers. A newly-understood attack shape is added
*here*, once, and every runtime gains it on the next sync. Nothing in these
files is Java-specific: they are data, and the builder that turns a declarative
graph shape into a live object graph is the only per-runtime code.

Adding a case: append an object to the relevant array, give it a stable
kebab-case `id` and a `description` that says *what breaks* rather than what the
bytes are, and keep the file ASCII — every non-ASCII character is written as a
`\uXXXX` escape so the fixture reads the same in every editor and diff.

## The files

| File | Feeds | What it holds |
|---|---|---|
| `strings.json` | the value renderer, every output format | hostile scalar values: control characters, bidi and zero-width, combining sequences, unpaired surrogates, template lookalikes, JSON/Mermaid/Markdown/YAML metacharacters, values up to 1 MiB |
| `headers.json` | `Traceparent` and any other wire reader | W3C `traceparent` and `tracestate` values: wrong lengths, non-hex, all-zero ids, version `ff`, trailing garbage, embedded CRLF, oversize |
| `templates.json` | `TemplateParser` and `RedactedPaths` | `@Narrated`/`@OnError` templates: nesting, unterminated braces, paths into redacted members at every depth, 50-segment paths, unicode identifiers |
| `graphs.json` | the value renderer | declarative object-graph *shapes*: depth, width, cycles, self-reference, `Optional`-in-`Map`-in-record chains, throwing/blocking/recursive `toString`, `hashCode` that throws, huge collections, standalone `Map.Entry`, `AtomicReferenceArray` |
| `injection.json` | every output format, as an AI-consumer oracle | prompt-injection payloads arriving as captured values: override phrasings, role and turn markers, tool-call lookalikes, markdown-link exfiltration, fence and frontmatter terminators, Mermaid label terminators, homoglyph and zero-width variants |
| `names.json` | the artifact writers, which turn a name into a path | test class and method names: separators and parent traversal, control characters, lone surrogates, noncharacters, bidi overrides, and names past the filesystem's per-element limit in characters *and* in bytes |
| `redaction.json` | the name deny-list and the value-shape matcher | sensitive field names in English, Spanish, Portuguese, French and Chinese; national-id value shapes with their check digits; and — carrying equal weight — the near-miss names and checksum-failing lookalikes that must stay **visible** |
| `trace-shapes.json` | every recursive renderer/exporter, via `ai.narrativetrace.core.tree.TreeWalk` | declarative `TraceNode` call-tree *shapes*: a legitimate deep chain, and a hand-built cyclic child list (`TraceNode.children` is undefended) — the tree-structure counterpart to `graphs.json`'s value-graph shapes |

## Case shapes

Every case is an object with `id` and `description`. The remaining keys say how
to build the input.

**Literal value** — `value` holds it directly:

```json
{ "id": "lone-cr", "description": "a line break to YAML but not to a Java line reader", "value": "\r" }
```

**Generated value** — `repeat` builds a large one without a large fixture;
optional `prefix` and `suffix` bracket it. `prefix + unit x count + suffix`:

```json
{ "id": "long-1mib", "description": "one mebibyte in one value", "repeat": { "unit": "x", "count": 1048576 } }
```

**Redaction case** (`redaction.json`) — either a `name` with the `canary`
planted behind it, or a `value` that is its own canary because the shape *is*
the secret. `expect` says which way the assertion runs:

```json
{ "id": "es-clave", "description": "a short word that must match as a token", "name": "claveAcceso", "canary": "canary-es-clave", "expect": "redacted" }
{ "id": "fp-circuit", "description": "cuit inside circuit", "name": "circuitBreaker", "canary": "canary-fp-circuit", "expect": "visible" }
{ "id": "shape-cpf-bare", "description": "a Brazilian CPF as eleven bare digits", "value": "52998224725", "expect": "redacted" }
```

Canaries are unique per row rather than a single shared string, so one row's
passing output cannot clear another's. The `visible` rows are not decoration:
a deny-list is only as good as the field it does *not* blank, and a default
that hides `circuitBreaker` is one teams switch off entirely — which leaks
every field rather than one.

**Declarative graph** (`graphs.json`) — either `layers`, a stack of wrappers
built outward around `payload` (index 0 is innermost, so
`["optional","map","record"]` is a record holding a map holding an `Optional`),
or `kind`, naming a shape a stack cannot express:

| `kind` | Built as |
|---|---|
| `repeatLayer` | `n` copies of `layer` stacked around `payload` |
| `width` | one `container` holding `n` elements, `payload` last |
| `cycle` | a ring of `n` holders; `n: 1` is a self-holding object |
| `selfInCollection` | a `container` that contains itself |
| `diamond` | one object reached twice by different paths — shared, not cyclic |
| `hostileMember` | an object whose `member` (`toString`, `hashCode`, `equals`, a getter, a record accessor, a field *name*) misbehaves |
| `manyFields` | an object with `n` fields |
| `emptyContainers` | every empty container, nested |
| `future` | a `Future` in the given `state` |
| `throwable` | an exception carrying `payload`, optionally with an `n`-deep cause chain |

`payload: "secret-record"` means the builder plants a record with a
`@NotTraced` component holding a **unique per-case sentinel token** at that
position. The redaction oracle then asserts the token appears in no byte of any
output, at any depth, in any format.

**Declarative trace shape** (`trace-shapes.json`) — `kind` names the call-tree
shape, `n` its size:

| `kind` | Built as |
|---|---|
| `chain` | a linear chain `n` nodes deep, one child each |
| `cycle` | a ring of `n` nodes, each holding the next; `n: 1` is a node that holds itself |

Kept well under `Oracles.MAX_OUTPUT_BYTES`: several renderers indent
proportionally to depth, so a chain anywhere near `TreeWalk.MAX_DEPTH` would
make output size, not the depth/cycle bound, the thing under test.
`TreeWalkTest` exercises `MAX_DEPTH` itself directly against the walker.

## The oracles these feed

Named here so every runtime implements the same ones. They are documented for readers
in `documentation/security-testing.md`.

1. **No uncaught exception** — a hostile input degrades, it does not propagate.
2. **Bounded time and size** — narration costs O(size); no input hangs, and no
   input produces unbounded output.
3. **Well-formedness** — JSON parses back and validates against
   `chapter-tree.schema.json`; Mermaid keeps balanced blocks and one line per
   statement; Markdown frontmatter parses as YAML.
4. **Redaction** — a sentinel behind `@NotTraced` reaches no output, at any
   depth, including through wrappers, `Map.Entry`, exception messages and any
   `toString` fallback path. `redaction.json` extends the same oracle to the
   *default* deny-list: every row's canary is absent from every output, or
   present in the value renderer's, exactly as the row declares. Absence is
   asserted in every emitter; presence only in the value renderers, because
   downstream emitters legitimately escape what they are handed and no escaping
   can make a hidden value reappear.
5. **Idempotence** — rendering the same input twice produces the same bytes.
6. **No thread or hook left behind** — no `narrative-trace-*` thread survives.
7. **AI-consumer containment** — an injection payload comes back as exactly one
   value when the output is parsed or lexed again; it never terminates the
   enclosing JSON string, Mermaid label, Markdown fence or frontmatter block.
8. **A name is a path** — every element a writer builds fits the filesystem's
   per-element limit *in bytes*, no name places an artifact outside the output
   directory, and two different names never resolve to one artifact.
