# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The one test behind documentation/first-10-minutes.md's "See a trace in 60 seconds" page.

This directory *is* the tutorial (rule 8, docs as tests):
``main.py`` is byte-identical to the page's "The program" code block, and ``main_with_logger.py``
is what the page's "Send it to your logger" diff turns it into -- both run exactly as the page's
"Run it" step says (``uv run main.py``). Neither is exercised by import: each runs as a real,
separate ``python`` process, the same way a reader's shell runs them, so nothing here touches the
other's global state (each script's own ``LoggingTraceConsumer`` -- never two on one event stream,
see ``narrativetrace.logging_bridge`` -- and ``main_with_logger.py``'s ``logging.basicConfig``
call, which would otherwise leak a stdout handler onto the root logger for the rest of this suite's
process).

The two scripts' captured stdout is saved under ``build/`` (git-ignored, regenerated every run --
see documentation/what-to-commit.md) for ``scripts/snippet_check.py`` to embed as the page's two
"Run it" output blocks, ``mask=duration`` neutralizing the one thing a real run cannot pin down.

The plugin half: ``narrativetrace-pytest``'s ``narrative_trace`` fixture is this repo's own "test
integration," and output through it is on by default (ruled 2026-09-11) -- exactly what the page's
postscript never has to mention setting up. This repo's own outer test session disables that
plugin (see ``conftest.py`` / ``pyproject.toml``'s ``addopts``, needed so pytest-cov's tracer sees
``narrativetrace`` imports first), so a real exercise of it always runs in an isolated subprocess --
the same ``pytester`` technique ``packages/narrativetrace-pytest/tests/test_plugin.py`` uses --
driving the identical ``OrderService.place_order`` call through the fixture and checking the
artifact it writes.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from examples.sixty_seconds.tutorial_artifacts import write_artifacts

_HERE = Path(__file__).parent

_TRACE_LINE = re.compile(
    r'^OrderService\.place_order\(customer_id: "cust-1", product_id: "prod-42", quantity: 3\) '
    r'→ "ORD-cust-1-prod-42-3" — \d+(\.\d+)?ms$'
)


def _order_service_source() -> str:
    """``main.py``'s ``OrderService`` class, lifted through the AST (never retyped, and immune
    to reflowing the rest of the file) for the pytester fixture below."""
    tree = ast.parse((_HERE / "main.py").read_text(encoding="utf-8"))
    class_def = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    return ast.unparse(class_def)


def test_see_a_trace_in_60_seconds(pytester: pytest.Pytester) -> None:
    """Runs the tutorial call through the real traced proxy three ways, once per page section:

    - the plain script ("The program" / "Run it"), captured and saved for the snippet embed;
    - its logger-wired sibling ("Send it to your logger"), same treatment;
    - the identical call again, through ``narrativetrace-pytest``'s fixture in an isolated
      subprocess, proving the runtime's own test integration writes the artifact by default.
    """
    plain, with_logger = write_artifacts()

    plain_lines = plain.splitlines()
    assert len(plain_lines) == 1
    assert _TRACE_LINE.match(plain_lines[0])

    logger_lines = with_logger.splitlines()
    assert len(logger_lines) == 3
    assert _TRACE_LINE.match(logger_lines[0])
    assert logger_lines[1] == (
        '→ OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)'
    )
    assert logger_lines[2] == '← returned: "ORD-cust-1-prod-42-3"'

    # Built by concatenation, not an indented triple-quoted literal: `_order_service_source()`'s
    # lines have their own (zero) indentation, and splicing them into an indented f-string leaves
    # `pytester.makepyfile`'s `textwrap.dedent` nothing consistent to strip.
    module_source = (
        "from narrativetrace.trace_object import trace_object\n\n"
        + _order_service_source()
        + "\n\n"
        "def test_place_order(narrative_trace):\n"
        "    service = trace_object(OrderService(), narrative_trace)\n"
        '    assert service.place_order("cust-1", "prod-42", 3) == "ORD-cust-1-prod-42-3"\n'
    )
    pytester.makepyfile(module_source)
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=1)
    artifacts = list(pytester.path.rglob("test_place_order.md"))
    assert len(artifacts) == 1, "narrativetrace-pytest must write a trace artifact by default"
