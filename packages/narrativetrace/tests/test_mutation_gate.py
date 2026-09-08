# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`poe mutate-gate`'s scoring logic (`scripts/mutation_gate.py`).

Exercises the pure ledger-parsing and kill-rate arithmetic in isolation from mutmut itself —
running the real mutation suite from a unit test would take minutes and require a mutmut cache
on disk. The gate's `main()` glue (subprocess calls, file reads) is exercised by actually running
`poe mutate-gate` in CI, not here.
"""

from __future__ import annotations

import pytest
from scripts.mutation_gate import compute_score, parse_ledger, parse_survived_ids


class TestParseLedger:
    def test_reads_id_and_reason_separated_by_a_tab(self) -> None:
        text = "some.module.x_func__mutmut_1\tthe reason it is equivalent\n"
        assert parse_ledger(text) == {"some.module.x_func__mutmut_1": "the reason it is equivalent"}

    def test_skips_blank_lines_and_comment_lines(self) -> None:
        text = "\n# a comment\n   # indented comment\nid_a\treason a\n"
        assert parse_ledger(text) == {"id_a": "reason a"}

    def test_empty_ledger_parses_to_an_empty_dict(self) -> None:
        assert parse_ledger("") == {}

    def test_last_entry_wins_on_a_duplicate_id(self) -> None:
        text = "dup\tfirst reason\ndup\tsecond reason\n"
        assert parse_ledger(text) == {"dup": "second reason"}


class TestParseSurvivedIds:
    def test_collects_only_ids_marked_survived(self) -> None:
        text = "    module.x_a__mutmut_1: survived\n    module.x_b__mutmut_2: killed\n"
        assert parse_survived_ids(text) == {"module.x_a__mutmut_1"}

    def test_ignores_non_result_lines(self) -> None:
        text = "\nTo apply a mutant on disk:\n    module.x_a__mutmut_1: survived\n"
        assert parse_survived_ids(text) == {"module.x_a__mutmut_1"}

    def test_no_survivors_returns_an_empty_set(self) -> None:
        text = "    module.x_a__mutmut_1: killed\n    module.x_b__mutmut_2: no tests\n"
        assert parse_survived_ids(text) == set()


class TestComputeScore:
    def test_ledgered_and_still_surviving_mutants_are_excluded_from_the_denominator(self) -> None:
        score, excluded = compute_score(
            total=100, killed=80, ledger_ids={"equiv_1"}, survived_ids={"equiv_1"}
        )
        assert excluded == 1
        assert score == pytest.approx(80 / 99)

    def test_a_ledgered_mutant_that_is_no_longer_surviving_is_not_excluded(self) -> None:
        score, excluded = compute_score(
            total=100, killed=80, ledger_ids={"now_killed"}, survived_ids=set()
        )
        assert excluded == 0
        assert score == pytest.approx(0.80)

    def test_an_empty_ledger_scores_against_the_raw_total(self) -> None:
        score, excluded = compute_score(total=10, killed=8, ledger_ids=set(), survived_ids=set())
        assert excluded == 0
        assert score == pytest.approx(0.80)

    def test_excluding_every_mutant_raises_rather_than_dividing_by_zero(self) -> None:
        with pytest.raises(ValueError, match=r"no mutants left to score"):
            compute_score(total=1, killed=0, ledger_ids={"only_one"}, survived_ids={"only_one"})
