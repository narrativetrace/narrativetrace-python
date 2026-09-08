# narrativetrace-glossary

The domain glossary of a repository: one checked-in `glossary.json` that is simultaneously the
translation dictionary, the reviewable domain documentation, and the vocabulary norm that clarity
diagnostics enforce (ADR-012).

The Java module `narrativetrace-glossary`. Platform mapping: Java *packages* become **dotted
module-path prefixes**, so a bounded context owns `acme.billing`, not `com.acme.billing`.

```python
from narrativetrace_glossary import read_glossary_json, write_glossary_json

glossary = read_glossary_json(Path("glossary.json").read_text(encoding="utf-8"))
Path("glossary.json").write_text(write_glossary_json(glossary), encoding="utf-8")
```

Identifiers become glossary phrases through the normalizer, and the module path of the traced code
picks the bounded context that owns them:

```python
from narrativetrace_glossary import method_candidates, normalize_phrase, resolve_context

normalize_phrase("open_account_with_overdraft")   # "open account with overdraft"
method_candidates("openAccountWithOverdraft")     # verb phrase + "account with overdraft"
resolve_context(glossary, "acme.billing.overdraft_service")   # "billing"
```

Every spelling of one concept converges to a single phrase, so matching against terms and aliases
always happens on the normalized form. Context prefixes match on dot boundaries — `acme.billing`
owns `acme.billing.overdraft` but never the sibling `acme.billingx` — the longest match wins, and
an unmatched path falls back to `_unassigned`, so harvesting works with zero configuration.

The normalizer rejects anything that is not a single code identifier (blank, underscore-only, or
whitespace-carrying input raises `ValueError`): a normalized phrase is term identity, so a
non-canonical one would corrupt a glossary key.

The writer is deterministic by construction — contexts sorted by name, terms in `(context, term)`
order, fixed key order, 2-space indent, trailing newline — so a run that observes no new vocabulary
leaves the committed file byte-identical.

## Harvesting a run into the glossary

`harvest_traces` observes captured trace trees; `merge_harvest` folds those observations into the
committed glossary. Trace nodes carry a *simple* class name, so the caller supplies `module_of` to
say which module declares it — production code passes `type(target).__module__`, tests pass a dict
lookup. A name it cannot answer for resolves to `_unassigned`.

```python
from narrativetrace_glossary import harvest_traces, merge_harvest, write_glossary_json

observed = harvest_traces(trees, glossary=glossary, module_of=modules.get)
result = merge_harvest(glossary, observed)

Path("glossary.json").write_text(write_glossary_json(result.glossary), encoding="utf-8")
```

Harvest sources are method names (the verb phrase plus the object noun phrase), parameter names,
class names with a role suffix stripped, and the type name of whatever a node threw. Names that are
no identifier — synthetic nodes like `<launcher>` or `fire-and-forget` — are skipped silently;
harvesting is best-effort by design. Narration templates are *never* harvested from a live trace:
they hold interpolated runtime values there.

The merge is **additive-only** and **idempotent**, both property-tested. It never removes or
rewrites an entry, so human-authored definitions, translations and a `curated` status are safe; a
phrase that matches a term's deprecated synonym in its own context is suppressed rather than
re-added, and comes back in `result.suppressed_alias_uses` for violation reporting. New terms are
`harvested`, record at most three distinct sites, and are dated by an injectable `clock` that
defaults to today in UTC — so the same run merged twice leaves the file byte-identical.
