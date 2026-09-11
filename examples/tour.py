# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Shared scaffolding for the runnable examples: scenarios and their console sections.

Every example exposes ``scenarios() -> list[Scenario]``. A :class:`Scenario` carries a title, a
note on *how that scenario's trace is wired* (which decorators and wrappers produced what the
viewer is about to read), and a ``run(context)`` callable that exercises the domain code and
returns the captured :class:`~narrativetrace.TraceTree`. :func:`walk` prints the sections the
Java examples print (``=== title ===``, ``--- Trace tree ---``, ``--- Prose ---``, …) so the demo
launcher can colorize and pace them by line shape.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from narrativetrace_diagrams import MermaidSequenceDiagramRenderer, PlantUmlSequenceDiagramRenderer

from narrativetrace import (
    ConcurrencyKind,
    ContextVarNarrativeContext,
    EnterEvent,
    ExitEvent,
    IndentedTextRenderer,
    LoggingTraceConsumer,
    MarkdownRenderer,
    NarrativeContextFilter,
    ProseRenderer,
    TraceEvent,
)
from narrativetrace.pipeline.event_store import EventStore

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from typing import TextIO

    from narrativetrace import NarrativeContext, TraceTree


@dataclass(frozen=True, slots=True)
class Section:
    """A rendering of the captured tree, announced by its ``--- marker ---`` line."""

    marker: str
    render: Callable[[TraceTree], str]


TREE = Section("--- Trace tree ---", IndentedTextRenderer().render)
PROSE = Section("--- Prose ---", ProseRenderer().render)
MARKDOWN = Section("--- Markdown ---", MarkdownRenderer().render)
MERMAID = Section("--- Mermaid ---", MermaidSequenceDiagramRenderer().render)
PLANTUML = Section("--- PlantUML ---", PlantUmlSequenceDiagramRenderer().render)

DEFAULT_SECTIONS = (TREE, PROSE, MERMAID)


@dataclass(frozen=True, slots=True)
class Scenario:
    """One demo scenario: a titled run of the domain code plus its wiring note.

    ``intro`` lines print under the header before the code runs; ``notice`` lines print right
    after the trace tree, where the Java examples point at what the tree just revealed.
    """

    title: str
    wiring: str
    run: Callable[[NarrativeContext], TraceTree]
    sections: tuple[Section, ...] = DEFAULT_SECTIONS
    intro: tuple[str, ...] = ()
    notice: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be blank")
        if "===" in self.title:
            raise ValueError("title must not contain '==='")
        if not self.wiring.strip():
            raise ValueError("wiring note must not be blank")


def walk(
    scenarios: Sequence[Scenario], out: TextIO, context: NarrativeContext
) -> list[tuple[Scenario, TraceTree]]:
    """Runs every scenario on ``context`` (reset between them) and prints its sections to ``out``.

    Returns each scenario paired with the tree it captured, so an example can post-process the
    whole run (the clarity report, for instance).
    """
    captured: list[tuple[Scenario, TraceTree]] = []
    for index, scenario in enumerate(scenarios):
        if index:
            context.reset()
            out.write("\n")
        _print_header(scenario, out)
        tree = scenario.run(context)
        _print_sections(scenario, tree, out)
        captured.append((scenario, tree))
    return captured


def _print_header(scenario: Scenario, out: TextIO) -> None:
    out.write(f"=== {scenario.title} ===\n\n")
    for line in scenario.intro:
        out.write(f"  {line}\n")
    if scenario.intro:
        out.write("\n")


def _print_sections(scenario: Scenario, tree: TraceTree, out: TextIO) -> None:
    for section in scenario.sections:
        out.write(f"\n{section.marker}\n\n{section.render(tree)}\n")
        if section is TREE:
            for line in scenario.notice:
                out.write(f"\n  {line}\n")


# --------------------------------------------------------------------------- #
# The live stream: → ← !! lines as the code runs                              #
# --------------------------------------------------------------------------- #
BRIDGE_LOGGER_NAME = "narrativetrace"  # the bridge's own logger — narrativetrace.logging_bridge
CLASSIC_FORMAT = "%(asctime)s %(levelname)s [%(threadName)s] %(name)s - %(message)s"
_RETURN_PREFIX = "← returned: "
_EXCEPTION_PREFIX = "!! "
_ENTRY_PREFIX = "→ "


def _indent(depth: int) -> str:
    return "  " * max(depth, 0)


class DemoFormatter(logging.Formatter):
    """Bare narration for the demo stream, indented by call depth.

    Reshapes :class:`~narrativetrace.LoggingTraceConsumer` records into the line shapes the
    launcher colorizes: ``→ Class.method(name: value)``, ``← Class.method → value`` and
    ``!! Class.method ✖ Error: message [error context]``. Return and exception lines borrow the
    name from their entry record, matched by span id; other lines (fork/join markers) pass
    through at their depth.
    """

    def __init__(self) -> None:
        super().__init__("%(message)s")
        self._names: dict[str, str] = {}
        self._baseline: int | None = None  # depth of the stream's outermost call, minus one

    def format(self, record: logging.LogRecord) -> str:
        fields = record.__dict__
        message = record.getMessage()
        span = str(fields.get("spanId", ""))
        if message.startswith(_ENTRY_PREFIX):
            if self._baseline is None:
                self._baseline = int(fields.get("nt.depth", 1)) - 1
            self._names[span] = f"{fields.get('nt.class')}.{fields.get('nt.method')}"
            return _indent(self._depth(fields) - 1) + message
        depth = self._depth(fields)
        name = self._names.pop(span, "?")
        if message.startswith(_RETURN_PREFIX):
            return f"{_indent(depth)}← {name} → {message[len(_RETURN_PREFIX) :]}"
        if message.startswith(_EXCEPTION_PREFIX):
            return f"{_indent(depth)}!! {name} ✖ {message[len(_EXCEPTION_PREFIX) :]}"
        return _indent(depth) + message

    def _depth(self, fields: dict[str, object]) -> int:
        """Call depth relative to the stream's first entry — a leftover scope elsewhere in the
        process (the bridge's scope stack is a context variable) must not shift the whole run."""
        return int(str(fields.get("nt.depth", 0))) - (self._baseline or 0)


class _LiveStore(EventStore):
    """The context's event store, with every event narrated to a listener as it is added.

    Fork-join and fire-and-forget children are re-emitted into the store when they are grafted
    under their parent; those replays were already narrated live, so they are stored silently.

    A replay is recognised by the *grafting* kinds the helpers stamp when they re-emit, PLUS a
    node whose own entry timestamp was already narrated — an example that grafts a captured
    subtree for display after stripping its concurrency tag (so a static renderer shows the
    node's own header rather than folding it into a fork/fire-and-forget block) still re-emits
    ``node.start_time_nanos`` unchanged, so its second entry carries the exact timestamp its live
    occurrence did; a genuinely new call always gets a fresh one from the clock. ``ASYNC`` alone
    is not a graft: it marks a call as it happens on a worker, so narrating it is exactly right
    and suppressing it would lose the live line the worker just produced.
    """

    def __init__(self, listener: Callable[[TraceEvent], None]) -> None:
        super().__init__()
        self._listener = listener
        self._replay_depth = 0
        self._seen_entries: set[tuple[str, str, int]] = set()

    def add(self, event: TraceEvent) -> None:
        if not self._is_replay(event):
            self._listener(event)
        super().add(event)

    def _is_replay(self, event: TraceEvent) -> bool:
        if isinstance(event, EnterEvent):
            key = _entry_key(event)
            if _is_grafted(event) or self._replay_depth or key in self._seen_entries:
                self._replay_depth += 1
                return True
            self._seen_entries.add(key)
            return False
        if isinstance(event, ExitEvent) and self._replay_depth:
            self._replay_depth -= 1
            return True
        return False


_GRAFTED_KINDS = frozenset({ConcurrencyKind.FORK_JOIN, ConcurrencyKind.FIRE_AND_FORGET})


def _is_grafted(event: EnterEvent) -> bool:
    """Whether this entry is a helper re-emitting a child it already narrated live."""
    return event.concurrency is not None and event.concurrency.kind in _GRAFTED_KINDS


def _entry_key(event: EnterEvent) -> tuple[str, str, int]:
    """Identifies one method entry by what a re-emission is guaranteed to preserve exactly."""
    sig = event.signature
    return (sig.class_name, sig.method_name, event.timestamp_nanos)


def _configure_realistic_logger() -> None:
    """Wires the stdlib logging bridge the way a real project would — see
    documentation/guides/logging.md: ``logging.basicConfig`` in the entry point (a project's
    ``logback.xml``/``dictConfig`` equivalent) plus :class:`~narrativetrace.NarrativeContextFilter`
    stamping the current span's keys onto every record. A no-op once the root logger already has a
    handler (a second example run in this process, or pytest's own log capture), so it never fights
    another realistic configuration or a test session's log fixtures.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s"))
    handler.addFilter(NarrativeContextFilter())
    logging.basicConfig(level=logging.DEBUG, handlers=[handler])


@contextmanager
def narrated_run(out: TextIO, *, classic: bool = False) -> Iterator[ContextVarNarrativeContext]:
    """A context whose events stream to ``out`` as they happen — the live ``→ ← !!`` lines —
    AND to the example's realistically configured logger.

    Both views come from ONE :class:`~narrativetrace.LoggingTraceConsumer`, bound to
    ``logging.getLogger("narrativetrace")`` — the same bridge logger documentation/guides/logging.md
    names. A dedicated handler on that logger renders the demo shape to ``out`` (``classic`` wears
    the traditional timestamped format with :class:`~narrativetrace.NarrativeContextFilter`
    stamping span keys; otherwise :class:`DemoFormatter` prints bare narration indented by depth),
    and — because loggers propagate by default — the same record also reaches whatever
    :func:`_configure_realistic_logger` attached to the root logger: a real project's
    ``logging.basicConfig``. Two consumers on the same event stream would double the bridge's MDC
    depth-tracking (a bug found writing this); one consumer with two handlers avoids it.
    """
    _configure_realistic_logger()
    logger = logging.getLogger(BRIDGE_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(out)
    if classic:
        handler.setFormatter(logging.Formatter(CLASSIC_FORMAT))
        handler.addFilter(NarrativeContextFilter())
    else:
        handler.setFormatter(DemoFormatter())
    logger.addHandler(handler)
    try:
        yield ContextVarNarrativeContext(store=_LiveStore(LoggingTraceConsumer(logger)))
    finally:
        handler.flush()
        logger.removeHandler(handler)
