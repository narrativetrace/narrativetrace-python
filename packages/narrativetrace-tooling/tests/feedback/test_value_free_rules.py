# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The ten value-free rules, one at a time, in both directions.

Each rule is tested on its own rather than through a report, because the corpus replay in
``narrativetrace-security-tests`` asserts the PRODUCT's promise ("this text may never reach a public
issue") and these assert the implementation's reach ("this rule is the one that notices"). A rule
whose corpus rows are all caught by a sibling rule would pass the replay and still be dead code.
"""

from __future__ import annotations

import pytest

from narrativetrace_tooling.feedback.check import rules_refusing
from narrativetrace_tooling.feedback.matchers import BASE64_RUN, shannon_bits_per_character
from narrativetrace_tooling.feedback.rules import (
    ALL_RULES,
    CONTROL,
    DURATION,
    EMAIL,
    ENTROPY,
    HOME_PATH,
    MARKER,
    RENDERED_CALL,
    RENDERED_OUTCOME,
    ValueFreeRule,
)


class TestTheRuleTable:
    def test_every_rule_carries_a_vf_prefixed_id_and_a_reason_a_person_can_act_on(self) -> None:
        for rule in ALL_RULES:
            assert rule.id.startswith("vf."), rule.id
            assert len(rule.reason) > 40, f"{rule.id}: a refusal has to say what to fix"

    def test_rule_ids_are_unique(self) -> None:
        ids = [rule.id for rule in ALL_RULES]

        assert len(ids) == len(set(ids))

    def test_a_rule_reads_text_and_refuses_none(self) -> None:
        """An absent field is ``""`` to every caller in this package, so ``None`` is a
        programming error rather than empty input — and reading it as empty would make a rule
        silently pass on a field nobody filled in."""
        with pytest.raises(TypeError, match=r"never None"):
            MARKER.rejects(None)  # type: ignore[arg-type]


class TestRenderedCall:
    @pytest.mark.parametrize(
        "text",
        [
            'OrderService.place_order(customer_id: "C-1234", total: 19.99)',
            '    - Inventory.reserve(sku: "TENT-2", quantity: 1)',
        ],
    )
    def test_refuses_a_qualified_call_line_carrying_a_parameters_value(self, text: str) -> None:
        assert RENDERED_CALL.rejects(text)

    @pytest.mark.parametrize("mark", ["**", "__", "*", "_"])
    def test_refuses_the_call_line_when_markdown_emphasis_sits_between_name_and_parenthesis(
        self, mark: str
    ) -> None:
        """Every runtime's Markdown renderer bolds the qualified name, so the real line is
        ``- **Name.method**(param: value)`` and not the bare form the rule was first written for."""
        assert RENDERED_CALL.rejects(f'- {mark}Order.place{mark}(customer_id: `"C-1"`)')

    @pytest.mark.parametrize("pair", ["*_", "_*"])
    def test_refuses_the_call_line_when_a_stray_mixed_emphasis_pair_sits_before_the_parenthesis(
        self, pair: str
    ) -> None:
        """The marker is a bounded class (``[*_]{0,2}``), never the overlapping alternation a ReDoS
        gate refuses; the mixed pair the class also admits only makes this deny rule stricter."""
        assert RENDERED_CALL.rejects(f'- Order.place{pair}(customer_id: "C-1")')

    def test_accepts_the_structural_call_line_when_its_name_is_emphasised(self) -> None:
        assert not RENDERED_CALL.rejects("- **Order.place**(customer_id, total)")

    @pytest.mark.parametrize(
        "text",
        [
            "- OrderService.place_order(customer_id, total)",
            "- Login.authenticate(username, password)",
            'place_order(id: "C-1")',
        ],
    )
    def test_accepts_a_structural_call_line_and_an_unqualified_fragment(self, text: str) -> None:
        """The last row is a decided LIMIT, pinned by the corpus row
        ``accepted-unqualified-rendered-call``: the rendered artifact always writes
        ``Type.method(...)``, which is what this rule is anchored on, so a hand-typed fragment is
        reached only by its key's name, through ``vf.named-secret``."""
        assert not RENDERED_CALL.rejects(text)


class TestRenderedOutcome:
    @pytest.mark.parametrize(
        "text",
        [
            'OrderService.place_order(customer_id) → "ORD-9001"',
            "Pricing.quote(sku) → 19.99",
            "Catalog.search(term) → List(3 items)",
        ],
    )
    def test_refuses_an_arrow_carrying_anything_but_the_structural_literal(self, text: str) -> None:
        assert RENDERED_OUTCOME.rejects(text)

    @pytest.mark.parametrize(
        "text",
        [
            "- OrderService.place_order(customer_id) → value",
            "- Inventory.reserve(sku) !! IllegalStateException",
            "- Inventory.reserve(sku) ?? incomplete",
        ],
    )
    def test_accepts_the_three_structural_outcomes(self, text: str) -> None:
        assert not RENDERED_OUTCOME.rejects(text)

    def test_the_word_value_must_be_the_whole_word(self) -> None:
        """``→ values_by_sku`` starts with the structural literal and is not it — a prefix
        test would let every identifier beginning with those five letters through."""
        assert RENDERED_OUTCOME.rejects("Catalog.search(term) → values_by_sku")


class TestDuration:
    @pytest.mark.parametrize(
        "text",
        [
            "OrderService.place_order(customer_id) — 1ms",
            "TripSettlement.settle(trip_name) — 1.5 s",
            "Inventory.reserve(sku) — 900µs",
            "Inventory.reserve(sku) — 12ns",
        ],
    )
    def test_refuses_an_elapsed_time_in_every_unit_the_renderer_writes(self, text: str) -> None:
        assert DURATION.rejects(text)

    @pytest.mark.parametrize(
        "text",
        [
            "twelve checks — 2 findings, both in the trap family",
            "narrativetrace 0.2.4 — 3 packages",
            "ai.narrativetrace:narrativetrace-core:0.2.4",
        ],
    )
    def test_accepts_the_numbers_a_legitimate_report_is_full_of(self, text: str) -> None:
        """Anchored on the em dash AND a unit, because a version coordinate and a finding count
        are the two numbers every report carries."""
        assert not DURATION.rejects(text)


class TestMarker:
    def test_refuses_the_redaction_marker_anywhere(self) -> None:
        assert MARKER.rejects('Login.authenticate(user: "ada", password: [REDACTED])')
        assert MARKER.rejects("[REDACTED]")

    def test_accepts_a_report_that_only_talks_about_redaction(self) -> None:
        assert not MARKER.rejects("the redaction check failed and its fix did not help")


class TestEntropy:
    @pytest.mark.parametrize(
        "text",
        [
            "Zm9vYmFyYmF6cXV1eHdhbGRvZnJlZG1pbmU9",
            "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        ],
        ids=["base64-session-token", "base64url-with-underscore"],
    )
    def test_refuses_an_opaque_encoded_run_with_nothing_but_density_to_give_it_away(
        self, text: str
    ) -> None:
        assert ENTROPY.rejects(text)

    @pytest.mark.parametrize(
        "text",
        [
            "a3f5c8e9d2b14706a3f5c8e9d2b14706",
            "a3f5c8e9d2b14706a3f5c8e9d2b1470689abcdef0123456789abcdef01234567",
        ],
        ids=["hex-run-32", "hex-run-64"],
    )
    def test_refuses_a_hex_run_by_length_because_entropy_can_never_reach_it(
        self, text: str
    ) -> None:
        """Sixteen symbols cap Shannon entropy at 4.0 bits per character, so the ceiling can never
        fire on hex. The hex half of this rule is carried by LENGTH instead — no word is 32 hex
        digits. Corpus row ``entropy-hex-run-32`` says so in its own description, which is what
        makes deleting the length clause a decision rather than a simplification."""
        assert ENTROPY.rejects(text)

    def test_the_entropy_ceiling_really_cannot_fire_on_hex(self) -> None:
        """The claim above, measured rather than asserted: the densest possible 64-character hex
        run — every symbol used equally often — still sits at exactly 4.0, which is not ABOVE the
        ceiling."""
        densest_hex = "0123456789abcdef" * 4

        assert shannon_bits_per_character(densest_hex) == pytest.approx(4.0)
        assert shannon_bits_per_character(densest_hex) <= 4.0

    @pytest.mark.parametrize(
        "text",
        [
            "the-quick-brown-fox-jumps-over-the-lazy-dog",
            "deadbeefcafe showed up in the stack trace",
            "https://narrativetrace.ai/docs/privacy-and-redaction#redaction-surface-by-surface",
            "build/narrativetrace/structural/OrderServiceTest/order_is_placed.nt",
        ],
        ids=["hyphenated-prose", "short-hex-word", "doc-url", "structural-artifact-path"],
    )
    def test_accepts_the_long_strings_a_legitimate_report_is_made_of(self, text: str) -> None:
        assert not ENTROPY.rejects(text)

    def test_a_path_is_several_runs_rather_than_one_long_one(self) -> None:
        """Measured, not quoted. As ONE run this path sits at 3.958 bits per character — four
        hundredths under the ceiling, the closest any legitimate string in the product came to
        being refused as a secret. That is a hair's breadth, not a decision, and this port tripped
        it (see the next test). Excluding the path SEPARATOR from the run alphabet replaced the
        margin with a split: the path reaches the length floor nowhere at all."""
        path = "build/narrativetrace/structural/OrderServiceTest/order_is_placed"

        assert 3.9 < shannon_bits_per_character(path) < 4.0, "the margin this used to rely on"
        assert BASE64_RUN.findall(path) == [], "no segment of a path is a 32-character run"
        assert not ENTROPY.rejects(path)

    def test_a_doc_url_quoted_in_a_persons_own_prose_stays_filable(self) -> None:
        """THE defect this port found by running the real doctor rather than a hand-written
        stand-in for one (cross-port item 1, this port's own instance). This runtime's doc URLs are
        GitHub blob links, so one segment of the doctor's own ``doc_url`` field —
        ``python/blob/main/documentation/guides/configuration``, 51 characters at 4.0303 bits per
        character — sat just OVER the ceiling. Every doctor report this port can generate was
        refused, and so was any report whose prose quoted a doc URL."""
        quoted = (
            "I followed https://github.com/narrativetrace/narrativetrace-python/blob/main/"
            "documentation/guides/configuration.md#where-settings-come-from and it did not help"
        )
        the_segment_that_tripped_it = "python/blob/main/documentation/guides/configuration"

        assert shannon_bits_per_character(the_segment_that_tripped_it) > 4.0
        assert len(the_segment_that_tripped_it) >= 32
        assert not ENTROPY.rejects(quoted)

    def test_a_slash_free_encoded_run_is_still_refused_after_the_alphabet_narrowed(self) -> None:
        """The exclusion must not have cost the rule its subject. Both corpus rows this rule
        exists for are slash-free, and they stay refused."""
        assert ENTROPY.rejects("Zm9vYmFyYmF6cXV1eHdhbGRvZnJlZG1pbmU9")
        assert ENTROPY.rejects("dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk")

    def test_a_hyphen_is_not_a_run_character_and_that_is_what_keeps_prose_filable(self) -> None:
        """Admitting the hyphen to the alphabet — base64url does use it — would refuse every
        hyphenated phrase of 32 characters. This one measures 4.33 bits per character, above the
        ceiling, so it would be refused as a secret. Corpus row ``accepted-hyphenated-prose``."""
        phrase = "the-quick-brown-fox-jumps-over-the-lazy"

        assert shannon_bits_per_character(phrase) > 4.0
        assert not ENTROPY.rejects(phrase)

    def test_an_empty_run_has_no_entropy_rather_than_dividing_by_zero(self) -> None:
        assert shannon_bits_per_character("") == 0.0


class TestEmail:
    @pytest.mark.parametrize(
        "text",
        [
            "ada@example.com saw it first on the staging build",
            "ada+narrativetrace@example.co.uk reported it",
        ],
    )
    def test_refuses_an_address_wherever_it_sits_in_a_sentence(self, text: str) -> None:
        assert EMAIL.rejects(text)

    @pytest.mark.parametrize(
        "text",
        [
            "the @not_traced import was never applied to the field",
            "install narrativetrace[otel] and re-run",
        ],
    )
    def test_accepts_an_at_sign_with_no_local_part_before_it(self, text: str) -> None:
        assert not EMAIL.rejects(text)


class TestHomePath:
    @pytest.mark.parametrize(
        "text",
        [
            "/Users/ada/work/orders/narrative-traces",
            "/home/ada/work/orders/narrative-traces",
            "C:\\Users\\ada\\work\\orders",
        ],
        ids=["macos", "linux", "windows"],
    )
    def test_refuses_an_absolute_home_directory_on_every_platform(self, text: str) -> None:
        assert HOME_PATH.rejects(text)

    @pytest.mark.parametrize(
        "text",
        [
            "~/work/orders/narrative-traces",
            "build/narrativetrace/doctor-report.json",
            "/usr/share/ada/data",
            "/home",
        ],
        ids=["rewritten", "relative", "not-a-home-root", "no-account-segment"],
    )
    def test_accepts_a_path_that_names_nobody(self, text: str) -> None:
        """The draft rewrites a home directory to ``~`` before the gate reads anything, so a hit
        here means the text was edited by hand afterwards. A rewrite that was eager would turn an
        ordinary path into ``~`` and make the report wrong instead of safe."""
        assert not HOME_PATH.rejects(text)


class TestControl:
    @pytest.mark.parametrize(
        "codepoint",
        [0x00, 0x07, 0x0D, 0x1B, 0x7F, 0x9F, 0x202E, 0x2066, 0xFEFF],
        ids=["nul", "bell", "cr", "escape", "delete", "c1", "rtl-override", "lri", "bom"],
    )
    def test_refuses_a_control_character_including_unicodes_own_bidi_controls(
        self, codepoint: int
    ) -> None:
        """``chr`` throughout: embedding the raw invisible characters in this source file would be
        the trojan-source hazard the rule exists to catch. The bidi half is in scope because a
        right-to-left override in an issue title reorders what the person triaging it SEES without
        changing a byte of what was filed."""
        assert CONTROL.rejects("trap.redaction-proof" + chr(codepoint))

    def test_accepts_the_two_whitespace_characters_a_report_legitimately_has(self) -> None:
        assert not CONTROL.rejects("did:\n\tran the doctor twice\n")

    @pytest.mark.parametrize("codepoint", [0x200B, 0x200C, 0x200D], ids=["zwsp", "zwnj", "zwj"])
    def test_accepts_a_zero_width_joiner_because_a_report_may_be_in_any_language(
        self, codepoint: int
    ) -> None:
        """Deliberately NOT all of the format category. The zero-width joiner and non-joiner are
        load-bearing letters in Devanagari, Bengali and emoji sequences — refusing them would
        refuse a report written in Hindi."""
        assert not CONTROL.rejects("trap" + chr(codepoint) + "redaction")


class TestRulesRefusing:
    def test_names_every_rule_that_refuses_the_text_in_declaration_order(self) -> None:
        refusing = rules_refusing('OrderService.place_order(id: "C-1") — 1ms')

        assert [rule.id for rule in refusing] == ["vf.rendered-call", "vf.duration"]

    def test_a_value_free_line_is_refused_by_nothing(self) -> None:
        assert rules_refusing("- OrderService.place_order(customer_id) → value") == ()

    def test_reads_text_and_refuses_none(self) -> None:
        with pytest.raises(TypeError, match=r"never None"):
            rules_refusing(None)  # type: ignore[arg-type]


class TestRuleIdentity:
    def test_a_rule_compares_by_value_and_is_hashable_so_a_test_can_assert_on_a_set(self) -> None:
        same = ValueFreeRule(RENDERED_CALL.id, RENDERED_CALL.reason, RENDERED_CALL.refuses)

        assert same == RENDERED_CALL
        assert RENDERED_CALL != MARKER
        assert len({RENDERED_CALL, MARKER, same}) == 2

    def test_a_rule_prints_as_its_id_so_a_failure_names_what_refused(self) -> None:
        assert str(RENDERED_CALL) == "vf.rendered-call"

    def test_the_table_is_a_tuple_so_no_caller_can_add_a_rule_at_runtime(self) -> None:
        assert isinstance(ALL_RULES, tuple)
        assert all(isinstance(rule, ValueFreeRule) for rule in ALL_RULES)
