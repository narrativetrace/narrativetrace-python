# narrativetrace-clarity

Naming-clarity analysis and CI gate for [narrativetrace](../narrativetrace).

The clarity engine, with dictionaries byte-identical across runtimes: 828 domain verbs (1053 total across
34 categories), 187 abbreviations, 35 collocation maps, and role-suffix dictionaries feed five
weighted scorers (method 0.30, class 0.20, parameter 0.25, structural 0.15, cohesion 0.10).

* `analyze(tree)` — score any core `TraceTree`.
* `narrativetrace-clarity <paths…>` — scan Python sources, write `clarity-report.md` /
  `clarity-results.json`, and gate the build with `--min-score` / `--max-high-issues`.
