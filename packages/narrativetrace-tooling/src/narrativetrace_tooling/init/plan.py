# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Everything an install or an uninstall would do, decided before anything is written.

INTENT: the seam that makes approval structural. A plan can be rendered as a diff, reviewed, and
only then applied — and because it is complete, applying it needs no second look at the project.

**@llmNote** A plan holds at most ONE action per path. Two actions on one path would make the diff a
lie (the second would be computed from a state the first has not produced), so the planners never
emit one and the invariant refuses it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from narrativetrace_tooling.init.action import Action, Refuse


@dataclass(frozen=True, slots=True)
class InitPlan:
    """A complete, reviewable plan.

    :param carrier: the coordinate everything in this plan is stamped with
    :param dry_run: whether this plan is for showing only — a dry run exits 0 even when it refuses
    :param actions: the actions, in the order a person should read them
    """

    carrier: str
    dry_run: bool
    actions: tuple[Action, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.carrier, str) or not self.carrier.strip():
            raise ValueError("a plan names the carrier it came from")
        if not isinstance(self.actions, Sequence) or isinstance(self.actions, str):
            raise TypeError("a plan with no actions is an empty tuple, never None")
        object.__setattr__(self, "actions", tuple(self.actions))
        assert _invariant(self), "a plan holds at most one action per path"

    @property
    def is_empty(self) -> bool:
        """True when there is nothing to do — the shape a re-run of an up-to-date install
        produces."""
        return not self.actions

    @property
    def refusals(self) -> tuple[Refuse, ...]:
        """Every refusal, in plan order."""
        return tuple(action for action in self.actions if isinstance(action, Refuse))

    @property
    def has_refusals(self) -> bool:
        """True when at least one action is a refusal."""
        return bool(self.refusals)

    @property
    def exit_code(self) -> int:
        """The exit code an entry point returns: 1 when anything was refused, 0 otherwise — and
        always 0 for a dry run, where a refusal is something shown rather than something that
        happened."""
        return 1 if not self.dry_run and self.has_refusals else 0


def _invariant(plan: InitPlan) -> bool:
    """Returns whether a plan is consistent: one action per path, every path project-relative.

    Constructor guards make this true for every live instance; tests re-check it around each case.
    """
    paths: list[Path] = [action.path for action in plan.actions]
    return len(set(paths)) == len(paths) and not any(path.is_absolute() for path in paths)
