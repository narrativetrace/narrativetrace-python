# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the shared example scaffolding: scenarios, sections, and the live stream."""

from __future__ import annotations

import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import pytest

from examples.tour import (
    LIVE_LOGGER_NAME,
    MARKDOWN,
    PLANTUML,
    DemoFormatter,
    Scenario,
    narrated_run,
    walk,
)
from narrativetrace import (
    ContextVarNarrativeContext,
    ForkJoinGroup,
    NarrativeContext,
    TraceTree,
    trace_object,
)


def _capture_nothing(context: NarrativeContext) -> TraceTree:
    return context.capture_trace()


class TestScenarioGuards:
    def test_blank_wiring_note_is_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"\Awiring note must not be blank\Z"):
            Scenario("Scenario 1", "   ", _capture_nothing)

    def test_blank_title_is_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"\Atitle must not be blank\Z"):
            Scenario("", "Wiring: plain trace_object.", _capture_nothing)

    def test_title_may_not_carry_the_header_markers(self) -> None:
        with pytest.raises(ValueError, match=r"\Atitle must not contain '==='\Z"):
            Scenario("=== Scenario ===", "Wiring: plain trace_object.", _capture_nothing)

    def test_valid_scenario_keeps_its_fields(self) -> None:
        scenario = Scenario("Scenario 1: Happy path", "Wiring: trace_object.", _capture_nothing)
        assert scenario.title == "Scenario 1: Happy path"
        assert scenario.wiring == "Wiring: trace_object."
        assert scenario.run(ContextVarNarrativeContext()).is_empty


class _Greeter:
    def greet(self, name: str) -> str:
        return f"hello {name}"


def _capture_greeting(context: NarrativeContext) -> TraceTree:
    trace_object(_Greeter(), context).greet("world")
    return context.capture_trace()


def _greeting_scenario(**overrides: object) -> Scenario:
    fields: dict[str, object] = {
        "title": "Scenario 1: Greeting",
        "wiring": "Wiring: trace_object around _Greeter.",
        "run": _capture_greeting,
    }
    fields.update(overrides)
    return Scenario(**fields)  # type: ignore[arg-type]


class TestWalk:
    def test_prints_the_header_and_the_default_sections_in_order(self) -> None:
        out = io.StringIO()
        walk([_greeting_scenario()], out, ContextVarNarrativeContext())
        lines = out.getvalue().splitlines()
        assert lines[0] == "=== Scenario 1: Greeting ==="
        markers = [line for line in lines if line.startswith("--- ")]
        assert markers == ["--- Trace tree ---", "--- Prose ---", "--- Mermaid ---"]
        assert '_Greeter.greet(name: "world") → "hello world"' in out.getvalue()
        assert "sequenceDiagram" in out.getvalue()

    def test_returns_each_scenario_with_its_captured_tree(self) -> None:
        captured = walk([_greeting_scenario()], io.StringIO(), ContextVarNarrativeContext())
        assert [scenario.title for scenario, _ in captured] == ["Scenario 1: Greeting"]
        assert captured[0][1].roots[0].signature.method_name == "greet"

    def test_each_scenario_starts_from_a_reset_context(self) -> None:
        second = _greeting_scenario(title="Scenario 2: Greeting again")
        captured = walk([_greeting_scenario(), second], io.StringIO(), ContextVarNarrativeContext())
        assert [len(tree.roots) for _, tree in captured] == [1, 1]

    def test_later_headers_are_preceded_by_a_blank_line(self) -> None:
        out = io.StringIO()
        second = _greeting_scenario(title="Scenario 2: Greeting again")
        walk([_greeting_scenario(), second], out, ContextVarNarrativeContext())
        lines = out.getvalue().splitlines()
        index = lines.index("=== Scenario 2: Greeting again ===")
        assert lines[index - 1] == ""

    def test_explicit_sections_replace_the_defaults(self) -> None:
        out = io.StringIO()
        scenario = _greeting_scenario(sections=(MARKDOWN, PLANTUML))
        walk([scenario], out, ContextVarNarrativeContext())
        markers = [line for line in out.getvalue().splitlines() if line.startswith("--- ")]
        assert markers == ["--- Markdown ---", "--- PlantUML ---"]
        assert "- **_Greeter.greet**" in out.getvalue()
        assert "@startuml" in out.getvalue()

    def test_intro_lines_follow_the_header_and_notice_lines_follow_the_tree(self) -> None:
        out = io.StringIO()
        scenario = _greeting_scenario(intro=("Read the tree first.",), notice=("^ Notice this.",))
        walk([scenario], out, ContextVarNarrativeContext())
        lines = out.getvalue().splitlines()
        assert lines[1:3] == ["", "  Read the tree first."]
        tree_marker = lines.index("--- Trace tree ---")
        assert "  ^ Notice this." in lines[tree_marker:]
        assert lines.index("  ^ Notice this.") < lines.index("--- Prose ---")

    def test_walking_no_scenarios_prints_nothing(self) -> None:
        out = io.StringIO()
        assert walk([], out, ContextVarNarrativeContext()) == []
        assert out.getvalue() == ""


class _Register:
    def __init__(self, context: NarrativeContext) -> None:
        self._greeter = trace_object(_Greeter(), context)

    def welcome(self, name: str) -> str:
        return self._greeter.greet(name).upper()

    def reject(self, name: str) -> str:
        raise PermissionError(f"{name} is banned")


def _demo_record(message: str, **fields: str) -> logging.LogRecord:
    record = logging.LogRecord("t", logging.DEBUG, "", 0, message, (), None)
    record.__dict__.update(fields)
    return record


class TestDemoFormatter:
    def test_entry_keeps_its_shape_and_indents_by_depth(self) -> None:
        formatter = DemoFormatter()
        formatter.format(
            _demo_record("→ A.a()", **{"nt.depth": "1", "nt.class": "A", "nt.method": "a"})
        )
        record = _demo_record("→ A.b(x: 1)", **{"nt.depth": "3", "nt.class": "A", "nt.method": "b"})
        assert formatter.format(record) == "    → A.b(x: 1)"

    def test_return_borrows_the_name_of_its_entry_by_span_id(self) -> None:
        formatter = DemoFormatter()
        formatter.format(
            _demo_record(
                "→ A.b()", **{"nt.depth": "1", "nt.class": "A", "nt.method": "b"}, spanId="s1"
            )
        )
        assert formatter.format(
            _demo_record("← returned: 42", **{"nt.depth": "0"}, spanId="s1")
        ) == ("← A.b → 42")

    def test_exception_line_marks_the_failure_with_a_cross(self) -> None:
        formatter = DemoFormatter()
        formatter.format(
            _demo_record("→ A.a()", **{"nt.depth": "1", "nt.class": "A", "nt.method": "a"})
        )
        formatter.format(
            _demo_record(
                "→ A.b()", **{"nt.depth": "2", "nt.class": "A", "nt.method": "b"}, spanId="s2"
            )
        )
        line = formatter.format(
            _demo_record("!! ValueError: bad [ctx]", **{"nt.depth": "1"}, spanId="s2")
        )
        assert line == "  !! A.b ✖ ValueError: bad [ctx]"

    def test_exit_without_a_known_entry_falls_back_to_a_placeholder_name(self) -> None:
        line = DemoFormatter().format(
            _demo_record("← returned: 1", **{"nt.depth": "0"}, spanId="x")
        )
        assert line == "← ? → 1"

    def test_indentation_is_relative_to_the_first_entry_of_the_stream(self) -> None:
        formatter = DemoFormatter()
        outer = formatter.format(
            _demo_record(
                "→ A.b()", **{"nt.depth": "3", "nt.class": "A", "nt.method": "b"}, spanId="o"
            )
        )
        inner = formatter.format(
            _demo_record(
                "→ A.c()", **{"nt.depth": "4", "nt.class": "A", "nt.method": "c"}, spanId="i"
            )
        )
        assert (outer, inner) == ("→ A.b()", "  → A.c()")
        assert formatter.format(_demo_record("← returned: 1", **{"nt.depth": "3"}, spanId="i")) == (
            "  ← A.c → 1"
        )

    def test_lines_without_depth_pass_through_unindented(self) -> None:
        assert (
            DemoFormatter().format(_demo_record("⑂ fork group created")) == "⑂ fork group created"
        )

    def test_a_name_is_consumed_by_its_exit(self) -> None:
        formatter = DemoFormatter()
        formatter.format(
            _demo_record(
                "→ A.b()", **{"nt.depth": "1", "nt.class": "A", "nt.method": "b"}, spanId="s"
            )
        )
        formatter.format(_demo_record("← returned: 1", **{"nt.depth": "0"}, spanId="s"))
        assert formatter.format(_demo_record("← returned: 2", **{"nt.depth": "0"}, spanId="s")) == (
            "← ? → 2"
        )


class TestNarratedRun:
    def test_streams_entry_and_return_lines_indented_by_depth(self) -> None:
        out = io.StringIO()
        with narrated_run(out) as context:
            trace_object(_Register(context), context).welcome("world")
        assert out.getvalue().splitlines() == [
            '→ _Register.welcome(name: "world")',
            '  → _Greeter.greet(name: "world")',
            '  ← _Greeter.greet → "hello world"',
            '← _Register.welcome → "HELLO WORLD"',
        ]

    def test_streams_an_exception_line_with_the_error_and_message(self) -> None:
        out = io.StringIO()
        with narrated_run(out) as context:
            register = trace_object(_Register(context), context)
            with pytest.raises(PermissionError):
                register.reject("mallory")
        assert out.getvalue().splitlines() == [
            '→ _Register.reject(name: "mallory")',
            "!! _Register.reject ✖ PermissionError: mallory is banned",
        ]

    def test_classic_mode_uses_the_timestamped_log_format(self) -> None:
        out = io.StringIO()
        with narrated_run(out, classic=True) as context:
            trace_object(_Greeter(), context).greet("world")
        lines = out.getvalue().splitlines()
        stamp = (
            r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} DEBUG \[MainThread\] narrativetrace\.examples - "
        )
        assert re.fullmatch(stamp + re.escape('→ _Greeter.greet(name: "world")'), lines[0])
        assert re.fullmatch(stamp + re.escape('← returned: "hello world"'), lines[1])

    def test_the_captured_tree_is_still_available_after_the_stream(self) -> None:
        with narrated_run(io.StringIO()) as context:
            trace_object(_Register(context), context).welcome("world")
            tree = context.capture_trace()
        assert [n.signature.method_name for n in tree.roots] == ["welcome"]
        assert [n.signature.method_name for n in tree.roots[0].children] == ["greet"]

    def test_grafted_fork_children_are_narrated_exactly_once(self) -> None:
        out = io.StringIO()
        with narrated_run(out) as context:
            greeter = trace_object(_Greeter(), context)
            fork = ForkJoinGroup.create(context)
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(fork.wrap(lambda: greeter.greet("a"))).result()
                pool.submit(fork.wrap(lambda: greeter.greet("b"))).result()
            fork.merge()
            assert len(context.capture_trace().roots) == 2
        entries = [line for line in out.getvalue().splitlines() if "→ _Greeter.greet(" in line]
        assert len(entries) == 2

    def test_nothing_leaks_into_the_stdlib_logger_registry(self) -> None:
        with narrated_run(io.StringIO()) as context:
            trace_object(_Greeter(), context).greet("world")
        assert LIVE_LOGGER_NAME not in logging.Logger.manager.loggerDict
