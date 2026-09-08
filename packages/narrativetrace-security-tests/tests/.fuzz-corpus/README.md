# Tier B fuzz corpus

Hypothesis's `DirectoryBasedExampleDatabase` for this package's `@fuzz_settings`-decorated
targets (`test_traceparent_properties.py`, `test_value_renderer_redaction_properties.py`,
`test_template_redaction_properties.py`), configured in `../fuzz_config.py`. Committed, not
gitignored: a crashing example `poe fuzz` finds once is saved here and replayed first on every
subsequent `poe test`/`poe check`, so it becomes a permanent regression the whole team inherits
rather than living only on the machine that found it — the role Jazzer's committed seed corpus
plays for the shared master copy's `@FuzzTest` targets.

Empty as of this commit: `poe fuzz`'s first 5,000-example-per-property run found no crash to seed
it with. This is expected, not a placeholder for something unimplemented — every target it covers
was already hardened by Tier A's structured corpus replay before Tier B ran at all.
