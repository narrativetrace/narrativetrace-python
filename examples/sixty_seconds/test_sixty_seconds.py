# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The one test behind documentation/sixty-seconds.md's "See a trace in 60 seconds" page (and,
indirectly, documentation/llms.txt's "Install and first trace" block -- see ``main_llms.py``) and
the Logging Guide's Loguru section (``main_with_loguru.py``).

This directory *is* the tutorial (rule 8, docs as tests):
``main.py`` is byte-identical to the page's "The program" code block, ``main_with_logger.py`` is
what the page's "Send it to your logger" diff turns it into, ``main_llms.py`` is the same
program with one ``@not_traced`` parameter -- the variant `llms.txt` embeds so an agent's first
program already shows redaction applied, not just imported (see documentation/llms.txt) -- and
``main_with_loguru.py`` is ``main_with_logger.py``'s sibling for the Logging Guide's Loguru
section: Loguru's own documented ``InterceptHandler`` recipe (stdlib interop) plus
``export_to_logger`` (documentation/guides/logging.md). All four run exactly as their page's
"Run it" step says (``uv run main.py``). None is exercised by import: each runs as a real,
separate ``python`` process, the same way a reader's shell runs them, so nothing here touches
another's global state (``main_with_logger.py``'s and ``main_with_loguru.py``'s single
``export_to_logger()`` call each opens its own private ``LoggingTraceConsumer`` -- never two on
one event stream, see ``narrativetrace.logging_bridge`` -- and their ``logging.basicConfig``
calls, which would otherwise leak a stdout handler onto the root logger for the rest of this
suite's process; ``main_with_loguru.py`` additionally calls ``loguru.logger.remove()``/``add()``,
which would otherwise leak its own sink onto Loguru's process-wide default logger).

The four scripts' captured stdout is saved under ``build/`` (git-ignored, regenerated every run --
see documentation/what-to-commit.md) for ``scripts/snippet_check.py`` to embed as the page's and
`llms.txt`'s output blocks, ``mask=duration`` neutralizing the one thing a real run cannot pin
down.

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


_REDACTED_TRACE_LINE = re.compile(
    r'^OrderService\.place_order\(customer_id: \[REDACTED\], product_id: "prod-42", quantity: 3\) '
    r'→ "ORD-cust-1-prod-42-3" — \d+(\.\d+)?ms$'
)

# main.py/main_with_logger.py adopt a fixed trace id (DEMO_TRACE_ID) so the page's embedded
# output always names the same trace (2026-09-13 ruling, item 5) -- the phrase TraceNamer derives
# from it, and the console renderer's own header line (item 4).
_DEMO_TRACE_HEADER = "trace: loose hook parks (a1b2c3d)"

# main_llms.py adopts no fixed id -- its header names a genuinely random trace every run.
_ANY_TRACE_HEADER = re.compile(r"^trace: [a-z]+ [a-z]+ [a-z]+ \([0-9a-f]{7}\)$")


def _assert_plain_output(plain: str) -> None:
    plain_lines = plain.splitlines()
    assert len(plain_lines) == 3
    assert plain_lines[0] == _DEMO_TRACE_HEADER
    assert plain_lines[1] == ""
    assert _TRACE_LINE.match(plain_lines[2])


def _assert_logger_output(with_logger: str) -> None:
    logger_lines = with_logger.splitlines()
    assert len(logger_lines) == 5
    assert logger_lines[0] == _DEMO_TRACE_HEADER
    assert logger_lines[1] == ""
    assert _TRACE_LINE.match(logger_lines[2])
    # export_to_logger's replay now carries the captured tree's own trace_id (its docstring), so
    # `traceName` here is the SAME fixed phrase as the console header above -- never random, no
    # mask needed on the page's embed. `runName` is empty either way, since this plain script
    # belongs to no test-suite execution (2026-09-13 ruling, item 2).
    assert logger_lines[3] == (
        "[loose hook parks] [] → "
        'OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", quantity: 3)'
    )
    assert logger_lines[4] == '[loose hook parks] [] ← returned: "ORD-cust-1-prod-42-3"'


def _assert_redaction_output(with_redaction: str) -> None:
    redaction_lines = with_redaction.splitlines()
    assert len(redaction_lines) == 3
    assert _ANY_TRACE_HEADER.match(redaction_lines[0])
    assert redaction_lines[1] == ""
    assert _REDACTED_TRACE_LINE.match(redaction_lines[2])


def _assert_loguru_output(with_loguru: str) -> None:
    loguru_lines = with_loguru.splitlines()
    assert len(loguru_lines) == 5
    assert loguru_lines[0] == _DEMO_TRACE_HEADER
    assert loguru_lines[1] == ""
    assert _TRACE_LINE.match(loguru_lines[2])
    # Loguru's InterceptHandler re-logs via `logger.opt(...).log(level, record.getMessage())` --
    # `record.getMessage()` is the SAME text `_assert_logger_output` checks above the
    # `%(traceName)s`/`%(runName)s` prefix a stdlib Formatter would otherwise add; InterceptHandler
    # never applies one, so these two lines carry no MDC prefix, only the demo sink's fixed
    # `{level} | {message}` format (main_with_loguru.py) -- deterministic, no timestamp.
    assert loguru_lines[3] == (
        'DEBUG | → OrderService.place_order(customer_id: "cust-1", product_id: "prod-42", '
        "quantity: 3)"
    )
    assert loguru_lines[4] == 'DEBUG | ← returned: "ORD-cust-1-prod-42-3"'


def _assert_pytest_fixture_writes_an_artifact(pytester: pytest.Pytester) -> None:
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


def test_see_a_trace_in_60_seconds(pytester: pytest.Pytester) -> None:
    """Runs the tutorial call through the real traced proxy five ways, once per page/llms.txt/
    Logging Guide section:

    - the plain script ("The program" / "Run it"), captured and saved for the snippet embed;
    - its logger-wired sibling ("Send it to your logger"), same treatment;
    - its redaction-wired sibling (llms.txt's "Install and first trace" block), same treatment;
    - its Loguru-wired sibling (the Logging Guide's Loguru section), same treatment;
    - the identical call again, through ``narrativetrace-pytest``'s fixture in an isolated
      subprocess, proving the runtime's own test integration writes the artifact by default.
    """
    plain, with_logger, with_redaction, with_loguru = write_artifacts()

    _assert_plain_output(plain)
    _assert_logger_output(with_logger)
    _assert_redaction_output(with_redaction)
    _assert_loguru_output(with_loguru)
    _assert_pytest_fixture_writes_an_artifact(pytester)
