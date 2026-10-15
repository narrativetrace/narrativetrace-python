# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A pytest plugin that writes down what the runner itself reported for every failing phase.

``recipe_artifacts.py`` loads it into the pytest process that runs a fixture (``-p``) and names a
file in ``NARRATIVETRACE_RECIPE_VERDICTS``. The recipe pages quote the runner's own message -- an
assertion's explanation, an approval rejection -- and that text exists nowhere in the trace
artifacts, so the evidence has to come from the run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from examples.recipes.checkout.env import VERDICTS_ENV


def pytest_exception_interact(
    node: pytest.Item | pytest.Collector, call: pytest.CallInfo[object]
) -> None:
    """Appends one JSON line per failing phase: the test, the phase and the exception's message."""
    target = os.environ.get(VERDICTS_ENV)
    if not target or call.excinfo is None:
        return
    verdict = {"test": node.name, "when": call.when, "message": str(call.excinfo.value)}
    with Path(target).open("a", encoding="utf-8") as verdicts:
        verdicts.write(json.dumps(verdict) + "\n")
