# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Runs one passing test through the real, installed `narrativetrace-pytest` plugin -- the only
way to observe an extension-gated default (approval mode, output-on-by-default, manifest.json)
without a project's own `pytest.ini`/`pyproject.toml` in the way. Mirrors Java's
`JUnitLauncherSupport` + `TracedCallFixture`: a fixture test file is written to a throwaway
directory and run through `pytest.main()` in-process, against whichever `narrativetrace`/
`narrativetrace-pytest` versions `uv run --with ...` put on this interpreter's path -- never a
second copy of the plugin's own logic.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

_ENV_PREFIX = "NARRATIVETRACE_"

_FIXTURE_SOURCE = """\
from narrativetrace import trace_object


class _Greeter:
    def greet(self, name):
        return f"hello {name}"


def test_traced_call(narrative_trace):
    service = trace_object(_Greeter(), narrative_trace)
    service.greet("world")
"""


@contextmanager
def _clean_environment(overrides: dict[str, str]) -> Iterator[None]:
    """Clears every ambient `NARRATIVETRACE_*` variable first, then applies `overrides` -- the
    same "clear, then set only what this probe wants to observe" discipline Java's probes use
    (`System.clearProperty` before each `JUnitLauncherSupport.run`), so a variable left over from
    the invoking shell can never quietly change what a probe observes."""
    previous = dict(os.environ)
    for key in list(os.environ):
        if key.startswith(_ENV_PREFIX):
            del os.environ[key]
    os.environ.update(overrides)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def run_traced_fixture(env: dict[str, str]) -> Path:
    """Runs one passing test (using the `narrative_trace` fixture) through the real, published
    `narrativetrace-pytest` plugin -- auto-registered via its own entry point, exactly as an
    adopter's install would be, never referenced by import path here -- with `env` layered over a
    clean `NARRATIVETRACE_*` environment for the duration of the run. Returns the working
    directory the run happened in, so a caller can inspect whatever it wrote relative to it (the
    default `NARRATIVETRACE_OUTPUT_DIR` is `narrative-traces` under the current directory).

    The fixture module's basename is unique per call (a random suffix): `contract_probe.runner`
    calls this function more than once within one interpreter process, and pytest's rootdir-less
    import mode keys a collected module by basename in `sys.modules` -- a second run reusing
    `test_contract_probe.py` from a different temp directory would collide with the first run's
    already-imported module of that name ("import file mismatch") rather than collecting the new
    file, silently reusing stale test code instead of failing loud.
    """
    work_dir = Path(tempfile.mkdtemp(prefix="contract-probe-pytest-"))
    test_file = work_dir / f"test_contract_probe_{uuid.uuid4().hex}.py"
    test_file.write_text(_FIXTURE_SOURCE, encoding="utf-8")
    previous_cwd = Path.cwd()
    os.chdir(work_dir)
    try:
        with _clean_environment(env):
            pytest.main([str(test_file), "-q", "-p", "no:cacheprovider"])
    finally:
        os.chdir(previous_cwd)
    return work_dir
