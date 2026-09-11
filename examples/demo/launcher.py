# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Demo launcher — one command, the trace story front and center.

    python -m examples.demo                         interactive example picker
    python -m examples.demo --example ecommerce     non-interactive
    python -m examples.demo --example ecommerce --classic    timestamped logs, no styling
    python -m examples.demo --example ecommerce --no-pause   play straight through
    python -m examples.demo --list                  list the examples

On a terminal the demo stops after each scenario — ``[Enter]`` continues, ``q`` quits — and every
scenario opens with a note on how its trace is wired (the ``wiring`` of each
:class:`examples.tour.Scenario`). A paced run is recorded first and then walked, so a stop point
can never inflate the durations the trace tree reports. Colors follow ``NO_COLOR`` /
``FORCE_COLOR`` / whether stdout is a terminal; pipes and CI get the example's verbatim output.

Translated runs (``--lang es|zh-CN``) re-render the same recorded scenarios through the chosen
example's committed ``glossary.json`` (:mod:`examples.demo.translate`): identifiers get glossed,
values stay byte-identical, and untranslated phrases land in a "glossary gaps" footer per
scenario. ``--classic`` has no translated variant (it is raw, unstyled logging output) and is
refused together with a non-English ``--lang``.

Picking an example through the interactive picker (a terminal, no ``--example``) is also followed
by a language menu, but only when the chosen example's glossary covers more than one locale
(``en`` always counts as available, so one curated locale is already "more than one"). An
explicit ``--lang`` always wins and skips the menu; so does ``--classic``, which has nothing to
translate.
"""

from __future__ import annotations

import argparse
import importlib
import io
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from examples.demo.translate import (
    declared_locales,
    load_example_glossary,
    menu_locales,
    render_translated_scenarios,
    translated_lines,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence
    from typing import TextIO

    from examples.tour import Scenario

EXAMPLES: dict[str, str] = {
    "ecommerce": "examples.ecommerce.ecommerce",
    "hotel_booking": "examples.hotel_booking.hotel_booking",
    "library": "examples.library.library",
    "minecraft": "examples.minecraft.minecraft",
}

TREE_MARKER = "--- Trace tree ---"
RULE = "─" * 60
QUIT = "q"

# Every example also sends its trace to a realistically configured `logging.basicConfig` —
# see examples/tour.py::_configure_realistic_logger and documentation/guides/logging.md. Run
# directly (`python -m examples.<name>`) that lands on the terminal; here it would drown the
# colorized walk this launcher paces, so the launcher claims `basicConfig` first and points it at
# this file instead — same `narrative-traces/` convention `narrativetrace-pytest` already writes
# under.
DEMO_LOG_PATH = Path("narrative-traces") / "demo.log"

RENDERER_NOTE = (
    "Renderers are not configured: there is no default, no registry, no setting. Capture\n"
    "produces a TraceTree and you call the renderer you want — here that is one line,\n"
    "IndentedTextRenderer().render(tree); ProseRenderer, MarkdownRenderer and the diagram\n"
    "renderers below are the same deal. A renderer is any callable from TraceTree to str.\n"
    "The live → ← !! lines are not a renderer at all: that is LoggingTraceConsumer fed from\n"
    "the context's event store, formatting each event as it happens — the only view you get\n"
    "without writing any rendering code, and what your log tool ingests.\n"
    "Configuration picks a renderer in exactly one place, trace files written from tests:\n"
    "NARRATIVETRACE_OUTPUT=true with NARRATIVETRACE_FORMAT=markdown|text|mermaid|plantuml\n"
    "(markdown is the default; narrativetrace.toml and pyproject.toml set the same keys)."
)

_MARKER_ANNOTATIONS = {
    TREE_MARKER: (
        "--- Trace tree — IndentedTextRenderer over the SAME trace as the stream above: "
        "structure, values, timings ---"
    ),
    "--- Prose ---": (
        "--- Prose — ProseRenderer, same trace as English sentences; your names become the "
        "story ---"
    ),
    "--- Markdown ---": (
        "--- Markdown — MarkdownRenderer, the per-test trace file format, same trace ---"
    ),
    "--- Mermaid ---": (
        "--- Mermaid — MermaidSequenceDiagramRenderer, markup to paste into mermaid.live ---"
    ),
    "--- PlantUML ---": (
        "--- PlantUML — PlantUmlSequenceDiagramRenderer markup, render it with plantuml ---"
    ),
}

_HEADER = re.compile(r"^=== (?P<title>.*) ===$")
_BANNER = re.compile(r"^=+$")
_MARKER = re.compile(r"^--- .* ---$")


# --------------------------------------------------------------------------- #
# Arguments                                                                   #
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m examples.demo",
        description="Run a NarrativeTrace example with the live narration colorized and paced.",
    )
    parser.add_argument("-e", "--example", choices=sorted(EXAMPLES), help="which example to run")
    parser.add_argument("--list", action="store_true", help="list the examples and exit")
    parser.add_argument(
        "--classic", action="store_true", help="traditional timestamped logs, no demo styling"
    )
    parser.add_argument(
        "--no-pause", action="store_true", help="play straight through, no stop points"
    )
    parser.add_argument(
        "--lang",
        default=None,
        help="trace language ('en', or a locale the example's glossary.json covers); "
        "unset lets the interactive picker offer a menu when the example has one to offer",
    )
    return parser


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    return build_parser().parse_args(list(argv))


# --------------------------------------------------------------------------- #
# Terminal policy — pure functions, unit-tested                               #
# --------------------------------------------------------------------------- #
def color_enabled(*, no_color: str | None, force_color: str | None, stdout_tty: bool) -> bool:
    """``NO_COLOR`` wins; otherwise ``FORCE_COLOR`` or a terminal turns colors on."""
    if no_color:
        return False
    return bool(force_color) or stdout_tty


def styled_output(*, force_color: str | None, stdout_tty: bool) -> bool:
    """Legend, wiring notes and stop points need a viewer: a terminal, or a forced recording."""
    return bool(force_color) or stdout_tty


def should_pause(*, no_pause: bool, classic: bool, stdin_tty: bool, stdout_tty: bool) -> bool:
    """Stop points need a terminal on both ends, and never apply to ``--classic``."""
    return not no_pause and not classic and stdin_tty and stdout_tty


# --------------------------------------------------------------------------- #
# Styling                                                                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Palette:
    cyan: str = ""
    green: str = ""
    red: str = ""
    yellow: str = ""
    magenta: str = ""
    dim: str = ""
    reset: str = ""

    @classmethod
    def ansi(cls) -> Palette:
        return cls(
            cyan="\033[36m",
            green="\033[32m",
            red="\033[1;31m",
            yellow="\033[1;33m",
            magenta="\033[1;35m",
            dim="\033[2m",
            reset="\033[0m",
        )

    @classmethod
    def plain(cls) -> Palette:
        return cls()

    def paint(self, color: str, text: str) -> str:
        return f"{color}{text}{self.reset}" if color else text


def style_line(line: str, palette: Palette) -> str:
    """Colors one line by its shape: headers yellow, markers magenta, → cyan, ←/-> green, !! red.

    ``-> `` is the translated view's own return marker (:mod:`narrativetrace_glossary.
    translation_view`), rendered without the arrow glyph so it survives every terminal encoding —
    colored the same green as its plain-English ``← `` counterpart.
    """
    indent = line[: len(line) - len(line.lstrip(" "))]
    body = line[len(indent) :]
    if (
        _HEADER.match(line)
        or _BANNER.match(line)
        or line == "CLARITY ANALYSIS REPORT".center(41).rstrip()
    ):
        return palette.paint(palette.yellow, line)
    if _MARKER.match(line):
        return palette.paint(palette.magenta, _MARKER_ANNOTATIONS.get(line, line))
    if body.startswith("→ "):
        return indent + palette.paint(palette.cyan, body)
    if body.startswith("← ") or body.startswith("-> "):
        return indent + palette.paint(palette.green, body)
    if body.startswith("!! "):
        return indent + palette.paint(palette.red, body)
    return line


def legend(palette: Palette) -> str:
    """The four-line key printed before a styled run: what → ← !! / tree / prose / diagram are."""
    p = palette
    opening = (
        "One recording, many views — every section below is the SAME captured trace, re-rendered:"
    )
    closing = (
        "Each scenario opens with how its trace is configured. "
        "No logging code was written for any of it."
    )
    return (
        f"\n{p.paint(p.dim, opening)}\n\n"
        f"  {p.paint(p.cyan, '→ method entered')}   {p.paint(p.green, '← returned')}   "
        f"{p.paint(p.red, '!! exception')}   live, as the code runs; indent = call depth\n\n"
        "  tree     structure, values, and timings; // lines are @narrated templates\n\n"
        "  prose    the trace as English sentences — derived from your class and method names\n\n"
        "  diagram  Mermaid and PlantUML markup for the same calls\n\n"
        f"{p.paint(p.dim, closing)}\n"
    )


# --------------------------------------------------------------------------- #
# Presenting a recorded run: wiring notes and stop points                     #
# --------------------------------------------------------------------------- #
class Example(Protocol):
    """What the launcher needs from an example module."""

    def scenarios(self) -> list[Scenario]: ...

    def run_example(self, out: TextIO, *, classic: bool = False) -> None: ...


def load_example(name: str) -> Example:
    module: Example = importlib.import_module(EXAMPLES[name])
    return module


def wiring_table(example: Example) -> dict[str, str]:
    """Notes keyed by the exact title between ``=== `` and `` ===``, plus the header-less ones."""
    table = {scenario.title: scenario.wiring for scenario in example.scenarios()}
    table.update(getattr(example, "EXTRA_WIRING", {}))
    table[TREE_MARKER] = RENDERER_NOTE
    return table


class Presenter:
    """Walks recorded lines: styles them, explains each section, and stops at scenario boundaries.

    ``pause`` receives the prompt and returns ``False`` when the viewer quits; pass ``None`` to
    play straight through.
    """

    def __init__(
        self,
        out: TextIO,
        palette: Palette,
        wiring: Mapping[str, str],
        pause: Callable[[str], bool] | None,
    ) -> None:
        self._out = out
        self._palette = palette
        self._wiring = wiring
        self._pause = pause
        self._boundaries = 0
        self._banners = 0
        self._renderers_explained = False
        self._quit = False

    def present(self, lines: Iterable[str]) -> None:
        for line in lines:
            self._present_line(line)
            if self._quit:
                return
        self._stop("[Enter] finish")

    def _present_line(self, line: str) -> None:
        header = _HEADER.match(line)
        if header:
            if not self._boundary("scenario"):
                return
            self._emit(style_line(line, self._palette))
            self._explain(header.group("title"))
        elif _BANNER.match(line):
            self._banners += 1
            if self._banners == 1 and not self._boundary("section"):
                return
            self._emit(style_line(line, self._palette))
            if self._banners == 2:
                self._explain("CLARITY ANALYSIS REPORT")
        elif line == TREE_MARKER and not self._renderers_explained:
            self._renderers_explained = True
            self._emit(style_line(line, self._palette))
            self._explain(TREE_MARKER)
        else:
            self._emit(style_line(line, self._palette))

    def _boundary(self, what: str) -> bool:
        """A stop point plus the rule that opens every section; ``False`` once the viewer quit."""
        prompt = (
            f"[Enter] next {what}   ·   [q] quit"
            if self._boundaries
            else "[Enter] start the demo   ·   [q] quit"
        )
        self._boundaries += 1
        self._stop(prompt)
        if self._quit:
            return False
        self._emit(self._palette.paint(self._palette.dim, RULE))
        return True

    def _explain(self, key: str) -> None:
        note = self._wiring.get(key)
        if note is None:
            return
        self._emit("")
        for text in note.split("\n"):
            self._emit(self._palette.paint(self._palette.dim, f"    {text}"))

    def _stop(self, prompt: str) -> None:
        if self._pause is not None and not self._pause(prompt):
            self._quit = True

    def _emit(self, text: str) -> None:
        self._out.write(text + "\n")


def terminal_pause(
    out: TextIO, read_line: Callable[[], str], palette: Palette
) -> Callable[[str], bool]:
    """A stop point on a terminal: prints the prompt, waits for a key, erases the prompt line."""

    def pause(prompt: str) -> bool:
        out.write(palette.paint(palette.dim, f"   {prompt} "))
        out.flush()
        try:
            answer = read_line()
        except EOFError:
            answer = QUIT
        out.write("\033[1A\033[2K" if palette.reset else "\n")
        return not answer.strip().lower().startswith(QUIT)

    return pause


# --------------------------------------------------------------------------- #
# The picker                                                                  #
# --------------------------------------------------------------------------- #
def _pick(
    prompt: str, choices: Sequence[str], out: TextIO, read_line: Callable[[], str]
) -> str | None:
    """Asks until a number or a name from ``choices`` comes back; ``None`` on end of input."""
    out.write(f"{prompt}\n")
    for index, choice in enumerate(choices, start=1):
        out.write(f"  {index}) {choice}\n")
    while True:
        out.write("#? ")
        out.flush()
        try:
            answer = read_line().strip()
        except EOFError:
            return None
        if answer in choices:
            return answer
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]


def pick_example(names: Sequence[str], out: TextIO, read_line: Callable[[], str]) -> str | None:
    """Asks until a number or a name from ``names`` comes back; ``None`` on end of input."""
    return _pick("Which example? (the trace narrates as the code runs)", names, out, read_line)


def pick_lang(locales: Sequence[str], out: TextIO, read_line: Callable[[], str]) -> str | None:
    """Asks until a number or a locale from ``locales`` comes back; ``None`` on end of input.

    Same idiom as :func:`pick_example` — a numbered list, an ``#?`` prompt, end of input gives up
    rather than defaulting to English silently.
    """
    prompt = (
        "Which language? / ¿Qué idioma? / 哪种语言? (the SAME run re-rendered via the glossary)"
    )
    return _pick(prompt, locales, out, read_line)


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Terminal:
    """The bits of the environment the launcher decides on, gathered once so tests can fake them."""

    stdout_tty: bool
    stdin_tty: bool
    no_color: str | None
    force_color: str | None

    @classmethod
    def detect(cls, environ: Mapping[str, str]) -> Terminal:
        return cls(
            stdout_tty=sys.stdout.isatty(),
            stdin_tty=sys.stdin.isatty(),
            no_color=environ.get("NO_COLOR"),
            force_color=environ.get("FORCE_COLOR"),
        )


def _resolve_example(
    args: argparse.Namespace, terminal: Terminal, out: TextIO, err: TextIO
) -> str | None:
    if args.example:
        return str(args.example)
    if not terminal.stdin_tty:
        err.write("stdin is not a terminal: pass --example NAME (see --list)\n")
        return None
    return pick_example(sorted(EXAMPLES), out, input)


def _offer_lang_menu(name: str, out: TextIO, read_line: Callable[[], str]) -> str | None:
    """The language menu for one already-chosen example; ``"en"`` outright when there is no real
    choice (no committed glossary, or a glossary that covers no locale beyond English), and
    ``None`` only if the menu itself is quit (end of input, same as :func:`pick_example`).
    """
    glossary = load_example_glossary(name)
    if glossary is None:
        return "en"
    locales = menu_locales(glossary)
    if len(locales) <= 1:
        return "en"
    out.write("\n")
    return pick_lang(locales, out, read_line)


def _resolve_lang(
    args: argparse.Namespace, name: str, *, interactive_pick: bool, terminal: Terminal, out: TextIO
) -> str | None:
    """The run's language: the explicit ``--lang``, a menu pick, or ``"en"``; ``None`` on quit.

    The menu is offered only in the interactive picker flow — a terminal, and the example itself
    came from :func:`pick_example` rather than ``--example`` — and never under ``--classic``,
    which has no translated variant to render at all.
    """
    if args.lang is not None:
        return str(args.lang)
    if interactive_pick and terminal.stdin_tty and not args.classic:
        return _offer_lang_menu(name, out, input)
    return "en"


def _route_realistic_logger_to_a_file() -> None:
    """Claims ``logging.basicConfig`` before any example does, pointed at :data:`DEMO_LOG_PATH`
    instead of the terminal. A no-op once the root logger already has a handler (a test session's
    own log capture, or a second call in this process), same guard as
    ``examples.tour._configure_realistic_logger`` — the two never fight over which one wins.
    """
    DEMO_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        filename=str(DEMO_LOG_PATH),
        filemode="w",
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def run(argv: Sequence[str], terminal: Terminal, out: TextIO, err: TextIO) -> int:
    """The launcher proper; ``main`` binds it to the real terminal."""
    args = parse_args(argv)
    if args.list:
        out.write("".join(f"{name}\n" for name in sorted(EXAMPLES)))
        return 0
    interactive_pick = not args.example
    name = _resolve_example(args, terminal, out, err)
    if name is None:
        return 2
    lang = _resolve_lang(args, name, interactive_pick=interactive_pick, terminal=terminal, out=out)
    if lang is None:
        return 2
    args.lang = lang
    if args.lang != "en" and args.classic:
        err.write("--classic replays raw log output; it has no translated variant.\n")
        return 2
    example = load_example(name)
    if args.lang != "en":
        return _run_translated(name, example, args, terminal, out, err)
    if args.classic:
        out.write(
            "Classic log format: same run, ordinary logging — date, level, [thread], logger.\n\n"
        )
        example.run_example(out, classic=True)
        return 0
    if not styled_output(force_color=terminal.force_color, stdout_tty=terminal.stdout_tty):
        example.run_example(out)
        return 0
    _present_styled(name, example, args, terminal, out)
    return 0


def _run_translated(
    name: str,
    example: Example,
    args: argparse.Namespace,
    terminal: Terminal,
    out: TextIO,
    err: TextIO,
) -> int:
    """``--lang`` dispatch: checks locale support, then renders or refuses with a precise reason."""
    glossary = load_example_glossary(name)
    if glossary is None:
        err.write(
            f"--lang {args.lang}: {name} has no committed glossary.json yet; only 'en' runs.\n"
        )
        return 2
    supported = declared_locales(glossary)
    if args.lang not in supported:
        available = ", ".join(sorted(supported)) or "none yet"
        err.write(
            f"--lang {args.lang}: {name}'s glossary has no {args.lang} translations "
            f"(available: {available}).\n"
        )
        return 2
    rendered = render_translated_scenarios(example, glossary, args.lang)
    if not styled_output(force_color=terminal.force_color, stdout_tty=terminal.stdout_tty):
        for line in translated_lines(rendered):
            out.write(f"{line}\n")
        return 0
    _present_translated(name, example, args, terminal, out, rendered)
    return 0


def _present_styled(
    name: str, example: Example, args: argparse.Namespace, terminal: Terminal, out: TextIO
) -> None:
    palette = (
        Palette.ansi()
        if color_enabled(
            no_color=terminal.no_color,
            force_color=terminal.force_color,
            stdout_tty=terminal.stdout_tty,
        )
        else Palette.plain()
    )
    pausing = should_pause(
        no_pause=args.no_pause,
        classic=args.classic,
        stdin_tty=terminal.stdin_tty,
        stdout_tty=terminal.stdout_tty,
    )
    out.write(legend(palette))
    recording = io.StringIO()
    example.run_example(recording)  # recorded in full first, so the timings stay honest
    pause = terminal_pause(out, input, palette) if pausing else None
    Presenter(out, palette, wiring_table(example), pause).present(recording.getvalue().splitlines())
    command = f"python -m examples.demo --example {name}"
    out.write(f"\nTip: {command} --classic replays this as timestamped logs.\n")
    if pausing:
        out.write(f"     {command} --no-pause plays it straight through.\n")
    out.write(
        f"     The same trace also reached your logger — see {DEMO_LOG_PATH} "
        "(examples/tour.py::_configure_realistic_logger); run the example directly "
        f"(python -m examples.{name}) to see that line on your terminal instead.\n"
    )


def _translated_note(locale: str, name: str, palette: Palette) -> str:
    text = (
        f"\nTranslated run ({locale}) — re-rendering the same recorded traces through\n"
        f"examples/{name}/glossary.json: identifiers are glossed with the original kept\n"
        "alongside them, values stay byte-identical, and any untranslated phrase lands in\n"
        'a "glossary gaps" footer at the end of its scenario.\n'
    )
    return palette.paint(palette.dim, text)


def _present_translated(
    name: str,
    example: Example,
    args: argparse.Namespace,
    terminal: Terminal,
    out: TextIO,
    rendered: list[tuple[Scenario, str]],
) -> None:
    palette = (
        Palette.ansi()
        if color_enabled(
            no_color=terminal.no_color,
            force_color=terminal.force_color,
            stdout_tty=terminal.stdout_tty,
        )
        else Palette.plain()
    )
    pausing = should_pause(
        no_pause=args.no_pause,
        classic=False,
        stdin_tty=terminal.stdin_tty,
        stdout_tty=terminal.stdout_tty,
    )
    out.write(_translated_note(args.lang, name, palette))
    pause = terminal_pause(out, input, palette) if pausing else None
    Presenter(out, palette, wiring_table(example), pause).present(translated_lines(rendered))
    command = f"python -m examples.demo --example {name} --lang {args.lang}"
    if pausing:
        out.write(f"\nTip: {command} --no-pause plays it straight through.\n")


def main(argv: Sequence[str] | None = None) -> int:
    _route_realistic_logger_to_a_file()
    args = sys.argv[1:] if argv is None else list(argv)
    return run(args, Terminal.detect(os.environ), sys.stdout, sys.stderr)
