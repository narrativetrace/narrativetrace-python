# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Integration tests for the narrativetrace pytest plugin via the pytester fixture."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_off_level_captures_nothing(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_LEVEL", "OFF")
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self, x): return x * 2

        def test_it(narrative_trace):
            svc = trace_object(Svc(), narrative_trace)
            assert svc.run(3) == 6
            assert narrative_trace.capture_trace().is_empty
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_garbage_level_degrades_to_detail(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_LEVEL", "nonsense")
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self, x): return x * 2

        def test_it(narrative_trace):
            svc = trace_object(Svc(), narrative_trace)
            svc.run(3)
            tree = narrative_trace.capture_trace()
            assert not tree.is_empty
            # DETAIL retains parameter values
            assert tree.roots[0].signature.parameters[0].rendered_value == "3"
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)


def test_output_writes_artifact(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self, x): return x * 2

        def test_place_order(narrative_trace):
            svc = trace_object(Svc(), narrative_trace)
            svc.run(3)
        """
    )
    result = pytester.runpytest_subprocess("-s")
    result.assert_outcomes(passed=1)
    trace_files = list(out_dir.rglob("test_place_order.md"))
    assert len(trace_files) == 1
    # PY12: a non-empty suite also aggregates a clarity report + results file.
    assert (out_dir / "clarity-results.json").exists()
    assert (out_dir / "clarity-report.md").exists()
    result.stdout.fnmatch_lines(["*Trace written:*"])


def test_output_is_on_by_default_with_no_configuration_at_all(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ruling this default flip exists for: wrapping a call with the fixture must produce a
    trace artifact without an adopter also having to discover and set an enable flag."""
    for name in ("NARRATIVETRACE_OUTPUT", "NARRATIVETRACE_OUTPUT_DIR"):
        monkeypatch.delenv(name, raising=False)
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self, x): return x * 2

        def test_place_order(narrative_trace):
            svc = trace_object(Svc(), narrative_trace)
            svc.run(3)
        """
    )
    result = pytester.runpytest_subprocess("-s")
    result.assert_outcomes(passed=1)
    trace_files = list((pytester.path / "narrative-traces").rglob("test_place_order.md"))
    assert len(trace_files) == 1


def test_output_false_writes_nothing(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "false")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self, x): return x * 2

        def test_place_order(narrative_trace):
            svc = trace_object(Svc(), narrative_trace)
            svc.run(3)
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    assert not out_dir.exists() or list(out_dir.rglob("*")) == []


def test_output_zero_writes_nothing(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "0")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self, x): return x * 2

        def test_place_order(narrative_trace):
            svc = trace_object(Svc(), narrative_trace)
            svc.run(3)
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    assert not out_dir.exists() or list(out_dir.rglob("*")) == []


@pytest.mark.parametrize("spelling", ["no", "off", "FALSE", "OFF", "No"])
def test_output_opt_out_accepts_case_insensitive_falsy_spellings(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", spelling)
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self, x): return x * 2

        def test_place_order(narrative_trace):
            svc = trace_object(Svc(), narrative_trace)
            svc.run(3)
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    assert not out_dir.exists() or list(out_dir.rglob("*")) == []


def test_output_explicit_true_still_writes_artifacts(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "true")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self, x): return x * 2

        def test_place_order(narrative_trace):
            svc = trace_object(Svc(), narrative_trace)
            svc.run(3)
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    assert list(out_dir.rglob("test_place_order.md"))


def test_config_file_output_false_opts_out_without_any_environment_variable(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The config-file spelling of the same opt-out, exercised the way an adopter without env
    control (e.g. a shared CI config) would use it."""
    for name in ("NARRATIVETRACE_OUTPUT", "NARRATIVETRACE_OUTPUT_DIR"):
        monkeypatch.delenv(name, raising=False)
    (pytester.path / "narrativetrace.toml").write_text("output = false\n", encoding="utf-8")
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self, x): return x * 2

        def test_place_order(narrative_trace):
            svc = trace_object(Svc(), narrative_trace)
            svc.run(3)
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    out_dir = pytester.path / "narrative-traces"
    assert not out_dir.exists() or list(out_dir.rglob("*")) == []


def test_output_matches_the_documented_first_10_minutes_recipe(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`documentation/first-10-minutes.md` steps 1-5 / README "Add it to one test", run through
    the real installed plugin (a `pytester_subprocess` run, so real pytest11 auto-registration —
    never an in-process fixture call) and checked against the EXACT Markdown the docs promise —
    entry_point, error_count, and the call-flow line — not just "a file exists" the way
    `test_output_writes_artifact` above (deliberately, per its own docstring) only checks. The
    other documented recipes (`trace_object`/`ContextVarNarrativeContext`/`MarkdownRenderer`
    chained through the public API, `narrativetrace-asgi`'s `add_middleware`/`attach_traceparent`,
    the `poe demo` entry point) each have their own dedicated real-path test — see
    `packages/narrativetrace-asgi/tests/test_documented_recipes.py` and
    `examples/demo/test_launcher.py::TestMainEntryPoint`.
    """
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        order_service="""
        class OrderService:
            def place_order(self, customer_id, product_id, quantity):
                return f"ORD-{customer_id}-{product_id}-{quantity}"
        """
    )
    pytester.makepyfile(
        test_order_service="""
        from narrativetrace import trace_object

        from order_service import OrderService


        class TestOrderService:
            def test_customer_places_order(self, narrative_trace):
                service = trace_object(OrderService(), narrative_trace)
                service.place_order("C-1234", "SKU-KB", 2)
        """
    )
    result = pytester.runpytest_subprocess("-s")
    result.assert_outcomes(passed=1)

    trace_file = out_dir / "traces" / "TestOrderService" / "test_customer_places_order.md"
    content = trace_file.read_text(encoding="utf-8")
    assert "type: trace" in content
    assert "scenario: Test customer places order" in content
    assert "entry_point: OrderService.place_order" in content
    assert "method_count: 1" in content
    assert "error_count: 0" in content
    assert "**Duration:** " in content and "**Result:** PASSED" in content
    assert (
        '**OrderService.place_order**(customer_id: `"C-1234"`, product_id: `"SKU-KB"`, '
        'quantity: `2`) → `"ORD-C-1234-SKU-KB-2"`'
    ) in content
    result.stdout.fnmatch_lines(
        [
            "*Scenario: Test customer places order*",
            "*Execution trace:*",
            "*Trace written:*",
        ]
    )


def test_empty_trace_writes_no_files(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        """
        def test_nothing(narrative_trace):
            assert True
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    assert not out_dir.exists() or list(out_dir.rglob("*")) == []


def test_failure_prints_execution_trace(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NARRATIVETRACE_LEVEL", raising=False)
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self): return "value"

        def test_boom(narrative_trace):
            svc = trace_object(Svc(), narrative_trace)
            svc.run()
            assert False, "boom"
        """
    )
    result = pytester.runpytest_subprocess("-s")
    result.assert_outcomes(failed=1)


def test_suite_footer_printed(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        def test_a(narrative_trace): pass
        def test_b(narrative_trace): pass
        """
    )
    result = pytester.runpytest_subprocess()
    result.stdout.fnmatch_lines(["*scenarios recorded*"])


def test_a_suite_where_every_test_fails_still_prints_the_footer(
    pytester: pytest.Pytester,
) -> None:
    """Mirrors a Java bug-hunt finding: JUnit4's ``@ClassRule`` wraps the whole class in one
    ``Statement``, so a class-level report was silently skipped when that ``Statement.evaluate()``
    threw (fixed by moving ``afterAll()`` into a ``finally``). Pytest has no equivalent seam —
    ``pytest_terminal_summary`` runs once per session regardless of any test's outcome, and each
    test's own ``narrative_trace`` fixture teardown (a plain ``yield``-based fixture, unconditional
    finalizer) accumulates into the suite footer before the test's failure is even reported —
    confirmed here with every test in the file failing, not just one.
    """
    pytester.makepyfile(
        """
        def test_a(narrative_trace):
            assert False, "first failure"

        def test_b(narrative_trace):
            assert False, "second failure"
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(failed=2)
    result.stdout.fnmatch_lines(["*2 scenarios recorded*"])


def test_markdown_writes_json_companion(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self): return "ok"

        def test_run(narrative_trace):
            trace_object(Svc(), narrative_trace).run()
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    # Not rglob("*.json") — the suite-level clarity-results.json would satisfy that on its own.
    assert (out_dir / "traces" / "test_markdown_writes_json_companion" / "test_run.json").exists()


def test_json_companion_carries_the_scenario_document_header(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self): return "ok"

        def test_place_order(narrative_trace):
            trace_object(Svc(), narrative_trace).run()
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    companion = out_dir / "traces" / "test_json_companion_carries_the_scenario_document_header"
    document = json.loads((companion / "test_place_order.json").read_text(encoding="utf-8"))
    assert document["version"] == "1.0"
    assert document["scenario"]["name"] == "Test place order"


def test_config_file_enables_output_without_any_environment_variable(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("NARRATIVETRACE_OUTPUT", "NARRATIVETRACE_OUTPUT_DIR", "NARRATIVETRACE_FORMAT"):
        monkeypatch.delenv(name, raising=False)
    (pytester.path / "narrativetrace.toml").write_text(
        'output = true\noutput_dir = "from-file"\nlevel = "DETAIL"\n', encoding="utf-8"
    )
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self): return "ok"

        def test_run(narrative_trace):
            trace_object(Svc(), narrative_trace).run()
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    written = pytester.path / "from-file" / "traces"
    assert written.is_dir()


def test_environment_overrides_the_config_file(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(pytester.path / "from-env"))
    (pytester.path / "narrativetrace.toml").write_text(
        'output = true\noutput_dir = "from-file"\n', encoding="utf-8"
    )
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self): return "ok"

        def test_run(narrative_trace):
            trace_object(Svc(), narrative_trace).run()
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    assert (pytester.path / "from-env" / "traces").is_dir()
    assert not (pytester.path / "from-file").exists()


def test_two_config_sources_in_one_directory_fail_the_run(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NARRATIVETRACE_OUTPUT", raising=False)
    (pytester.path / "narrativetrace.toml").write_text("output = true\n", encoding="utf-8")
    (pytester.path / "pyproject.toml").write_text(
        "[tool.narrativetrace]\noutput = false\n", encoding="utf-8"
    )
    pytester.makepyfile(
        """
        def test_run(narrative_trace):
            pass
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*DuplicateConfigurationError*"])


def test_scenario_result_uses_the_product_vocabulary(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self): return "ok"

        def test_passes(narrative_trace):
            trace_object(Svc(), narrative_trace).run()

        def test_fails(narrative_trace):
            trace_object(Svc(), narrative_trace).run()
            raise AssertionError("boom")
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1, failed=1)
    traces = out_dir / "traces" / "test_scenario_result_uses_the_product_vocabulary"
    # The JSON artifact carries the schema-legal spelling; only the Markdown caption says PASSED.
    assert (
        json.loads((traces / "test_passes.json").read_text(encoding="utf-8"))["scenario"]["result"]
        == "success"
    )
    assert (
        json.loads((traces / "test_fails.json").read_text(encoding="utf-8"))["scenario"]["result"]
        == "error"
    )
    assert "**Result:** FAILED" in (traces / "test_fails.md").read_text(encoding="utf-8")
    assert "**Result:** PASSED" in (traces / "test_passes.md").read_text(encoding="utf-8")


def test_plantuml_format_writes_a_plantuml_trace(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    monkeypatch.setenv("NARRATIVETRACE_FORMAT", "plantuml")
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class Svc:
            def run(self): return "ok"

        def test_run(narrative_trace):
            trace_object(Svc(), narrative_trace).run()
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    written = list(out_dir.rglob("*.puml"))
    assert written
    assert written[0].read_text(encoding="utf-8").startswith("@startuml")


def test_footer_shows_clarity_split(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class OrderService:
            def place_order(self): return "ok"

        def test_a(narrative_trace):
            trace_object(OrderService(), narrative_trace).place_order()
        """
    )
    result = pytester.runpytest_subprocess()
    result.stdout.fnmatch_lines(["*Clarity:*high*moderate*low*"])


def test_footer_omits_the_loss_line_when_nothing_was_lost(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class OrderService:
            def place_order(self): return "ok"

        def test_a(narrative_trace):
            trace_object(OrderService(), narrative_trace).place_order()
        """
    )
    result = pytester.runpytest_subprocess()
    assert "Incomplete:" not in result.stdout.str()


def test_footer_names_what_the_suite_lost(pytester: pytest.Pytester) -> None:
    """A refusal is a bounded-resource condition, forced here rather than waited for.

    Ten thousand adopted spans is the real trigger; lowering the ceiling on the fixture's own
    stack reaches the same state deterministically and proves the whole chain — stack counters
    to context reading to suite footer.
    """
    pytester.makepyfile(
        """
        from narrativetrace.ids import SpanId
        from narrativetrace.trace_object import trace_object

        class OrderService:
            def place_order(self): return "ok"

        def test_a(narrative_trace):
            trace_object(OrderService(), narrative_trace).place_order()
            stack = narrative_trace._get_stack()
            stack.max_adopted_spans = 0
            stack.adopt({SpanId.generate(), SpanId.generate()})
        """
    )
    result = pytester.runpytest_subprocess()
    result.stdout.fnmatch_lines(["*Incomplete: 1 async scope not adopted (cap), 2 spans*"])


def test_clarity_results_json_has_one_entry_per_traced_test(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class OrderService:
            def place_order(self): return "ok"

        def test_one(narrative_trace):
            trace_object(OrderService(), narrative_trace).place_order()

        def test_two(narrative_trace):
            trace_object(OrderService(), narrative_trace).place_order()
        """
    )
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)
    data = json.loads((out_dir / "clarity-results.json").read_text(encoding="utf-8"))
    assert data["version"] == "1.0"
    assert len(data["scenarios"]) == 2  # one entry per traced test, duplicates retained


_TRADING_GLOSSARY = """{
  "schemaVersion": 1,
  "contexts": {"trading": {"packages": ["acme.trading"]}},
  "terms": [
    {
      "term": "fold tranche",
      "context": "trading",
      "kind": "verb-phrase",
      "status": "curated",
      "firstSeen": "2020-01-01"
    }
  ]
}"""

_TRANCHE_TEST = """
from narrativetrace.trace_object import trace_object

class TrancheService:
    def foldTranche(self, tranche): return tranche

def test_folds_a_tranche(narrative_trace):
    trace_object(TrancheService(), narrative_trace).foldTranche("t-1")
"""


def _clarity_score(pytester: pytest.Pytester, out_dir: Path, glossary_dir: Path | None) -> float:
    if glossary_dir is not None:
        (glossary_dir / "glossary.json").write_text(_TRADING_GLOSSARY, encoding="utf-8")
    pytester.makepyfile(_TRANCHE_TEST)
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    report = json.loads((out_dir / "clarity-results.json").read_text(encoding="utf-8"))
    return float(report["scenarios"][0]["overallScore"])


def test_committed_glossary_raises_the_suite_clarity_score(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(pytester.path / "plain"))
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(pytester.path))
    without = _clarity_score(pytester, pytester.path / "plain", None)

    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(pytester.path / "glossed"))
    with_glossary = _clarity_score(pytester, pytester.path / "glossed", pytester.path)

    assert with_glossary > without


def test_malformed_committed_glossary_degrades_instead_of_failing_the_suite(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(pytester.path / "nt-out"))
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(pytester.path))
    (pytester.path / "glossary.json").write_text("{ not json", encoding="utf-8")
    pytester.makepyfile(_TRANCHE_TEST)

    result = pytester.runpytest_subprocess("-s")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*could not be read*built-in dictionaries only*"])


# --------------------------------------------------------------------------- #
# Glossary harvest hook (Phase 5): opt-in by glossary.json presence           #
# --------------------------------------------------------------------------- #
def test_no_committed_glossary_and_no_override_never_harvests(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(pytester.path))
    pytester.makepyfile(_TRANCHE_TEST)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)
    assert not (pytester.path / "glossary.json").is_file()
    assert "Vocabulary:" not in result.stdout.str()


def test_narrativetrace_glossary_on_forces_a_first_harvest(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(pytester.path))
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY", "on")
    pytester.makepyfile(_TRANCHE_TEST)

    result = pytester.runpytest_subprocess("-s")

    result.assert_outcomes(passed=1)
    assert (pytester.path / "glossary.json").is_file()
    result.stdout.fnmatch_lines(["*Vocabulary: * new terms harvested*"])


def test_a_committed_glossary_opts_a_suite_into_harvesting_by_default(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(pytester.path))
    (pytester.path / "glossary.json").write_text(
        '{"schemaVersion": 1, "contexts": {}, "terms": []}', encoding="utf-8"
    )
    pytester.makepyfile(_TRANCHE_TEST)

    result = pytester.runpytest_subprocess("-s")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*Vocabulary: * new terms harvested*"])
    merged = json.loads((pytester.path / "glossary.json").read_text(encoding="utf-8"))
    assert merged["terms"]


def test_narrativetrace_glossary_off_disables_even_with_a_committed_glossary(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(pytester.path))
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY", "off")
    before = '{"schemaVersion": 1, "contexts": {}, "terms": []}'
    (pytester.path / "glossary.json").write_text(before, encoding="utf-8")
    pytester.makepyfile(_TRANCHE_TEST)

    result = pytester.runpytest_subprocess("-s")

    result.assert_outcomes(passed=1)
    assert "Vocabulary:" not in result.stdout.str()
    assert (pytester.path / "glossary.json").read_text(encoding="utf-8") == before


def test_a_deprecated_alias_is_reported_in_the_footer(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(pytester.path))
    # A pytester-generated test module has no dotted path any declared bounded context could
    # own, so every real harvest from it files under "_unassigned" — matching context here, not
    # a declared one, is what makes the alias actually resolvable (unlike clarity scoring, which
    # flattens every context and would not have caught this).
    glossary = """{
      "schemaVersion": 1,
      "contexts": {"_unassigned": {"packages": []}},
      "terms": [
        {
          "term": "fold tranche",
          "context": "_unassigned",
          "kind": "verb-phrase",
          "status": "curated",
          "synonyms": [{"alias": "collapse tranche"}],
          "firstSeen": "2020-01-01"
        }
      ]
    }"""
    (pytester.path / "glossary.json").write_text(glossary, encoding="utf-8")
    pytester.makepyfile(
        """
        from narrativetrace.trace_object import trace_object

        class TrancheService:
            def collapseTranche(self, tranche): return tranche

        def test_collapses_a_tranche(narrative_trace):
            trace_object(TrancheService(), narrative_trace).collapseTranche("t-1")
        """
    )

    result = pytester.runpytest_subprocess("-s")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*1 deprecated synonyms in use*"])
    result.stdout.fnmatch_lines(["*fold tranche*"])


def test_harvesting_writes_a_usage_report_alongside_clarity_output(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    out_dir = pytester.path / "nt-out"
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT", "1")
    monkeypatch.setenv("NARRATIVETRACE_OUTPUT_DIR", str(out_dir))
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(pytester.path))
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY", "on")
    pytester.makepyfile(_TRANCHE_TEST)

    result = pytester.runpytest_subprocess()

    result.assert_outcomes(passed=1)
    report = json.loads((out_dir / "glossary-usage.json").read_text(encoding="utf-8"))
    assert report["newTerms"]


def test_a_malformed_committed_glossary_skips_harvesting_without_failing_the_suite(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(pytester.path))
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY", "on")
    (pytester.path / "glossary.json").write_text("{ not json", encoding="utf-8")
    pytester.makepyfile(_TRANCHE_TEST)

    result = pytester.runpytest_subprocess("-s")

    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*glossary harvest failed, skipped*"])
