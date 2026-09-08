# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared renderer contract and document metadata.

``NarrativeRenderer`` and ``TraceMetadata``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.tree import TraceTree


class NarrativeRenderer(Protocol):
    """Turns an immutable :class:`TraceTree` into text (pure view transformation)."""

    def render(self, tree: TraceTree) -> str: ...


@dataclass(frozen=True, slots=True)
class TraceMetadata:
    """Caller-supplied metadata for rendering a trace as a standalone document.

    ``result`` is a :class:`~narrativetrace.render.scenario_result.ScenarioResult`, so the wire
    spelling written into JSON and the display spelling rendered into Markdown come from one value
    and cannot drift. A string is accepted for compatibility and parsed through
    :meth:`ScenarioResult.from_text`: either spelling is fine, anything else raises here rather
    than reaching an artifact the canonical schema would reject.
    """

    scenario: str
    result: ScenarioResult

    def __post_init__(self) -> None:
        if isinstance(self.result, str):
            object.__setattr__(self, "result", ScenarioResult.from_text(self.result))
        if not isinstance(self.result, ScenarioResult):
            raise TypeError("result must be a ScenarioResult")
