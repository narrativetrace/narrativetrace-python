# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the demo launcher: arguments, terminal policy, styling, pacing, and the entry."""

from __future__ import annotations

import io
import os
import subprocess  # nosec B404 - fixed argv below, used only to run the real demo entry point
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from examples.demo.launcher import (
    EXAMPLES,
    RENDERER_NOTE,
    RULE,
    TREE_MARKER,
    Palette,
    Presenter,
    Terminal,
    color_enabled,
    legend,
    load_example,
    parse_args,
    pick_example,
    pick_lang,
    run,
    should_pause,
    style_line,
    styled_output,
    terminal_pause,
    wiring_table,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ANSI = Palette.ansi()
PLAIN = Palette.plain()
PIPE = Terminal(stdout_tty=False, stdin_tty=False, no_color=None, force_color=None)
TTY = Terminal(stdout_tty=True, stdin_tty=True, no_color=None, force_color=None)


def _scripted(*answers: str) -> Callable[[], str]:
    queue: Iterator[str] = iter(answers)

    def read_line() -> str:
        try:
            return next(queue)
        except StopIteration:
            raise EOFError from None

    return read_line


class TestParseArgs:
    def test_defaults(self) -> None:
        args = parse_args([])
        assert args.example is None
        assert not args.list
        assert not args.classic
        assert not args.no_pause
        # None, not "en": unset is how run() knows --lang was never given, so the interactive
        # picker's language menu (when the example offers one) is still free to choose for itself.
        assert args.lang is None

    def test_every_flag(self) -> None:
        args = parse_args(["-e", "minecraft", "--classic", "--no-pause", "--lang", "es"])
        assert args.example == "minecraft"
        assert args.classic and args.no_pause
        assert args.lang == "es"

    def test_unknown_example_is_rejected(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            parse_args(["--example", "nope"])
        assert exit_info.value.code == 2

    def test_unknown_option_is_rejected(self) -> None:
        with pytest.raises(SystemExit) as exit_info:
            parse_args(["--slow"])
        assert exit_info.value.code == 2

    def test_example_needs_a_value(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--example"])


class TestTerminalPolicy:
    @pytest.mark.parametrize(
        ("no_color", "force_color", "tty", "expected"),
        [
            (None, None, True, True),
            (None, None, False, False),
            (None, "1", False, True),
            ("1", "1", True, False),
            ("1", None, True, False),
            ("", None, True, True),  # NO_COLOR set but empty does not count
            (None, "", False, False),
        ],
    )
    def test_color_enabled(
        self, no_color: str | None, force_color: str | None, tty: bool, expected: bool
    ) -> None:
        assert color_enabled(no_color=no_color, force_color=force_color, stdout_tty=tty) is expected

    @pytest.mark.parametrize(
        ("force_color", "tty", "expected"),
        [(None, True, True), (None, False, False), ("1", False, True), ("", False, False)],
    )
    def test_styled_output(self, force_color: str | None, tty: bool, expected: bool) -> None:
        assert styled_output(force_color=force_color, stdout_tty=tty) is expected

    @pytest.mark.parametrize(
        ("no_pause", "classic", "stdin_tty", "stdout_tty", "expected"),
        [
            (False, False, True, True, True),
            (True, False, True, True, False),
            (False, True, True, True, False),
            (False, False, False, True, False),
            (False, False, True, False, False),
        ],
    )
    def test_should_pause(
        self, no_pause: bool, classic: bool, stdin_tty: bool, stdout_tty: bool, expected: bool
    ) -> None:
        assert (
            should_pause(
                no_pause=no_pause, classic=classic, stdin_tty=stdin_tty, stdout_tty=stdout_tty
            )
            is expected
        )


class TestStyleLine:
    def test_header_is_yellow(self) -> None:
        assert style_line("=== Scenario 1: X ===", ANSI) == "\033[1;33m=== Scenario 1: X ===\033[0m"

    def test_banner_rule_is_yellow(self) -> None:
        assert style_line("=" * 40, ANSI) == "\033[1;33m" + "=" * 40 + "\033[0m"

    def test_entry_keeps_its_indent_and_turns_cyan(self) -> None:
        assert style_line("    → A.b(x: 1)", ANSI) == "    \033[36m→ A.b(x: 1)\033[0m"

    def test_return_is_green_and_exception_is_red(self) -> None:
        assert style_line("← A.b → 1", ANSI) == "\033[32m← A.b → 1\033[0m"
        assert style_line("  !! A.b ✖ E: m", ANSI) == "  \033[1;31m!! A.b ✖ E: m\033[0m"

    def test_known_markers_are_annotated_in_magenta(self) -> None:
        line = style_line(TREE_MARKER, ANSI)
        assert line.startswith("\033[1;35m--- Trace tree — IndentedTextRenderer")
        assert line.endswith("---\033[0m")

    def test_unknown_marker_is_magenta_verbatim(self) -> None:
        assert style_line("--- Clarity ---", ANSI) == "\033[1;35m--- Clarity ---\033[0m"

    def test_ordinary_lines_pass_through(self) -> None:
        assert style_line("├── A.b() → 1 — 0ms", ANSI) == "├── A.b() → 1 — 0ms"
        assert style_line("", ANSI) == ""

    def test_plain_palette_only_annotates(self) -> None:
        assert style_line("→ A.b()", PLAIN) == "→ A.b()"
        assert style_line("--- Prose ---", PLAIN).startswith("--- Prose — ProseRenderer")

    def test_a_line_that_merely_contains_an_arrow_is_not_an_entry(self) -> None:
        assert style_line("returns → later", ANSI) == "returns → later"


class TestPresenter:
    def _present(self, lines: list[str], pause: Callable[[str], bool] | None) -> str:
        out = io.StringIO()
        Presenter(
            out, PLAIN, {"S1": "Wiring: one.", TREE_MARKER: "Renderers: note."}, pause
        ).present(lines)
        return out.getvalue()

    def test_wiring_note_follows_its_header_indented_and_the_rule_precedes_it(self) -> None:
        text = self._present(["=== S1 ===", "x"], None)
        assert text.splitlines() == [RULE, "=== S1 ===", "", "    Wiring: one.", "x"]

    def test_header_without_a_note_prints_nothing_extra(self) -> None:
        text = self._present(["=== S2 ===", "x"], None)
        assert text.splitlines() == [RULE, "=== S2 ===", "x"]

    def test_renderer_note_is_printed_once_at_the_first_tree_marker(self) -> None:
        text = self._present([TREE_MARKER, "a", TREE_MARKER, "b"], None)
        assert text.count("Renderers: note.") == 1
        assert text.splitlines()[1:3] == ["", "    Renderers: note."]

    def test_multi_line_notes_are_indented_line_by_line(self) -> None:
        out = io.StringIO()
        Presenter(out, PLAIN, {"S": "one\ntwo"}, None).present(["=== S ==="])
        assert out.getvalue().splitlines()[3:] == ["    one", "    two"]

    def test_stop_points_come_before_each_scenario_and_once_at_the_end(self) -> None:
        prompts: list[str] = []

        def pause(prompt: str) -> bool:
            prompts.append(prompt)
            return True

        self._present(["=== S1 ===", "x", "=== S2 ===", "y"], pause)
        assert prompts == [
            "[Enter] start the demo   ·   [q] quit",
            "[Enter] next scenario   ·   [q] quit",
            "[Enter] finish",
        ]

    def test_quitting_at_a_stop_point_ends_the_walk(self) -> None:
        answers = iter([True, False])
        text = self._present(["=== S1 ===", "x", "=== S2 ===", "y"], lambda _: next(answers))
        assert "x" in text
        assert "=== S2 ===" not in text
        assert "y" not in text

    def test_clarity_banner_is_one_section_with_its_note_after_the_second_rule(self) -> None:
        prompts: list[str] = []

        def pause(prompt: str) -> bool:
            prompts.append(prompt)
            return True

        out = io.StringIO()
        presenter = Presenter(out, PLAIN, {"CLARITY ANALYSIS REPORT": "Report note."}, pause)
        presenter.present(["=" * 10, "  CLARITY ANALYSIS REPORT", "=" * 10, "body"])
        assert prompts == ["[Enter] start the demo   ·   [q] quit", "[Enter] finish"]
        lines = out.getvalue().splitlines()
        assert lines.index("    Report note.") == lines.index("=" * 10, 2) + 2

    def test_without_pauses_nothing_prompts(self) -> None:
        assert "[Enter]" not in self._present(["=== S1 ===", "x"], None)


class TestTerminalPause:
    def test_enter_continues_and_the_prompt_is_erased_with_ansi(self) -> None:
        out = io.StringIO()
        pause = terminal_pause(out, _scripted(""), ANSI)
        assert pause("[Enter] next") is True
        assert out.getvalue() == "\033[2m   [Enter] next \033[0m\033[1A\033[2K"

    def test_q_quits_case_insensitively(self) -> None:
        assert terminal_pause(io.StringIO(), _scripted("Q"), PLAIN)("p") is False
        assert terminal_pause(io.StringIO(), _scripted(" quit"), PLAIN)("p") is False

    def test_end_of_input_quits(self) -> None:
        assert terminal_pause(io.StringIO(), _scripted(), PLAIN)("p") is False

    def test_plain_palette_ends_the_prompt_line_with_a_newline(self) -> None:
        out = io.StringIO()
        terminal_pause(out, _scripted("x"), PLAIN)("p")
        assert out.getvalue() == "   p \n"


class TestPickExample:
    NAMES = ("ecommerce", "hotel_booking", "minecraft")

    def test_lists_the_examples_and_accepts_a_number(self) -> None:
        out = io.StringIO()
        assert pick_example(self.NAMES, out, _scripted("2")) == "hotel_booking"
        assert out.getvalue().splitlines()[:4] == [
            "Which example? (the trace narrates as the code runs)",
            "  1) ecommerce",
            "  2) hotel_booking",
            "  3) minecraft",
        ]

    def test_accepts_a_name(self) -> None:
        assert pick_example(self.NAMES, io.StringIO(), _scripted("minecraft")) == "minecraft"

    def test_asks_again_after_an_invalid_answer(self) -> None:
        out = io.StringIO()
        assert pick_example(self.NAMES, out, _scripted("0", "4", "x", " 1 ")) == "ecommerce"
        assert out.getvalue().count("#? ") == 4

    def test_end_of_input_gives_up(self) -> None:
        assert pick_example(self.NAMES, io.StringIO(), _scripted()) is None


class TestPickLang:
    LOCALES = ("en", "es", "zh-CN")

    def test_lists_the_locales_and_accepts_a_number(self) -> None:
        out = io.StringIO()
        assert pick_lang(self.LOCALES, out, _scripted("2")) == "es"
        assert out.getvalue().splitlines()[1:4] == ["  1) en", "  2) es", "  3) zh-CN"]

    def test_accepts_a_locale_name(self) -> None:
        assert pick_lang(self.LOCALES, io.StringIO(), _scripted("zh-CN")) == "zh-CN"

    def test_asks_again_after_an_invalid_answer(self) -> None:
        out = io.StringIO()
        assert pick_lang(self.LOCALES, out, _scripted("0", "4", "x", " 1 ")) == "en"
        assert out.getvalue().count("#? ") == 4

    def test_end_of_input_gives_up(self) -> None:
        assert pick_lang(self.LOCALES, io.StringIO(), _scripted()) is None


class TestWiring:
    @pytest.mark.parametrize("name", sorted(EXAMPLES))
    def test_every_example_scenario_has_a_note_and_the_renderer_note_is_present(
        self, name: str
    ) -> None:
        example = load_example(name)
        table = wiring_table(example)
        for scenario in example.scenarios():
            assert table[scenario.title].startswith("Wiring: ")
        assert table[TREE_MARKER] == RENDERER_NOTE

    def test_hotel_booking_explains_its_report_banner(self) -> None:
        assert "CLARITY ANALYSIS REPORT" in wiring_table(load_example("hotel_booking"))

    def test_legend_names_the_three_live_line_shapes(self) -> None:
        text = legend(PLAIN)
        assert "→ method entered" in text
        assert "← returned" in text
        assert "!! exception" in text


class TestRun:
    def test_list_prints_the_example_names(self) -> None:
        out = io.StringIO()
        assert run(["--list"], PIPE, out, io.StringIO()) == 0
        assert out.getvalue().splitlines() == sorted(EXAMPLES)

    def test_lang_with_no_committed_glossary_is_refused_with_a_pointer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("examples.demo.launcher.load_example_glossary", lambda _name: None)
        err = io.StringIO()
        assert run(["--example", "minecraft", "--lang", "es"], PIPE, io.StringIO(), err) == 2
        assert "has no committed glossary.json yet" in err.getvalue()

    def test_lang_unsupported_by_the_example_glossary_is_refused_with_available_locales(
        self,
    ) -> None:
        # hotel_booking's committed glossary has es translations only, not zh-CN.
        err = io.StringIO()
        assert run(["--example", "hotel_booking", "--lang", "zh-CN"], PIPE, io.StringIO(), err) == 2
        assert "available: es" in err.getvalue()

    def test_lang_es_renders_translated_output_for_ecommerce(self) -> None:
        out = io.StringIO()
        exit_code = run(
            ["--example", "ecommerce", "--no-pause", "--lang", "es"], PIPE, out, io.StringIO()
        )
        assert exit_code == 0
        text = out.getvalue()
        assert "=== Scenario 1: Successful Order" in text
        assert "cliente" in text or "pedido" in text

    def test_lang_zh_cn_renders_translated_output_for_ecommerce(self) -> None:
        out = io.StringIO()
        exit_code = run(
            ["--example", "ecommerce", "--no-pause", "--lang", "zh-CN"], PIPE, out, io.StringIO()
        )
        assert exit_code == 0
        assert "顾客" in out.getvalue() or "订单" in out.getvalue()

    def test_lang_and_classic_together_is_refused(self) -> None:
        err = io.StringIO()
        exit_code = run(
            ["--example", "ecommerce", "--classic", "--lang", "es"], PIPE, io.StringIO(), err
        )
        assert exit_code == 2
        assert "no translated variant" in err.getvalue()

    def test_pipe_without_an_example_fails_fast(self) -> None:
        err = io.StringIO()
        assert run([], PIPE, io.StringIO(), err) == 2
        assert err.getvalue() == "stdin is not a terminal: pass --example NAME (see --list)\n"

    def test_pipe_gets_the_verbatim_example_output(self) -> None:
        out = io.StringIO()
        assert run(["--example", "minecraft", "--no-pause"], PIPE, out, io.StringIO()) == 0
        text = out.getvalue()
        assert text.startswith("=== Refactored: Player Joins World ===\n")
        assert "\033[" not in text
        assert "Wiring:" not in text
        assert "--- Trace tree ---" in text

    def test_classic_replays_timestamped_logs_without_styling(self) -> None:
        out = io.StringIO()
        forced = Terminal(stdout_tty=True, stdin_tty=True, no_color=None, force_color="1")
        assert run(["--example", "minecraft", "--classic"], forced, out, io.StringIO()) == 0
        lines = out.getvalue().splitlines()
        assert lines[0].startswith("Classic log format:")
        assert any(" DEBUG [MainThread] narrativetrace - → " in line for line in lines)
        assert "\033[" not in out.getvalue()

    def test_forced_color_on_a_pipe_gets_legend_notes_and_colors_without_pauses(self) -> None:
        out = io.StringIO()
        forced = Terminal(stdout_tty=False, stdin_tty=False, no_color=None, force_color="1")
        assert run(["--example", "minecraft"], forced, out, io.StringIO()) == 0
        text = out.getvalue()
        assert "One recording, many views" in text
        assert "\033[36m→ WorldServer.player_joined" in text
        assert "    Wiring: no container" in text
        assert "[Enter]" not in text
        assert "--classic replays this as timestamped logs." in text
        assert text.rstrip().endswith("see that line on your terminal instead.")

    def test_no_color_on_a_terminal_keeps_the_structure_and_drops_the_colors(self) -> None:
        out = io.StringIO()
        terminal = Terminal(stdout_tty=True, stdin_tty=True, no_color="1", force_color=None)
        assert run(["--example", "minecraft", "--no-pause"], terminal, out, io.StringIO()) == 0
        text = out.getvalue()
        assert "\033[" not in text
        assert "    Wiring: byte for byte" in text
        assert RULE in text

    def test_terminal_run_pauses_and_quits_on_q(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answers = _scripted("", "q")
        monkeypatch.setattr("builtins.input", answers)
        out = io.StringIO()
        assert run(["--example", "minecraft"], TTY, out, io.StringIO()) == 0
        text = out.getvalue()
        assert "=== Refactored: Player Joins World ===" in text
        assert "=== Unrefactored: Player Joins World ===" not in text
        assert "--no-pause plays it straight through." in text

    def test_terminal_picker_is_used_when_no_example_is_given(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # minecraft's own glossary covers "es" (a real but partial curation, TODO item 8), so the
        # picker is followed by a language menu; "en" keeps this scenario's assertions unchanged.
        answers = _scripted("4", "en")
        monkeypatch.setattr("builtins.input", answers)
        out = io.StringIO()
        assert run(["--no-pause"], TTY, out, io.StringIO()) == 0
        assert "Which example?" in out.getvalue()
        assert "=== Refactored: Player Joins World ===" in out.getvalue()

    def test_terminal_picker_end_of_input_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("builtins.input", _scripted())
        assert run([], TTY, io.StringIO(), io.StringIO()) == 2


class TestRunLangMenu:
    """The interactive language menu: offered after the picker, never elsewhere."""

    def test_menu_is_offered_for_a_multi_locale_example_and_the_pick_drives_the_render(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "1" picks ecommerce (sorted first, and the only example with both es and zh-CN).
        monkeypatch.setattr("builtins.input", _scripted("1", "es"))
        out = io.StringIO()
        assert run(["--no-pause"], TTY, out, io.StringIO()) == 0
        text = out.getvalue()
        assert "Which example?" in text
        assert "Which language?" in text
        assert "cliente" in text or "pedido" in text

    def test_menu_selection_by_number_drives_the_render_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("builtins.input", _scripted("1", "3"))  # ecommerce, then zh-CN (#3)
        out = io.StringIO()
        assert run(["--no-pause"], TTY, out, io.StringIO()) == 0
        assert "顾客" in out.getvalue() or "订单" in out.getvalue()

    def test_menu_is_absent_for_an_example_whose_glossary_covers_no_locale(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("examples.demo.launcher.load_example_glossary", lambda _name: None)
        monkeypatch.setattr("builtins.input", _scripted("1"))  # only the example answer needed
        out = io.StringIO()
        assert run(["--no-pause"], TTY, out, io.StringIO()) == 0
        text = out.getvalue()
        assert "Which example?" in text
        assert "Which language?" not in text

    def test_menu_is_absent_when_lang_is_given_explicitly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("builtins.input", _scripted("1"))  # only the example answer needed
        out = io.StringIO()
        assert run(["--no-pause", "--lang", "es"], TTY, out, io.StringIO()) == 0
        text = out.getvalue()
        assert "Which language?" not in text
        assert "cliente" in text or "pedido" in text

    def test_menu_is_absent_off_a_terminal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _unexpected_input() -> str:
            raise AssertionError("input() must not be called off a terminal")

        monkeypatch.setattr("builtins.input", _unexpected_input)
        out = io.StringIO()
        assert run(["--example", "ecommerce", "--no-pause"], PIPE, out, io.StringIO()) == 0
        assert "Which language?" not in out.getvalue()

    def test_menu_is_absent_when_example_is_given_explicitly_even_on_a_terminal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An explicit --example skips the picker; the language menu is a follow-on of the picker
        # flow specifically, not of every terminal run — nothing is scripted to answer with.
        monkeypatch.setattr("builtins.input", _scripted())
        out = io.StringIO()
        assert run(["--example", "ecommerce", "--no-pause"], TTY, out, io.StringIO()) == 0
        text = out.getvalue()
        assert "Which example?" not in text
        assert "Which language?" not in text

    def test_menu_is_absent_under_classic_even_for_a_multi_locale_example(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("builtins.input", _scripted("1"))  # only the example answer needed
        out = io.StringIO()
        assert run(["--classic"], TTY, out, io.StringIO()) == 0
        text = out.getvalue()
        assert "Which example?" in text
        assert "Which language?" not in text
        assert "Classic log format:" in text


class TestMainEntryPoint:
    """`python -m examples.demo` — the real, documented entry point (README's "Try it locally",
    `demo.sh`, and the `poe demo` task all resolve to this exact invocation, per `__main__.py`
    and `pyproject.toml`'s `[tool.poe.tasks.demo]`) — run as a genuine subprocess. Every test
    above this class calls `run()` in-process with a fake `Terminal`/`io.StringIO()`, so none of
    them exercises `main()`, `Terminal.detect(os.environ)`, or this module's own `sys.exit`/argv
    wiring — exactly the "internals only, never the documented incantation itself" gap this
    class closes, the same way `test_add_middleware_matches_the_documented_fastapi_recipe`
    (`packages/narrativetrace-asgi/tests/test_documented_recipes.py`) and
    `test_output_matches_the_documented_sixty_seconds_recipe`
    (`packages/narrativetrace-pytest/tests/test_plugin.py`) close it for their own paths.

    A subprocess with its stdout piped (never a TTY) takes `run()`'s plain, unstyled branch —
    no pacing sleep, no `input()` — so these run in well under a second despite being real
    process launches.
    """

    @staticmethod
    def _run_demo(*args: str, timeout: float = 60.0) -> subprocess.CompletedProcess[str]:
        """Runs the real entry point with an explicit UTF-8 encoding for the captured pipes —
        the demo's output uses non-ASCII glyphs (→, ⑂, —), and `subprocess.run(text=True)`
        otherwise decodes with `locale.getpreferredencoding()`, which reads as plain ASCII in a
        minimal/POSIX-locale CI environment and raises `UnicodeDecodeError` on the first such
        byte — the environment-dependence class of trap the family's release retrospective
        warns about, not a real crash in the demo itself. `PYTHONIOENCODING` pins the child
        process's own stdout encoding for the same reason, independent of its ambient locale."""
        return subprocess.run(  # nosec B603 - fixed argv, no shell, no untrusted input
            [sys.executable, "-m", "examples.demo", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=timeout,
            check=False,
        )

    def test_runs_the_ecommerce_example_end_to_end(self) -> None:
        result = self._run_demo("--example", "ecommerce", "--no-pause")

        assert result.returncode == 0, result.stderr
        assert "OrderService.place_order" in result.stdout
        assert "card_token: [REDACTED]" in result.stdout

    def test_list_prints_every_example_name(self) -> None:
        result = self._run_demo("--list", timeout=30.0)

        assert result.returncode == 0
        assert set(result.stdout.split()) == set(EXAMPLES)

    def test_an_unknown_example_name_is_refused_before_anything_runs(self) -> None:
        result = self._run_demo("--example", "not-a-real-example", timeout=30.0)

        assert result.returncode != 0
        assert "OrderService" not in result.stdout
