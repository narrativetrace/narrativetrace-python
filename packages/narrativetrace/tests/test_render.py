# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Characterization tests pinning renderer output to the Java format."""

from __future__ import annotations

import sys
import types

from narrativetrace.concurrency import ConcurrencyInfo, ConcurrencyKind
from narrativetrace.ids import SpanId, TraceId
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Incomplete, Returned, Threw
from narrativetrace.render import humanize
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.camel import to_phrase
from narrativetrace.render.frontmatter import FrontmatterBuilder
from narrativetrace.render.indented import IndentedTextRenderer
from narrativetrace.render.markdown import MarkdownRenderer
from narrativetrace.render.prose import ProseRenderer
from narrativetrace.render.scenario import frame
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import MethodSignature, ParameterCapture
from narrativetrace.span import SpanContext
from narrativetrace.tree import TraceTree
from narrativetrace.tree_walk import CYCLE_MARKER, DEPTH_LIMIT_MARKER, MAX_DEPTH

MS = 1_000_000


def _sig(
    cls: str,
    method: str,
    params: list[ParameterCapture] | None = None,
    narration: str | None = None,
    error_context: str | None = None,
) -> MethodSignature:
    return MethodSignature(cls, method, params or [], narration, error_context)


def _tree(*roots: TraceNode) -> TraceTree:
    return TraceTree(list(roots))


class TestHelpers:
    def test_to_phrase_camel_and_snake(self) -> None:
        assert to_phrase("OrderService") == "order service"
        assert to_phrase("place_order") == "place order"
        assert to_phrase("placeOrder") == "place order"

    def test_humanize_strips_trailing_parens_and_capitalises(self) -> None:
        assert humanize("placeOrder()") == "Place order"
        assert humanize("already spaced") == "already spaced"

    def test_frame(self) -> None:
        assert frame("placeOrder") == "Scenario: Place order"


class TestMarkdown:
    def test_leaf_return_with_backtick_params(self) -> None:
        node = TraceNode(
            _sig("Svc", "add", [ParameterCapture("a", "2"), ParameterCapture("b", "3")]),
            [],
            Returned("5"),
        )
        assert MarkdownRenderer().render(_tree(node)) == "- **Svc.add**(a: `2`, b: `3`) → `5`"

    def test_slow_marker_is_strict_greater_than(self) -> None:
        exactly = TraceNode(_sig("S", "m"), [], Returned("x"), duration_nanos=200 * MS)
        over = TraceNode(_sig("S", "m"), [], Returned("x"), duration_nanos=201 * MS)
        assert MarkdownRenderer().render(_tree(exactly)) == "- **S.m**() → `x` — 200ms"
        assert MarkdownRenderer().render(_tree(over)) == "- **S.m**() → `x` — 201ms ⚠️ slow"

    def test_parent_closing_bullet_and_narration(self) -> None:
        child = TraceNode(_sig("Svc", "inner"), [], Returned("i"))
        parent = TraceNode(_sig("Svc", "outer", narration="doing work"), [child], Returned("o"))
        assert MarkdownRenderer().render(_tree(parent)) == (
            "- **Svc.outer**()\n  *doing work*\n  - **Svc.inner**() → `i`\n  - → `o`"
        )

    def test_error_block(self) -> None:
        node = TraceNode(
            _sig("Svc", "boom", error_context="failed to boom"),
            [],
            Threw(ValueError("kaboom")),
        )
        assert MarkdownRenderer().render(_tree(node)) == (
            "- **Svc.boom**()\n\n  > ❌ `ValueError`: kaboom\n  > failed to boom"
        )

    def test_redacted_param(self) -> None:
        node = TraceNode(
            _sig("S", "m", [ParameterCapture("pw", "", redacted=True)]), [], Returned("x")
        )
        assert MarkdownRenderer().render(_tree(node)) == "- **S.m**(pw: `[REDACTED]`) → `x`"

    def test_incomplete(self) -> None:
        node = TraceNode(_sig("S", "m"), [], Incomplete())
        assert MarkdownRenderer().render(_tree(node)) == "- **S.m**() ⏳ in-flight"

    def test_message_is_html_escaped(self) -> None:
        node = TraceNode(_sig("S", "m"), [], Threw(ValueError("<script>")))
        assert "&lt;script&gt;" in MarkdownRenderer().render(_tree(node))

    def test_class_name_is_html_escaped(self) -> None:
        # Adversarial-audit mirror (2026-09-02): class_name/method_name were interpolated raw
        # while the return/exception value beside them was already escaped.
        node = TraceNode(_sig("<script>", "m"), [], Returned("x"))
        assert "&lt;script&gt;" in MarkdownRenderer().render(_tree(node))

    def test_parameter_name_is_html_escaped(self) -> None:
        node = TraceNode(_sig("S", "m", [ParameterCapture("<b>", "1")]), [], Returned("x"))
        assert "&lt;b&gt;" in MarkdownRenderer().render(_tree(node))

    def test_exception_type_name_backtick_does_not_break_the_code_span(self) -> None:
        exc_type = type("Weird`Name", (RuntimeError,), {})
        exc_type.__name__ = "Weird`Name"
        node = TraceNode(_sig("S", "m"), [], Threw(exc_type("x")))
        out = MarkdownRenderer().render(_tree(node))
        # a wider, padded fence must have been chosen -- a single backtick would terminate at the
        # name's own backtick instead of wrapping the whole type name
        assert "`` Weird`Name ``" in out

    def test_a_newline_in_class_name_adds_no_line(self) -> None:
        safe = MarkdownRenderer().render(_tree(TraceNode(_sig("S", "m"), [], Returned("x"))))
        hostile = MarkdownRenderer().render(
            _tree(TraceNode(_sig("S\nx: 1", "m"), [], Returned("x")))
        )
        assert hostile.count("\n") == safe.count("\n")


class TestMarkdownDocument:
    def test_document_has_frontmatter_and_header(self) -> None:
        ctx = SpanContext(trace_id=TraceId("0" * 32), span_id=SpanId("a" * 16))
        root = TraceNode(
            _sig("Svc", "run"), [], Returned("ok"), duration_nanos=5 * MS, span_context=ctx
        )
        doc = MarkdownRenderer().render_document(
            _tree(root), TraceMetadata("happy path", ScenarioResult.SUCCESS)
        )
        assert doc.startswith("---\ntype: trace\nscenario: happy path\n")
        assert "entry_point: Svc.run" in doc
        assert "trace_name: red fox runs" in doc
        assert "## Trace: Svc.run" in doc
        # The human-facing spelling — the wire spelling `success` belongs only in JSON.
        assert "**Duration:** 5ms | **Result:** PASSED" in doc
        assert "### Call Flow" in doc

    def test_a_failed_scenario_captions_the_display_spelling(self) -> None:
        root = TraceNode(_sig("Svc", "run"), [], Returned("ok"), duration_nanos=5 * MS)

        doc = MarkdownRenderer().render_document(
            _tree(root), TraceMetadata("happy path", ScenarioResult.ERROR)
        )

        assert "**Result:** FAILED" in doc

    def test_escapes_scenario_in_document_body_header_exactly_as_in_frontmatter(self) -> None:
        # The frontmatter routes the scenario through YAML escaping; the body header used to
        # interpolate it raw, so a hostile scenario forged document structure (a heading) and
        # injected raw HTML into the rendered Markdown -- a 2026-09-08 audit's finding in the
        # Java spec repo.
        root = TraceNode(_sig("OrderService", "placeOrder"), [], Returned('"order-42"'))
        metadata = TraceMetadata(
            "ok\n# forged heading\n<img src=x onerror=alert(1)>", ScenarioResult.SUCCESS
        )

        doc = MarkdownRenderer().render_document(_tree(root), metadata)

        assert "**Scenario:** ok\\n# forged heading\\n&lt;img src=x onerror=alert(1)&gt;\n" in doc
        assert "# forged heading" not in doc.splitlines()
        # The body (everything after the frontmatter block) carries no active HTML. The
        # frontmatter itself is YAML, where < and > are ordinary printable characters.
        body = doc[doc.index("## Trace:") :]
        assert "<img" not in body


class TestFrontmatter:
    def test_counts_and_yaml_escaping(self) -> None:
        child = TraceNode(_sig("S", "child"), [], Threw(ValueError()))
        root = TraceNode(_sig("S", "root"), [child], Returned("x"))
        fm = FrontmatterBuilder().scenario("has: colon").build(_tree(root))
        assert 'scenario: "has: colon"' in fm
        assert "method_count: 2" in fm
        assert "error_count: 1" in fm

    def test_empty_tree_frontmatter(self) -> None:
        fm = FrontmatterBuilder().scenario("x").build(_tree())
        assert "method_count: 0" in fm
        assert "entry_point" not in fm

    def test_a_leading_indicator_character_is_quoted(self) -> None:
        # Security fuzz suite finding: unquoted, "%s %n %d" is a YAML directive indicator, not a
        # plain scalar -- PyYAML/SnakeYAML both refuse to parse it.
        fm = FrontmatterBuilder().scenario("%s %n %d").build(_tree())
        assert 'scenario: "%s %n %d"' in fm

    def test_a_control_character_is_escaped_not_left_raw(self) -> None:
        # Security fuzz suite finding: a raw C0 control byte inside the quoted scalar violates
        # YAML's printable-character rule even though the string as a whole was quoted.
        fm = FrontmatterBuilder().scenario("a\x01b").build(_tree())
        assert 'scenario: "a\\u0001b"' in fm

    def test_leading_or_trailing_whitespace_is_quoted(self) -> None:
        fm = FrontmatterBuilder().scenario(" x").build(_tree())
        assert 'scenario: " x"' in fm

    def test_plain_text_stays_unquoted(self) -> None:
        fm = FrontmatterBuilder().scenario("happy path").build(_tree())
        assert "scenario: happy path\n" in fm

    def test_a_bmp_noncharacter_is_escaped(self) -> None:
        # Security fuzz suite finding: U+FFFE/U+FFFF are outside control_sanitize's definition of
        # a control character but still violate YAML's printable-character rule.
        fm = FrontmatterBuilder().scenario("a￾b").build(_tree())
        assert 'scenario: "a\\ufffeb"' in fm

    def test_entry_point_is_yaml_escaped_not_raw(self) -> None:
        # Adversarial-audit mirror (2026-09-02): entry_point interpolated class_name/
        # method_name without going through yaml_safe at all -- unlike every other frontmatter
        # field. A class name carrying a colon-space is a new mapping key if unescaped.
        root = TraceNode(_sig("S: evil_key", "run"), [], Returned("x"))
        fm = FrontmatterBuilder().scenario("s").build(_tree(root))
        assert 'entry_point: "S: evil_key.run"' in fm

    def test_a_newline_in_entry_point_adds_no_frontmatter_line(self) -> None:
        root = TraceNode(_sig('S\nevil_key: "h"', "run"), [], Returned("x"))
        fm = FrontmatterBuilder().scenario("s").build(_tree(root))
        assert fm.count("\n") == FrontmatterBuilder().scenario("s").build(
            _tree(TraceNode(_sig("S", "run"), [], Returned("x")))
        ).count("\n")

    def test_a_supplementary_character_is_escaped_not_passed_through_raw(self) -> None:
        # Interoperability, not a Python-side crash: this runtime's str already holds a
        # supplementary character as one code point, and PyYAML round-trips it raw without
        # incident. Java's SnakeYAML 2.3, reading a UTF-16 char stream in 1024-char chunks, can
        # land its buffer boundary between a surrogate pair's two halves and crash on spec-valid
        # YAML -- a 2026-09-08 audit's finding in the Java spec repo. Frontmatter is a
        # machine-readable interoperability contract shared across every NarrativeTrace runtime,
        # so it is emitted BMP-only here too: the 8-digit \U escape is YAML's own (ns-esc-32-bit).
        fm = FrontmatterBuilder().scenario("see\U0001f648no evil").build(_tree())

        assert 'scenario: "see\\U0001f648no evil"' in fm
        assert all(ord(c) <= 0xFFFF for c in fm)

    def test_a_long_astral_run_leaves_no_supplementary_character_raw(self) -> None:
        # The shape of the corpus's long-astral-run-1024 case: enough supplementary characters
        # that a UTF-16-chunked reader elsewhere in the family could land a boundary inside a
        # pair. After escaping, no output character is above the BMP, so the property holds for
        # every alignment, not just one.
        fm = FrontmatterBuilder().scenario("\U0001f648" * 600).build(_tree())

        assert all(ord(c) <= 0xFFFF for c in fm)

    def test_a_self_referential_root_does_not_crash_the_counts(self) -> None:
        root = TraceNode(_sig("S", "root"), [], Returned("x"))
        root.children.append(root)  # a hand-built cycle: nothing in the dataclass prevents this
        fm = FrontmatterBuilder().scenario("s").build(_tree(root))
        assert "method_count: " in fm

    def test_a_ten_thousand_deep_chain_does_not_overflow_the_stack(self) -> None:
        node = TraceNode(_sig("S", "leaf"), [], Returned("x"))
        for _ in range(10_000):
            node = TraceNode(_sig("S", "wrap"), [node], Returned("x"))
        fm = FrontmatterBuilder().scenario("s").build(_tree(node))
        assert "method_count: " in fm


class TestIndented:
    def test_tree_with_error(self) -> None:
        child = TraceNode(_sig("Svc", "inner", error_context="bad"), [], Threw(ValueError("boom")))
        parent = TraceNode(_sig("Svc", "outer"), [child], Returned("o"))
        assert IndentedTextRenderer().render(_tree(parent)) == (
            "Svc.outer()\n├── Svc.inner() !! ValueError: boom | bad\n└── → o"
        )

    def test_redacted_and_void_return(self) -> None:
        node = TraceNode(
            _sig("S", "m", [ParameterCapture("pw", "", redacted=True)]), [], Returned(None)
        )
        assert IndentedTextRenderer().render(_tree(node)) == "S.m(pw: [REDACTED]) → null"

    def test_a_newline_in_class_name_adds_no_line(self) -> None:
        # Adversarial-audit mirror (2026-09-02): class_name/method_name/param names were
        # interpolated raw while the exception message beside them was already sanitised.
        safe = IndentedTextRenderer().render(_tree(TraceNode(_sig("S", "m"), [], Returned("x"))))
        hostile = IndentedTextRenderer().render(
            _tree(TraceNode(_sig("S\nfake line", "m"), [], Returned("x")))
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_a_newline_in_parameter_name_adds_no_line(self) -> None:
        safe = IndentedTextRenderer().render(
            _tree(TraceNode(_sig("S", "m", [ParameterCapture("a", "1")]), [], Returned("x")))
        )
        hostile = IndentedTextRenderer().render(
            _tree(TraceNode(_sig("S", "m", [ParameterCapture("a\nfake", "1")]), [], Returned("x")))
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_a_newline_in_exception_type_name_adds_no_line(self) -> None:
        exc_type = type("Evil", (RuntimeError,), {})
        exc_type.__name__ = "Evil\nfake line"
        node = TraceNode(_sig("S", "m"), [], Threw(exc_type("x")))
        safe = IndentedTextRenderer().render(
            _tree(TraceNode(_sig("S", "m"), [], Threw(RuntimeError("x"))))
        )
        hostile = IndentedTextRenderer().render(_tree(node))
        assert hostile.count("\n") == safe.count("\n")


class TestProse:
    def test_returning_leaf(self) -> None:
        node = TraceNode(
            _sig("OrderService", "placeOrder", [ParameterCapture("id", "7")]), [], Returned("ok")
        )
        assert ProseRenderer().render(_tree(node)) == (
            "The order service place order for id: 7, returning ok."
        )

    def test_failed_to_phrasing(self) -> None:
        node = TraceNode(
            _sig("Svc", "charge", error_context="no funds"), [], Threw(ValueError("nope"))
        )
        assert ProseRenderer().render(_tree(node)) == (
            "The svc failed to charge — ValueError: nope (no funds)."
        )

    def test_parent_structure_and_closing(self) -> None:
        child = TraceNode(_sig("Svc", "inner"), [], Returned("i"))
        parent = TraceNode(_sig("Svc", "outer"), [child], Returned("o"))
        assert ProseRenderer().render(_tree(parent)) == (
            "The svc outer:\n  The svc inner, returning i.\n  Returned o."
        )

    def test_a_newline_in_parameter_name_adds_no_line(self) -> None:
        # Adversarial-audit mirror (2026-09-02): parameter names and the exception message
        # were interpolated raw, unlike every other prose seam.
        safe = ProseRenderer().render(
            _tree(TraceNode(_sig("S", "m", [ParameterCapture("a", "1")]), [], Returned("x")))
        )
        hostile = ProseRenderer().render(
            _tree(TraceNode(_sig("S", "m", [ParameterCapture("a\nfake", "1")]), [], Returned("x")))
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_a_newline_in_the_exception_message_adds_no_line(self) -> None:
        safe = ProseRenderer().render(
            _tree(TraceNode(_sig("S", "m"), [], Threw(RuntimeError("boom"))))
        )
        hostile = ProseRenderer().render(
            _tree(TraceNode(_sig("S", "m"), [], Threw(RuntimeError("boom\nfake line"))))
        )
        assert hostile.count("\n") == safe.count("\n")

    def test_a_newline_in_narration_adds_no_line(self) -> None:
        safe = ProseRenderer().render(
            _tree(TraceNode(_sig("S", "m", narration="ok"), [], Returned("x")))
        )
        hostile = ProseRenderer().render(
            _tree(TraceNode(_sig("S", "m", narration="ok\nfake line"), [], Returned("x")))
        )
        assert hostile.count("\n") == safe.count("\n")


def _member(cls: str, dur_ms: int, start_ms: int, group: str, thread: str) -> TraceNode:
    return TraceNode(
        _sig(cls, "run"),
        [],
        Returned("ok"),
        duration_nanos=dur_ms * MS,
        start_time_nanos=start_ms * MS,
        concurrency=ConcurrencyInfo(group, ConcurrencyKind.FORK_JOIN, thread_name=thread),
    )


class TestConcurrencyRendering:
    def test_markdown_fork_join_with_wait_analysis(self) -> None:
        a = _member("Alpha", 30, 0, "g", "worker-1")
        b = _member("Beta", 10, 5, "g", "worker-2")  # overlaps → parallel
        parent = TraceNode(_sig("Svc", "outer"), [a, b], Returned("o"))
        out = MarkdownRenderer().render(_tree(parent))
        assert "- ⑂ fork [2 tasks]" in out
        assert "- ↦ **Alpha.run**()" in out
        assert "[thread: worker-1]" in out
        assert "- ⑃ join — 30ms (waited 20ms for Alpha after Beta)" in out

    def test_markdown_sequential_async_hint(self) -> None:
        a = _member("Alpha", 10, 0, "g", "w1")
        b = _member("Beta", 10, 20, "g", "w2")  # no overlap → sequential
        parent = TraceNode(_sig("Svc", "outer"), [a, b], Returned("o"))
        out = MarkdownRenderer().render(_tree(parent))
        assert "⚡ Sequential async: total 20ms, parallelizable to ~10ms" in out
        assert "[async, awaited sequentially]" in out

    def test_markdown_fire_and_forget_empty(self) -> None:
        launcher = TraceNode(
            _sig("Bg", "fire-and-forget"),
            [],
            None,
            concurrency=ConcurrencyInfo("f", ConcurrencyKind.FIRE_AND_FORGET, thread_name="daemon"),
        )
        parent = TraceNode(_sig("Svc", "outer"), [launcher], Returned("o"))
        out = MarkdownRenderer().render(_tree(parent))
        assert "- ⤳ fire-and-forget [thread: daemon]" in out
        assert "[launched, result not captured]" in out

    def test_prose_concurrently_label(self) -> None:
        a = _member("Alpha", 10, 0, "g", "w1")
        b = _member("Beta", 10, 5, "g", "w2")
        parent = TraceNode(_sig("Svc", "outer"), [a, b], Returned("o"))
        out = ProseRenderer().render(_tree(parent))
        assert "Concurrently:" in out

    def test_indented_join_line(self) -> None:
        a = _member("Alpha", 30, 0, "g", "w1")
        b = _member("Beta", 10, 5, "g", "w2")
        parent = TraceNode(_sig("Svc", "outer"), [a, b], Returned("o"))
        out = IndentedTextRenderer().render(_tree(parent))
        assert "├── ⑂ fork [2 tasks]" in out
        assert "├── ⑃ join — 30ms" in out


class TestDepthAndCycleBounds:
    """Security-suite mirror (2026-09-04): all three renderers used unbounded native recursion
    with no depth bound or cycle guard -- both a cycle and a pathologically deep chain crashed
    with an uncaught RecursionError."""

    _RENDERERS = (
        ("markdown", MarkdownRenderer()),
        ("indented", IndentedTextRenderer()),
        ("prose", ProseRenderer()),
    )

    @staticmethod
    def _chain(n: int) -> TraceNode:
        node = TraceNode(_sig("S", "leaf"), [], Returned("x"))
        for _ in range(n):
            node = TraceNode(_sig("S", "wrap"), [node], Returned("x"))
        return node

    def test_a_self_referential_node_does_not_crash_any_renderer(self) -> None:
        node = TraceNode(_sig("S", "self"), [], Returned("x"))
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        for name, renderer in self._RENDERERS:
            out = renderer.render(_tree(node))  # must not raise RecursionError
            assert CYCLE_MARKER in out, name

    def test_a_ten_thousand_deep_chain_is_truncated_not_crashed(self) -> None:
        chain = self._chain(10_000)
        for name, renderer in self._RENDERERS:
            out = renderer.render(_tree(chain))  # must not raise RecursionError
            assert DEPTH_LIMIT_MARKER in out, name

    def test_a_chain_within_the_depth_cap_carries_no_marker(self) -> None:
        chain = self._chain(MAX_DEPTH - 1)
        for name, renderer in self._RENDERERS:
            out = renderer.render(_tree(chain))
            assert DEPTH_LIMIT_MARKER not in out, name
            assert CYCLE_MARKER not in out, name

    @staticmethod
    def _frame_depth() -> int:
        depth = 0
        frame: types.FrameType | None = sys._getframe()
        while frame is not None:
            depth += 1
            frame = frame.f_back
        return depth

    def test_a_chain_at_the_depth_cap_survives_a_constrained_call_stack(self) -> None:
        """Pins the *real* stack-safety bound, not merely "works under pytest's own ambient
        1000-frame limit". Every renderer here still recurses natively per tree level (only the
        depth/cycle *check* is bounded, by ``TreeWalk``), so ``MAX_DEPTH`` is only actually safe
        if it needs far fewer frames than whatever recursion budget is available at runtime -- a
        budget this test's own call chain already spends part of, and that a caller embedding this
        library (a web framework, an async runtime) could have eaten further into. Recursion limit
        is set relative to *this test's own* current frame depth, not an absolute number, so the
        margin measured is the renderers' actual frame cost, independent of how deep pytest's own
        collection machinery happens to nest this call. Always restored, even on failure -- a
        stuck low limit would break every later test in the process.

        **The headroom below is calibrated for mutmut, not just plain pytest** (2026-09-09 nightly
        finding): under plain pytest the measured minimum for MarkdownRenderer (the most
        stack-frame-hungry of the three) is 403 frames above this test's own call depth, but
        mutmut wraps every function in a dispatch trampoline (`mutmut.mutation.trampoline
        .wrap_in_trampoline` -- one extra call frame per logical call, present even with no
        mutant active, i.e. `MUTANT_UNDER_TEST` unset), so the *same* chain measured against
        `packages/narrativetrace/mutants`'s instrumented copy needs 1,213 frames -- headroom
        that was fine under plain pytest raised a genuine `RecursionError` once mutmut got
        involved, breaking the nightly `python-mutate-gate` job. 1,600 clears the
        mutmut-instrumented measurement with margin; a caller embedding this library natively
        (no trampoline) keeps roughly 4x that margin on top."""
        chain = self._chain(MAX_DEPTH - 1)
        headroom = 1600
        original_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(self._frame_depth() + headroom)
        try:
            for name, renderer in self._RENDERERS:
                out = renderer.render(_tree(chain))  # must not raise RecursionError
                assert DEPTH_LIMIT_MARKER not in out, name
        finally:
            sys.setrecursionlimit(original_limit)
