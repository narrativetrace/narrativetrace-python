# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the shared TraceNode tree-walk depth/cycle guard."""

from __future__ import annotations

from narrativetrace.tree_walk import CYCLE_MARKER, DEPTH_LIMIT_MARKER, MAX_DEPTH, TreeWalk


class TestFreshWalk:
    def test_a_root_has_no_stop_reason(self) -> None:
        walk = TreeWalk()
        assert walk.stop_reason(object()) is None


class TestCycleDetection:
    def test_a_node_already_on_the_current_path_reports_the_cycle_marker(self) -> None:
        walk = TreeWalk()
        node = object()
        walk.enter(node)
        assert walk.stop_reason(node) == CYCLE_MARKER

    def test_a_node_no_longer_on_the_path_after_exit_is_not_a_cycle(self) -> None:
        walk = TreeWalk()
        node = object()
        walk.enter(node)
        walk.exit(node)
        assert walk.stop_reason(node) is None

    def test_a_diamond_reached_by_two_different_paths_is_not_a_cycle(self) -> None:
        """The same node reached twice via different, non-nested paths (a shared subtree) must
        never be flagged -- only a node that is its own ancestor on the *current* path is."""
        walk = TreeWalk()
        shared = object()
        parent_a, parent_b = object(), object()

        walk.enter(parent_a)
        assert walk.stop_reason(shared) is None
        walk.enter(shared)
        walk.exit(shared)
        walk.exit(parent_a)

        walk.enter(parent_b)
        assert walk.stop_reason(shared) is None
        walk.exit(parent_b)


class TestDepthBound:
    def test_depth_within_the_cap_has_no_stop_reason(self) -> None:
        walk = TreeWalk()
        ancestors = [object() for _ in range(MAX_DEPTH - 1)]
        for ancestor in ancestors:
            walk.enter(ancestor)
        assert walk.stop_reason(object()) is None

    def test_depth_at_the_cap_reports_the_depth_limit_marker(self) -> None:
        walk = TreeWalk()
        ancestors = [object() for _ in range(MAX_DEPTH)]
        for ancestor in ancestors:
            walk.enter(ancestor)
        assert walk.stop_reason(object()) == DEPTH_LIMIT_MARKER

    def test_exit_returns_depth_budget(self) -> None:
        walk = TreeWalk()
        ancestors = [object() for _ in range(MAX_DEPTH)]
        for ancestor in ancestors:
            walk.enter(ancestor)
        node = object()
        assert walk.stop_reason(node) == DEPTH_LIMIT_MARKER
        walk.exit(ancestors[-1])  # unwind one level, as a caller's finally would on the way up
        assert walk.stop_reason(node) is None

    def test_cycle_is_reported_even_within_the_depth_cap(self) -> None:
        """A cycle short enough to still be within budget is still a cycle, not a depth stop --
        the two reasons are independent checks, cycle taking precedence when both would apply."""
        walk = TreeWalk()
        node = object()
        walk.enter(node)
        assert walk.stop_reason(node) == CYCLE_MARKER
