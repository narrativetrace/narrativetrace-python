Set up NarrativeTrace in this project and show me its first trace.
1. Read https://narrativetrace.ai/python/llms.txt first. It carries the install block and the
known traps. Do not guess versions or artifact names.
2. If this directory has no project yet, create the smallest console app that
llms.txt's "Install and first trace" block describes. Otherwise work inside the existing
project and trace one real service boundary.
3. Add the `narrativetrace` package the way llms.txt shows, then run `uv run narrativetrace
init --dry-run` and show me the diff. It installs the NarrativeTrace agent skills into this
project and adds a marked section to AGENTS.md. Run it for real only after I have seen the
diff.
4. If the `add-narrative-tracing` skill is now available, follow it. Otherwise follow the
"Install and first trace (copy this)" block in llms.txt.
5. Add one test that traces a call with a deny-listed parameter and asserts the trace
shows `[REDACTED]` for it.
6. Run the program, then run the doctor (`uv run narrativetrace doctor`). Paste
the trace and the doctor report, explain the trace in two sentences, and list exactly what
changed in the project.
Rules: never disable redaction; do not commit `.received.nt` files; apply
`@not_traced` to the real parameter, because importing it protects nothing; run everything in
the foreground and read the output before you report; if you cannot fetch URLs, say so and I
will paste llms.txt.