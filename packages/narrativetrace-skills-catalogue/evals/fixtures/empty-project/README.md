# Fixture: empty-project

The `add-narrative-tracing` case fixtures' starting point: a bare `pyproject.toml` (a name, a
version, no dependency, no lockfile, no NarrativeTrace package) and this README — the "before you
start" state the Sixty Seconds page and `llms.txt`'s "Install and first trace" both assume, so the
install step (`uv add narrativetrace`, which needs a `pyproject.toml` to add to — `uv add` does not
create one, `uv init --bare` does) is what puts the package in, rather than an already-set-up
project. The skill's Tier A2 replay runs from a copy of this directory
(`tests/test_replay_cold_install.py`).
