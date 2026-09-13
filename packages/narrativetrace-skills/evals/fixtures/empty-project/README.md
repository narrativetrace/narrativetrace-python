# Fixture: empty-project

The `add-narrative-tracing` happy-path case's fixture: a directory with nothing in it but this
README (no `pyproject.toml`, no NarrativeTrace package) — the "before you start" state the
Sixty Seconds page and `llms.txt`'s "Install and first trace" both assume, so the case actually
exercises the install step (`uv add narrativetrace`, which also creates the missing
`pyproject.toml`) rather than starting from an already-set-up project.
