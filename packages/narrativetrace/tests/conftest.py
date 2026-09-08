# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared pytest/hypothesis configuration for the narrativetrace test suite."""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

# Coverage instrumentation slows example execution well past hypothesis's default 200ms
# per-example deadline; these are correctness ("no crash"/invariant) properties, not latency
# budgets, so the deadline is disabled to avoid spurious flakes under `poe coverage`.
_SUPPRESSED = [HealthCheck.too_slow]

# mutmut drives `pytest.main()` twice inside one process — a stats run, then the clean run — while
# the test modules stay in `sys.modules`. Hypothesis therefore sees a single `@given` method object
# invoked from two different class instances and fails `differing_executors`, which aborts the whole
# mutation run before any mutant is tried. The check does flag a real hazard in an ordinary run, so
# it is relaxed only under mutmut, which announces itself with `MUTANT_UNDER_TEST`.
if "MUTANT_UNDER_TEST" in os.environ:
    _SUPPRESSED.append(HealthCheck.differing_executors)

settings.register_profile("narrativetrace", deadline=None, suppress_health_check=_SUPPRESSED)
settings.load_profile("narrativetrace")
