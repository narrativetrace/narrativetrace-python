# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from contract_probe.versions import is_applicable


def test_applicable_when_since_is_earlier_than_installed() -> None:
    assert is_applicable("0.1.0", "0.2.1") is True


def test_applicable_when_since_equals_installed() -> None:
    # Ruling 1: exempt only while STRICTLY later than installed -- equal still applies.
    assert is_applicable("0.2.1", "0.2.1") is True


def test_not_applicable_when_since_is_later_than_installed() -> None:
    assert is_applicable("0.2.2", "0.2.1") is False


def test_applicable_handles_different_segment_counts() -> None:
    assert is_applicable("0.1", "0.1.1") is True
    assert is_applicable("0.1.2", "0.1") is False
