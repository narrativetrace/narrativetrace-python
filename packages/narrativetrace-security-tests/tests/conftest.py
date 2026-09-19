# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Hypothesis profile handling for this package's own subprocess-isolated test runs.

`poe fuzz` (`scripts/fuzz_report.py`) invokes this package's fuzz-target test files as a
standalone `pytest` subprocess — never mixed into the same session as any other package's tests.
`fuzz_config.py`'s own docstring explains why a profile is never loaded unconditionally at import
time here: `settings.load_profile` is a process-wide side effect, and this package's tests
otherwise run inside the shared `poe test`/`poe check` session alongside every other package's, so
loading one here unconditionally would silently change Hypothesis's behaviour (deadline, health
checks) for every other package's property tests too.

**Release rule 2** ("a graceful-skip tool must prove it has ever run", confirmed as a live gap
2026-09-17 by the Linux-box nightly report, `reports/nightly/2026-09-17-manual.md` finding F1):
the nightly quality run sets `HYPOTHESIS_PROFILE=fuzz`, but nothing in this repository ever read
that variable — no profile named "fuzz" existed, and no code called `settings.load_profile` with
it — so a typo or a stale value was silently ignored rather than failing, indistinguishable from
the variable actually doing its job. Fixed by registering the "fuzz" profile and making the
variable OPT-IN load-bearing (absent → untouched, so `poe test`/`poe check` behave exactly as
before this file existed): when set, whatever profile name it names is loaded — Hypothesis's own
`settings.load_profile` raises `InvalidArgument` for an unregistered name, so a typo now fails
loudly instead of vanishing (see `test_hypothesis_profile.py`).
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

_PROFILE_ENV_VAR = "HYPOTHESIS_PROFILE"

# Same relaxed posture as the "narrativetrace" package's own default profile
# (packages/narrativetrace/tests/conftest.py) -- named separately so the nightly's intent
# (HYPOTHESIS_PROFILE=fuzz) is visible in its own invocation rather than borrowing another
# package's profile name.
settings.register_profile("fuzz", deadline=None, suppress_health_check=[HealthCheck.too_slow])

_requested_profile = os.environ.get(_PROFILE_ENV_VAR)
if _requested_profile is not None:
    settings.load_profile(_requested_profile)  # raises InvalidArgument for an unregistered name
