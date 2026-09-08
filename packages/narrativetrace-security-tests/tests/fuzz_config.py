# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier B fallback: shared Hypothesis settings for this package's fuzz targets.

Mirrors Java's target-priority table (``documentation/security-testing.md``): target 1 is
``Traceparent``/any wire reader, target 2 is ``ValueRenderer`` over hostile object graphs, target 4
is template parsing and rendering. Java fuzzes these with Jazzer, whose ``@FuzzTest`` steers
generation by the target's own coverage; the
Python equivalent, atheris, has no wheel for this container's platform (aarch64 Linux) and building
it from source needs a Clang+libFuzzer toolchain this container does not have (``uv pip install
atheris`` fails with "Failed to find libFuzzer"; no ``clang`` binary anywhere on ``$PATH``). Noted
in the private backlog; see ``documentation/security-testing.md`` for the full evidence.

Hypothesis's own example database is the fallback: :data:`fuzz_settings` points it at a directory
committed to the repository (not gitignored) rather than the usual ``.hypothesis/`` cache, so every
failing example ``poe fuzz`` finds is replayed first on every subsequent run -- a crash found once
becomes a permanent regression the whole team inherits, the role Jazzer's committed seed corpus
plays for Java.

Applied as a decorator directly on each target's generated-example test methods, never as a
globally loaded profile: ``settings.load_profile`` sets the *process-wide* active default, and this
package's tests run inside the same ``poe check``/``poe test`` session as every other package's --
loading a profile here would silently change Hypothesis's behaviour (deadline, health checks) for
every other package's property tests too.
"""

from __future__ import annotations

import os
from pathlib import Path

from hypothesis import settings
from hypothesis.database import DirectoryBasedExampleDatabase

_CORPUS_DIR = Path(__file__).parent / ".fuzz-corpus"

_DEFAULT_EXAMPLES = 100
"""Hypothesis's own built-in default, kept explicit so the fuzz multiplier below is legible."""

_FUZZ_EXAMPLES = 5_000
"""``poe fuzz``'s per-target budget -- large enough to be worth a dedicated task, small enough to
finish in well under Java's ``FuzzBudget.PER_TARGET`` (5 minutes) on ordinary hardware."""

_examples = _FUZZ_EXAMPLES if "NARRATIVETRACE_FUZZ" in os.environ else _DEFAULT_EXAMPLES

fuzz_settings = settings(
    max_examples=_examples,
    deadline=None,
    database=DirectoryBasedExampleDatabase(_CORPUS_DIR),
)
"""Decorate a ``@given``-decorated test with this (``@fuzz_settings`` above ``@given``) to opt it
into the persistent corpus and the budgeted example count."""
