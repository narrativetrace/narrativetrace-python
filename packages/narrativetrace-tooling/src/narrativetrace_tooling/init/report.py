# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What actually happened when a plan was applied, action by action.

INTENT: the answer a caller reports and exits on. A refusal — planned, or discovered when the
filesystem would not cooperate — is DATA here, never an exception, so one impossible action never
costs a run the actions that did work.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, unique

from narrativetrace_tooling.init.action import Action


@unique
class Status(Enum):
    """Whether an action happened."""

    APPLIED = "applied"
    """The filesystem now says what the action promised."""

    REFUSED = "refused"
    """Nothing was done, and :attr:`Applied.detail` says why."""


@dataclass(frozen=True, slots=True)
class Applied:
    """One action's outcome.

    **@llmNote** A :attr:`Status.REFUSED` result must carry a reason — the same contract
    :class:`~narrativetrace_tooling.init.action.Refuse` holds on the planning side. A refusal nobody
    can act on is worse than no refusal at all: it reaches a person as an empty parenthesis in a
    warning.

    :param action: the action as planned
    :param status: whether it happened
    :param detail: why it did not, or ``""`` when it did
    """

    action: Action
    status: Status
    detail: str

    def __post_init__(self) -> None:
        if self.action is None:
            raise TypeError("an execution result needs the action it is about")
        if not isinstance(self.status, Status):
            raise TypeError(
                f"an execution result needs a status, never {type(self.status).__name__}"
            )
        if not isinstance(self.detail, str):
            raise TypeError(
                f'a detail is "" when there is none, never {type(self.detail).__name__}'
            )
        if self.status is Status.REFUSED and not self.detail.strip():
            raise ValueError(
                f"a refusal carries the reason it refused — {self.action.path} gives none"
            )


def applied(action: Action) -> Applied:
    """The result of an action that happened."""
    return Applied(action, Status.APPLIED, "")


def refused(action: Action, detail: str) -> Applied:
    """The result of an action that did not, and why."""
    return Applied(action, Status.REFUSED, detail)


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """One entry per action, in plan order.

    :param carrier: the coordinate the plan was stamped with
    :param results: one entry per action, in plan order
    """

    carrier: str
    results: tuple[Applied, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.carrier, str) or not self.carrier.strip():
            raise ValueError("a report names the carrier the plan came from")
        if not isinstance(self.results, Sequence) or isinstance(self.results, str):
            raise TypeError("a report with no results is an empty tuple, never None")
        object.__setattr__(self, "results", tuple(self.results))

    @property
    def has_refusals(self) -> bool:
        """True when anything was refused."""
        return any(result.status is Status.REFUSED for result in self.results)

    @property
    def exit_code(self) -> int:
        """1 when anything was refused, 0 otherwise — what an entry point returns."""
        return 1 if self.has_refusals else 0
