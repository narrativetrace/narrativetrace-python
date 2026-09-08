# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for ConcurrencyKind and ConcurrencyInfo."""

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind


def test_kinds() -> None:
    assert {k.name for k in ConcurrencyKind} == {"FORK_JOIN", "FIRE_AND_FORGET", "ASYNC"}


def test_concurrency_info_fields() -> None:
    info = ConcurrencyInfo(
        group_id="g1",
        thread_name="worker-1",
        thread_id=42,
        virtual=False,
        kind=ConcurrencyKind.FORK_JOIN,
        task_label="place-order",
    )
    assert info.group_id == "g1"
    assert info.thread_name == "worker-1"
    assert info.thread_id == 42
    assert info.virtual is False
    assert info.kind is ConcurrencyKind.FORK_JOIN
    assert info.task_label == "place-order"


def test_task_label_defaults_to_none() -> None:
    info = ConcurrencyInfo(group_id="g1", kind=ConcurrencyKind.FIRE_AND_FORGET)
    assert info.task_label is None
    assert info.thread_name is None
