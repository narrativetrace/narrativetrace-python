# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Cross-package parity: the free CLI's ``config.output-env`` doctor check keeps its own copy of
this plugin's ``_TRUTHY`` spellings (the core distribution stays dependency-free and never imports
an integration package), documented in that check's own module docstring as a mirror. This test —
in the higher layer, importing down, never the reverse — is what catches the two copies drifting
apart."""

from __future__ import annotations

from narrativetrace_pytest.plugin import _TRUTHY

from narrativetrace.doctor.checks.output_env import TRUTHY


def test_doctors_truthy_set_matches_the_plugins_own_set() -> None:
    assert TRUTHY == _TRUTHY
