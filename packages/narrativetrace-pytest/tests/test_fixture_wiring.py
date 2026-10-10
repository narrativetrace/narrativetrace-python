# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The pytest row's wiring fixture works as printed: run under the real plugin, its test passes and
the plugin writes that test's trace."""

from __future__ import annotations

from pathlib import Path

import pytest

_FIXTURE = Path(__file__).with_name("fixture_wiring.py")


def test_the_wired_test_passes_and_writes_its_trace(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(test_wired=_FIXTURE.read_text(encoding="utf-8"))

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)
    traces = [path.read_text(encoding="utf-8") for path in out_dir.rglob("*.md")]
    assert any("OrderService.place_order" in text for text in traces)
