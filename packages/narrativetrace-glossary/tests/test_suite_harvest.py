# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""One harvest run: read, merge, write back, report."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from narrativetrace_glossary import (
    BoundedContext,
    Glossary,
    GlossaryTerm,
    SynonymAlias,
    TermKind,
    TermStatus,
    write_glossary_json,
)
from narrativetrace_glossary.harvester import HarvestCandidate
from narrativetrace_glossary.suite_harvest import (
    GLOSSARY_JSON_FILE,
    GLOSSARY_MARKDOWN_FILE,
    run_suite_harvest,
)
from narrativetrace_glossary.usage_report import USAGE_REPORT_FILE


def _candidate(
    phrase: str = "overdraft account", identifier: str = "overdraft_account"
) -> HarvestCandidate:
    return HarvestCandidate(
        "billing", phrase, TermKind.NOUN_PHRASE, "OverdraftService.open", identifier
    )


def test_first_run_with_no_committed_glossary_creates_one_and_reports_no_violations(
    tmp_path: Path,
) -> None:
    result = run_suite_harvest(
        [_candidate()],
        glossary_dir=tmp_path,
        output_dir=tmp_path / "out",
        clock=lambda: date(2026, 8, 11),
    )

    assert (tmp_path / GLOSSARY_JSON_FILE).is_file()
    assert (tmp_path / GLOSSARY_MARKDOWN_FILE).is_file()
    assert len(result.merge.new_terms) == 1
    assert result.violations == ()
    assert result.issues == ()
    assert "1 new terms harvested" in result.summary
    assert (tmp_path / "out" / USAGE_REPORT_FILE).is_file()


def test_a_second_run_merges_into_the_first_and_finds_no_new_terms(tmp_path: Path) -> None:
    run_suite_harvest([_candidate()], glossary_dir=tmp_path, output_dir=tmp_path / "out")

    result = run_suite_harvest([_candidate()], glossary_dir=tmp_path, output_dir=tmp_path / "out")

    assert result.merge.new_terms == ()


def test_a_deprecated_alias_is_reported_as_a_violation_only_when_a_glossary_pre_existed(
    tmp_path: Path,
) -> None:
    canonical = GlossaryTerm(
        "overdraft account",
        "billing",
        TermKind.NOUN_PHRASE,
        TermStatus.CURATED,
        synonyms=[SynonymAlias("account with overdraft")],
        first_seen=date(2020, 1, 1),
    )
    glossary = Glossary({"billing": BoundedContext("billing", ["acme.billing"])}, [canonical])
    (tmp_path / GLOSSARY_JSON_FILE).write_text(write_glossary_json(glossary), encoding="utf-8")
    alias_candidate = HarvestCandidate(
        "billing",
        "account with overdraft",
        TermKind.NOUN_PHRASE,
        "OverdraftService.open",
        "open_v1",
    )

    result = run_suite_harvest(
        [alias_candidate], glossary_dir=tmp_path, output_dir=tmp_path / "out"
    )

    assert len(result.violations) == 1
    assert result.violations[0].canonical_term == "overdraft account"
    assert len(result.issues) == 1
    assert result.issues[0].category == "non-canonical-term"
    assert "1 deprecated synonyms in use" in result.summary


def test_write_back_is_a_pure_function_of_content_second_write_is_byte_identical(
    tmp_path: Path,
) -> None:
    run_suite_harvest([_candidate()], glossary_dir=tmp_path, output_dir=tmp_path / "out")
    first_bytes = (tmp_path / GLOSSARY_JSON_FILE).read_bytes()

    run_suite_harvest([], glossary_dir=tmp_path, output_dir=tmp_path / "out")

    assert (tmp_path / GLOSSARY_JSON_FILE).read_bytes() == first_bytes


def test_usage_report_reflects_the_run(tmp_path: Path) -> None:
    run_suite_harvest([_candidate()], glossary_dir=tmp_path, output_dir=tmp_path / "out")

    report = json.loads((tmp_path / "out" / USAGE_REPORT_FILE).read_text(encoding="utf-8"))

    assert report["newTerms"][0]["term"] == "overdraft account"
    assert report["usage"][0]["phrase"] == "overdraft account"


def test_empty_candidates_against_an_empty_project_writes_an_empty_glossary(tmp_path: Path) -> None:
    result = run_suite_harvest([], glossary_dir=tmp_path, output_dir=tmp_path / "out")

    assert result.merge.new_terms == ()
    assert result.summary == "Vocabulary: 0 new terms harvested, 0 deprecated synonyms in use"
    assert (tmp_path / GLOSSARY_JSON_FILE).is_file()
