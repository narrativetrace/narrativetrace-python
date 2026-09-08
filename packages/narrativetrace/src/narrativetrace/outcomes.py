# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Completion outcome attached to a trace node or exit event.

``TraceOutcome``. Renderers and exporters pattern-match on this sealed hierarchy
instead of inferring success or failure from raw exceptions or missing events.

Not every node has a terminal value: :class:`Incomplete` means an enter was seen without a
matching exit, and some synthetic nodes (fire-and-forget launchers) carry ``None`` outcome.
"""

from __future__ import annotations

from dataclasses import dataclass

from narrativetrace.values import RenderedValue


class TraceOutcome:
    """Base of the sealed outcome union. Not instantiated directly."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class Returned(TraceOutcome):
    """Normal completion with an eager rendered return value (``None`` for void methods)."""

    rendered_value: str | None
    structured_value: RenderedValue | None = None


@dataclass(frozen=True, slots=True)
class Threw(TraceOutcome):
    """Exceptional completion with the original exception attached."""

    exception: BaseException


@dataclass(frozen=True, slots=True)
class Incomplete(TraceOutcome):
    """A method still in-flight at snapshot time (no matching exit was seen)."""
