# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Coverage.py's own "measuring subprocesses" recipe -- coverage.py ships no hook that turns
this on automatically (it would mean silently instrumenting every Python subprocess on the
machine, which it deliberately does not do by default).

This package's entire plugin behaviour is exercised through ``pytester.runpytest_subprocess()``
(a real child ``python -m pytest`` process, never in-process), so without this file the plugin's
own execution is invisible to any coverage tracer running in the parent test process. Importable
only because ``conftest.py`` prepends this directory to ``PYTHONPATH`` for the duration of this
package's own test session (and only that -- ``Pytester.popen()`` inherits the parent's
environment, so a variable set here propagates to every subprocess pytester spawns); the ``site``
module imports any ``sitecustomize`` it finds on the path automatically at interpreter start,
which is what actually invokes this.
"""

from __future__ import annotations

import coverage

coverage.process_startup()
