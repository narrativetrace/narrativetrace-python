# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The default-logger row's wiring fixture works as printed: in a fresh interpreter, whose root
logger has no handler (the row's starting point), the trace reaches standard output through the
stdlib root logger. A fresh interpreter because pytest's own log capture puts handlers on the root
logger during a test, and ``logging.basicConfig`` rightly stands down when any are there."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_FIXTURE = Path(__file__).with_name("logging_wiring.py")


def test_the_trace_reaches_stdout_through_the_root_logger() -> None:
    completed = subprocess.run(  # nosec B603 - this interpreter, this repository's own fixture
        [sys.executable, str(_FIXTURE)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "OrderService.place_order" in completed.stdout
