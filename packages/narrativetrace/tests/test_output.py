# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for console reporting, template warnings, paths, and the trace writer."""

from __future__ import annotations

from pathlib import Path

from narrativetrace.loss import TraceLoss
from narrativetrace.nodes import TraceNode
from narrativetrace.outcomes import Returned, Threw
from narrativetrace.output.paths import (
    _java_string_hash,
    extension_for_format,
    file_slug,
    trace_directory,
    trace_file,
)
from narrativetrace.output.reporter import ConsoleSummaryReporter
from narrativetrace.output.warnings import collect, format_warnings
from narrativetrace.output.writer import TraceArtifact, write_trace
from narrativetrace.render.base import TraceMetadata
from narrativetrace.render.scenario_result import ScenarioResult
from narrativetrace.signature import MethodSignature
from narrativetrace.tree import TraceTree

MS = 1_000_000


class TestReporter:
    def test_result_with_clarity(self) -> None:
        assert ConsoleSummaryReporter().format_test_result("t", 12, 0.5) == (
            "    ✓ t (12ms, clarity: 0.50)"
        )

    def test_result_without_clarity(self) -> None:
        assert ConsoleSummaryReporter().format_test_result("t", 12) == "    ✓ t (12ms)"

    def test_failure_block(self) -> None:
        block = ConsoleSummaryReporter().format_test_failure("t", 5, "ValueError", "svc.py:3", "/p")
        assert block == ("    ✗ t (5ms)\n      > ValueError at svc.py:3\n      > Full trace: /p")

    def test_header(self) -> None:
        assert ConsoleSummaryReporter().format_suite_header() == (
            "NarrativeTrace — Recording test narratives\n"
        )

    def test_footer_clarity_buckets_at_boundaries(self) -> None:
        footer = ConsoleSummaryReporter().format_suite_footer(3, "/out", [0.7, 0.4, 0.1])
        assert "Clarity: 33% high | 33% moderate | 33% low" in footer

    def test_footer_empty_clarity_is_zero_invariant(self) -> None:
        footer = ConsoleSummaryReporter().format_suite_footer(0, "/out", [])
        assert "Clarity: 0% high | 0% moderate | 0% low" in footer

    def test_footer_without_clarity(self) -> None:
        footer = ConsoleSummaryReporter().format_suite_footer(2, "/out")
        assert "2 scenarios recorded" in footer
        assert "Reports: /out" in footer


class TestSuiteFooterLossLine:
    """One line naming what a run lost, omitted entirely when it lost nothing."""

    def _footer(self, loss: TraceLoss) -> str:
        return ConsoleSummaryReporter().format_suite_footer(5, "/out", [0.9, 0.8], loss)

    def test_says_nothing_when_nothing_was_lost(self) -> None:
        footer = self._footer(TraceLoss.none())
        assert "Incomplete" not in footer
        assert "5 scenarios recorded" in footer

    def test_a_footer_with_a_loss_reads_exactly_like_this(self) -> None:
        """Golden: the substring assertions above cannot see a mangled separator or line break."""
        assert self._footer(TraceLoss(12, 1, 7)) == (
            "\nNarrativeTrace — Suite complete\n"
            "  5 scenarios recorded\n"
            "  Clarity: 100% high | 0% moderate | 0% low\n"
            "  Incomplete: 12 events dropped (buffer full), 1 async scope not adopted (cap), "
            "7 spans\n"
            "  Reports: /out"
        )

    def test_a_footer_that_lost_nothing_reads_exactly_like_this(self) -> None:
        assert self._footer(TraceLoss.none()) == (
            "\nNarrativeTrace — Suite complete\n"
            "  5 scenarios recorded\n"
            "  Clarity: 100% high | 0% moderate | 0% low\n"
            "  Reports: /out"
        )

    def test_a_footer_without_a_clarity_split_reads_exactly_like_this(self) -> None:
        footer = ConsoleSummaryReporter().format_suite_footer(2, "/out", None, TraceLoss(0, 1, 1))
        assert footer == (
            "\nNarrativeTrace — Suite complete\n"
            "  2 scenarios recorded\n"
            "  Incomplete: 1 async scope not adopted (cap), 1 span\n"
            "  Reports: /out"
        )

    def test_reports_dropped_events_alone(self) -> None:
        footer = self._footer(TraceLoss(1204, 0, 0))
        assert "Incomplete: 1204 events dropped (buffer full)" in footer
        assert "not adopted" not in footer

    def test_reports_refused_scopes_alone(self) -> None:
        footer = self._footer(TraceLoss(0, 3, 4100))
        assert "Incomplete: 3 async scopes not adopted (cap), 4100 spans" in footer
        assert "buffer full" not in footer

    def test_reports_both_sources_on_one_line(self) -> None:
        footer = self._footer(TraceLoss(12, 1, 7))
        assert "Incomplete: 12 events dropped (buffer full)" in footer
        assert "1 async scope not adopted (cap), 7 spans" in footer

    def test_singular_and_plural_read_correctly(self) -> None:
        footer = ConsoleSummaryReporter().format_suite_footer(1, "/out", [0.9], TraceLoss(1, 1, 1))
        assert "1 event dropped" in footer
        assert "1 async scope" in footer
        assert "1 span" in footer

    def test_the_loss_line_sits_above_the_reports_path(self) -> None:
        footer = self._footer(TraceLoss(2, 0, 0))
        assert footer.index("Incomplete:") < footer.index("Reports:")

    def test_the_existing_footer_keeps_working_without_a_loss(self) -> None:
        footer = ConsoleSummaryReporter().format_suite_footer(5, "/out", [0.9, 0.8])
        assert "5 scenarios recorded" in footer
        assert "Incomplete" not in footer

    def test_a_loss_is_named_even_without_a_clarity_split(self) -> None:
        footer = ConsoleSummaryReporter().format_suite_footer(5, "/out", None, TraceLoss(2, 0, 0))
        assert "Incomplete: 2 events dropped (buffer full)" in footer
        assert "Clarity" not in footer


class TestWarnings:
    def _tree(self, narration: str | None, error_context: str | None) -> TraceTree:
        sig = MethodSignature("Svc", "run", [], narration, error_context)
        return TraceTree([TraceNode(sig, [], Returned("x"))])

    def test_single_placeholder_in_narration(self) -> None:
        warnings = collect(self._tree("sent {order id}", None))
        assert len(warnings) == 1
        assert warnings[0].placeholder == "order id"
        assert warnings[0].field == "narration"

    def test_multi_segment_placeholder(self) -> None:
        warnings = collect(self._tree("{customer.address.city}", None))
        assert len(warnings) == 1

    def test_both_fields_yield_two_warnings(self) -> None:
        warnings = collect(self._tree("{a}", "{b}"))
        assert len(warnings) == 2

    def test_format_header_and_lines(self) -> None:
        out = format_warnings(collect(self._tree("{a}", None)))
        assert out.startswith("WARNING: Unresolved template placeholder(s) detected:")
        assert "Svc.run: {a} in narration" in out

    def test_empty_is_blank(self) -> None:
        assert format_warnings([]) == ""

    def test_a_self_referential_node_does_not_crash_collection(self) -> None:
        node = TraceNode(MethodSignature("Svc", "run", []), [], Returned("x"))
        node.children.append(node)  # a hand-built cycle: nothing in the dataclass prevents this
        assert collect(TraceTree([node])) == []

    def test_a_ten_thousand_deep_chain_does_not_overflow_the_stack(self) -> None:
        node = TraceNode(MethodSignature("Svc", "run", []), [], Returned("x"))
        for _ in range(10_000):
            node = TraceNode(MethodSignature("Svc", "run", []), [node], Returned("x"))
        assert isinstance(collect(TraceTree([node])), list)


class TestPaths:
    def test_slug_camel_to_snake(self) -> None:
        assert file_slug("placeOrderNow") == "place_order_now"
        assert file_slug("has spaces!") == "has_spaces_"

    def test_extension_mapping(self) -> None:
        assert extension_for_format("text") == ".txt"
        assert extension_for_format("mermaid") == ".mmd"
        assert extension_for_format("plantuml") == ".puml"
        assert extension_for_format("markdown") == ".md"
        assert extension_for_format("unknown") == ".md"

    def test_extension_mapping_ignores_case(self) -> None:
        assert extension_for_format("TEXT") == ".txt"
        assert extension_for_format("PlantUML") == ".puml"

    def test_trace_directory_uses_simple_class(self) -> None:
        d = trace_directory(Path("/base"), "pkg.mod.TestOrders")
        assert d == Path("/base/traces/TestOrders")

    def test_trace_file(self) -> None:
        f = trace_file(Path("/base"), "TestOrders", "testPlaceOrder")
        assert f == Path("/base/traces/TestOrders/test_place_order.md")


class TestPathSafety:
    """A class name reaches ``trace_directory`` verbatim from a caller's ``Class.getName()`` --
    or, for the many ``TraceTestSupport`` callers that are not a class name at all (a scenario
    name, an HTTP route), from anything. Mirrors Java's ``OutputDirectoryResolver`` fix: the
    method-name slug has always stripped everything but ``[a-z0-9_]``, but the class-name segment
    reached ``Path`` construction unfiltered, so ``../../../tmp/evil`` resolved to an *absolute*
    path a `/` join takes as the whole answer, escaping the output directory entirely."""

    def test_a_traversal_class_name_does_not_escape_the_output_directory(self) -> None:
        d = trace_directory(Path("/base"), "../../../tmp/evil")
        assert str(d).startswith("/base/traces/")

    def test_a_separator_in_a_class_name_does_not_create_a_subdirectory(self) -> None:
        d = trace_directory(Path("/base"), "traces/escaped")
        assert d == Path("/base/traces/traces_escaped")

    def test_a_backslash_in_a_class_name_is_neutralised(self) -> None:
        d = trace_directory(Path("/base"), "traces\\escaped")
        assert d == Path("/base/traces/traces_escaped")

    def test_a_control_character_in_a_class_name_is_neutralised(self) -> None:
        d = trace_directory(Path("/base"), "before\x00after")
        assert d == Path("/base/traces/before_after")

    def test_a_lone_surrogate_in_a_class_name_is_neutralised(self) -> None:
        d = trace_directory(Path("/base"), "name\ud800here")
        assert d == Path("/base/traces/name_here")

    def test_a_bmp_noncharacter_in_a_class_name_is_neutralised(self) -> None:
        # Legal UTF-8, but macOS/APFS raises OSError: Illegal byte sequence from a real mkdir/
        # open carrying either one -- found running this corpus locally, on a filesystem the
        # Java spec repo's Linux dev container never touches.
        d = trace_directory(Path("/base"), "name￾￿here")
        assert d == Path("/base/traces/name__here")

    def test_a_dots_only_name_resolves_to_a_placeholder_not_the_parent_directory(self) -> None:
        d = trace_directory(Path("/base"), "...")
        assert d == Path("/base/traces/unnamed")

    def test_an_empty_class_name_resolves_to_a_placeholder(self) -> None:
        d = trace_directory(Path("/base"), "")
        assert d == Path("/base/traces/unnamed")

    def test_a_plain_class_name_keeps_its_own_spelling(self) -> None:
        d = trace_directory(Path("/base"), "OrderServiceTest")
        assert d == Path("/base/traces/OrderServiceTest")


class TestLongNameCap:
    """The per-component filesystem limit every mainstream filesystem shares (ext4, XFS, APFS,
    NTFS): 255 *bytes*, not characters -- 200 three-byte characters overflow a component 200
    ASCII ones fit inside. Mirrors Java's ``OutputDirectoryResolver.capped``."""

    _MAX_COMPONENT_BYTES = 255

    def test_a_long_class_name_is_capped_to_the_filesystem_limit(self) -> None:
        d = trace_directory(Path("/base"), "a" * 1024)
        assert len(d.name.encode("utf-8")) <= self._MAX_COMPONENT_BYTES

    def test_a_long_method_name_is_capped_to_the_filesystem_limit(self) -> None:
        f = trace_file(Path("/base"), "T", "m" * 1024)
        assert len(f.stem.encode("utf-8")) + len(f.suffix.encode("utf-8")) <= (
            self._MAX_COMPONENT_BYTES
        )

    def test_a_name_under_the_limit_is_untouched(self) -> None:
        assert file_slug("shortName") == "short_name"

    def test_two_long_names_sharing_a_prefix_resolve_to_different_files(self) -> None:
        first = trace_file(Path("/base"), "T", "m" * 300 + "one")
        second = trace_file(Path("/base"), "T", "m" * 300 + "two")
        assert first != second

    def test_resolving_the_same_long_name_twice_gives_the_same_path(self) -> None:
        name = "x" * 500
        assert trace_file(Path("/base"), "T", name) == trace_file(Path("/base"), "T", name)

    def test_a_multibyte_name_is_capped_by_bytes_not_characters(self) -> None:
        # 200 three-byte characters (600 bytes) must not survive uncapped just because a
        # character count alone would call 200 "short".
        f = trace_file(Path("/base"), "T", "漢" * 200)
        assert len(f.stem.encode("utf-8")) + len(f.suffix.encode("utf-8")) <= (
            self._MAX_COMPONENT_BYTES
        )

    def test_the_disambiguator_is_javas_string_hash_of_the_full_slug(self) -> None:
        """Wiring check: ``_capped`` must hash the whole slug, not the already-truncated prefix
        -- hashing the wrong half would still produce eight hex digits and pass every other
        assertion here while silently breaking the family's cross-runtime hash unification."""
        slug = file_slug("m" * 1024)
        assert slug.endswith(f"_{_java_string_hash('m' * 1024):08x}")


class TestJavaStringHash:
    """Parity with Java's specified ``String.hashCode()`` -- ``h = 31*h + c`` over UTF-16 code
    units -- so the same over-long name resolves to the same disambiguator on every runtime in
    the family, not a per-port value. Mirrors dotnet's own hand-rolled reimplementation of the
    same formula (``.NET``, like Python, otherwise randomizes string hashing per process)."""

    def test_the_empty_string_hashes_to_zero(self) -> None:
        assert _java_string_hash("") == 0

    def test_a_single_ascii_character_hashes_to_its_code_point(self) -> None:
        assert _java_string_hash("a") == 97

    def test_matches_the_recurrence_for_a_short_string(self) -> None:
        # h = 31*(31*0 + ord('a')) + ord('b') = 31*97 + 98
        assert _java_string_hash("ab") == 31 * 97 + 98

    def test_matches_javas_well_known_hash_of_hello(self) -> None:
        # A widely-verified constant: Java's "hello".hashCode() == 99162322.
        assert _java_string_hash("hello") == 99162322

    def test_32_bit_overflow_wraps_like_javas_int_arithmetic(self) -> None:
        # Long enough that the unmasked recurrence would exceed 2**32 partway through; every
        # step must wrap to stay a 32-bit unsigned value, matching Java's `int` overflow.
        assert 0 <= _java_string_hash("x" * 50) <= 0xFFFFFFFF

    def test_a_supplementary_character_hashes_as_its_utf16_surrogate_pair(self) -> None:
        # U+1F600 has no single UTF-16 code unit; Java's UTF-16-backed String stores it (and
        # therefore hashes it) as the surrogate pair U+D83D, U+DE00.
        assert _java_string_hash("\U0001f600") == 31 * 0xD83D + 0xDE00

    def test_a_lone_surrogate_hashes_as_one_code_unit_with_no_pairing(self) -> None:
        # Python permits an unpaired surrogate as a scalar value; Java permits the same as an
        # unpaired `char`. Neither language treats it as supplementary, so it is not split.
        assert _java_string_hash("\ud800") == 0xD800

    def test_resolving_the_same_name_twice_gives_the_same_hash(self) -> None:
        assert _java_string_hash("repeat me") == _java_string_hash("repeat me")


class TestWriter:
    def _tree(self) -> TraceTree:
        return TraceTree([TraceNode(MethodSignature("Svc", "run", []), [], Returned("ok"))])

    def test_empty_trace_writes_nothing(self, tmp_path: Path) -> None:
        result = write_trace(
            TraceTree([]),
            TraceMetadata("s", ScenarioResult.SUCCESS),
            TraceArtifact(tmp_path, "T", "m"),
        )
        assert result.files == []
        assert list(tmp_path.rglob("*")) == []

    def test_markdown_written_with_echo(self, tmp_path: Path) -> None:
        result = write_trace(
            self._tree(),
            TraceMetadata("happy", ScenarioResult.SUCCESS),
            TraceArtifact(tmp_path, "T", "runIt"),
        )
        assert len(result.files) == 1
        path = result.files[0]
        assert path == tmp_path / "traces" / "T" / "run_it.md"
        assert path.read_text(encoding="utf-8").startswith("---\ntype: trace")
        assert "Trace written:" in result.console_echo

    def test_text_format_framed(self, tmp_path: Path) -> None:
        result = write_trace(
            self._tree(),
            TraceMetadata("myScenario", ScenarioResult.SUCCESS),
            TraceArtifact(tmp_path, "T", "m", fmt="text"),
        )
        content = result.files[0].read_text(encoding="utf-8")
        assert result.files[0].suffix == ".txt"
        assert content.startswith("Scenario: My scenario")

    def test_plantuml_format_writes_the_diagram_not_markdown(self, tmp_path: Path) -> None:
        result = write_trace(
            self._tree(),
            TraceMetadata("s", ScenarioResult.SUCCESS),
            TraceArtifact(tmp_path, "T", "m", fmt="plantuml"),
            plantuml_renderer=lambda _t: "@startuml\n@enduml",
        )
        assert result.files[0].suffix == ".puml"
        assert result.files[0].read_text(encoding="utf-8") == "@startuml\n@enduml\n"

    def test_format_selection_ignores_case(self, tmp_path: Path) -> None:
        result = write_trace(
            self._tree(),
            TraceMetadata("myScenario", ScenarioResult.SUCCESS),
            TraceArtifact(tmp_path, "T", "m", fmt="TEXT"),
        )
        assert result.files[0].suffix == ".txt"
        assert result.files[0].read_text(encoding="utf-8").startswith("Scenario: My scenario")

    def test_markdown_extras_written_for_mixed_case_format(self, tmp_path: Path) -> None:
        result = write_trace(
            self._tree(),
            TraceMetadata("s", ScenarioResult.SUCCESS),
            TraceArtifact(tmp_path, "T", "m", fmt="Markdown"),
            json_exporter=lambda _t: '{"schema": 1}',
            diagram_renderer=lambda _t: "sequenceDiagram",
        )
        assert {f.suffix for f in result.files} == {".md", ".json", ".mmd"}

    def test_markdown_extras_via_hooks(self, tmp_path: Path) -> None:
        result = write_trace(
            self._tree(),
            TraceMetadata("s", ScenarioResult.SUCCESS),
            TraceArtifact(tmp_path, "T", "m"),
            json_exporter=lambda _t: '{"schema": 1}',
            diagram_renderer=lambda _t: "sequenceDiagram",
        )
        suffixes = {f.suffix for f in result.files}
        assert suffixes == {".md", ".json", ".mmd"}


class TestWriterSurrogateResilience:
    """A security fuzz suite finding, writer layer (mirrors Java's ``TraceFileWriter`` fix):
    narration/scenario text reaches the writer without passing through ``control_sanitize`` (it's
    prose an author wrote, not a captured value), so a lone surrogate in it used to raise
    ``UnicodeEncodeError`` from the filesystem write itself rather than degrade the artifact."""

    def test_a_scenario_name_carrying_a_lone_surrogate_does_not_crash_the_write(
        self, tmp_path: Path
    ) -> None:
        tree = TraceTree([TraceNode(MethodSignature("Svc", "run", []), [], Returned("ok"))])
        metadata = TraceMetadata("before\ud800after", ScenarioResult.SUCCESS)
        result = write_trace(tree, metadata, TraceArtifact(tmp_path, "T", "m", fmt="text"))
        content = result.files[0].read_bytes().decode("utf-8")
        # Python's built-in `errors="replace"` substitutes ASCII "?" on encode (Java's
        # CodingErrorAction.REPLACE substitutes U+FFFD) -- a divergence in the marker's
        # spelling, not in the "degrade rather than crash" contract itself.
        assert "Before?after" in content


class TestErrorCounts:
    def test_write_error_tree(self, tmp_path: Path) -> None:
        tree = TraceTree([TraceNode(MethodSignature("S", "m", []), [], Threw(ValueError("x")))])
        result = write_trace(
            tree, TraceMetadata("s", ScenarioResult.ERROR), TraceArtifact(tmp_path, "T", "m")
        )
        assert "error_count: 1" in result.files[0].read_text(encoding="utf-8")
