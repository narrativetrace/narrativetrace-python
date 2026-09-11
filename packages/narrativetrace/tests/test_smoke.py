# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Smoke test proving the package imports and the quality gate has something to run."""

from narrativetrace import __version__


def test_version_is_exposed() -> None:
    assert __version__ == "0.1.1"
