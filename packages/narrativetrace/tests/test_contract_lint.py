# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/contract_lint.py`: schema/linkage validation of `documentation/contract.yaml`
(`slugify`/`heading_anchors`/`parse_page_ref`/`parse`/`lint`), plus the two-verdict holds/fails
decision logic (`decide`) both `contract-probe` (nightly, against a real registry) and this
module's own fixture tests below exercise.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.contract_lint import (
    ContractDocument,
    ContractEntry,
    ContractVerdict,
    decide,
    heading_anchors,
    lint,
    parse,
    parse_page_ref,
    slugify,
)

# ---- slugify / heading_anchors ------------------------------------------------------------


def test_slugify_matches_a_known_github_anchor() -> None:
    # Real anchor this repository already links to (documentation/guides/installation.md).
    assert slugify("Installation") == "installation"


def test_slugify_strips_punctuation_but_keeps_hyphens_and_underscores() -> None:
    assert slugify("`@not_traced` — redaction") == "not_traced--redaction"


def test_slugify_does_not_collapse_adjacent_separators() -> None:
    # An em dash between two words removes to nothing, leaving both surrounding spaces -- which
    # become a double hyphen. Deliberate: this is what GitHub's own renderer produces.
    assert slugify("The buffered path — capture that never blocks") == (
        "the-buffered-path--capture-that-never-blocks"
    )


def test_heading_anchors_disambiguates_repeated_slugs(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text("# Title\n## Properties\nsome text\n## Properties\n", encoding="utf-8")
    assert heading_anchors(page) == {"title", "properties", "properties-1"}


# ---- parse_page_ref -------------------------------------------------------------------------


def test_parse_page_ref_splits_path_and_anchor() -> None:
    ref = parse_page_ref("documentation/foo.md#some-anchor")
    assert ref.relative_path == "documentation/foo.md"
    assert ref.anchor == "some-anchor"


def test_parse_page_ref_requires_an_anchor() -> None:
    with pytest.raises(ValueError, match=r"<path>#<anchor>"):
        parse_page_ref("documentation/foo.md")


# ---- parse ------------------------------------------------------------------------------


def _contract_yaml(*entry_blocks: str) -> str:
    return 'version_source: "pyproject.toml#version"\nentries:\n' + "\n".join(entry_blocks)


_VALID_ENTRY_POINT_ENTRY = """\
  - id: entry-point-narrativetrace
    kind: entry-point
    registry: pypi
    coordinate: "narrativetrace"
    page: "documentation/foo.md#some-anchor"
    claim: "narrativetrace resolves on PyPI"
    documented_default: "PRESENT"
    probe: "contract-probe/src/contract_probe/probes/entry_point_probe.py"
"""


def test_parse_reads_an_entry_point_entry(tmp_path: Path) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text(_contract_yaml(_VALID_ENTRY_POINT_ENTRY), encoding="utf-8")
    document = parse(contract)
    assert document.version_source == "pyproject.toml#version"
    assert len(document.entries) == 1
    entry = document.entries[0]
    assert entry.id == "entry-point-narrativetrace"
    assert entry.kind == "entry-point"
    assert entry.coordinate == "narrativetrace"
    assert entry.expect == "PRESENT"


def test_parse_accepts_expected_effect_as_the_expect_field(tmp_path: Path) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text(
        _contract_yaml(
            """\
  - id: config-shape-example
    kind: config-shape
    page: "documentation/foo.md#some-anchor"
    claim: "an example config shape produces an effect"
    expected_effect: "field redacted"
    probe: "contract-probe/probe.py"
"""
        ),
        encoding="utf-8",
    )
    entry = parse(contract).entries[0]
    assert entry.expect == "field redacted"


def test_parse_missing_version_source_raises(tmp_path: Path) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text("entries: []", encoding="utf-8")
    with pytest.raises(ValueError, match="version_source"):
        parse(contract)


def test_parse_entry_missing_expect_field_raises(tmp_path: Path) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text(
        _contract_yaml(
            """\
  - id: broken
    kind: probed-default
    page: "documentation/foo.md#some-anchor"
    claim: "something"
    probe: "probe.py"
"""
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="documented_default"):
        parse(contract)


def test_parse_unknown_kind_raises(tmp_path: Path) -> None:
    contract = tmp_path / "contract.yaml"
    contract.write_text(
        _contract_yaml(
            """\
  - id: broken
    kind: not-a-real-kind
    page: "documentation/foo.md#some-anchor"
    claim: "something"
    documented_default: "true"
    probe: "probe.py"
"""
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown kind"):
        parse(contract)


# ---- lint -------------------------------------------------------------------------------


def _entry(
    entry_id: str = "e1",
    kind: str = "probed-default",
    page: str = "documentation/foo.md#heading",
    claim: str | None = None,
    expect: str = "true",
    probe: str = "probe.py",
    coordinate: str | None = None,
) -> ContractEntry:
    return ContractEntry(
        id=entry_id,
        kind=kind,
        page=page,
        claim=claim if claim is not None else f"claim {entry_id}",
        expect=expect,
        probe=probe,
        coordinate=coordinate,
        registry=None,
    )


def test_lint_clean_document_has_no_problems(tmp_path: Path) -> None:
    page = tmp_path / "documentation" / "foo.md"
    page.parent.mkdir(parents=True)
    page.write_text("# Foo\n## Heading\n", encoding="utf-8")
    (tmp_path / "probe.py").write_text("# probe", encoding="utf-8")

    document = ContractDocument("pyproject.toml#version", [_entry()])
    problems = lint(tmp_path, document)
    assert problems == []


def test_lint_flags_duplicate_ids(tmp_path: Path) -> None:
    page = tmp_path / "documentation" / "foo.md"
    page.parent.mkdir(parents=True)
    page.write_text("## Heading\n", encoding="utf-8")
    (tmp_path / "probe.py").write_text("# probe", encoding="utf-8")
    document = ContractDocument(
        "v", [_entry(entry_id="dup", claim="a"), _entry(entry_id="dup", claim="b")]
    )
    problems = lint(tmp_path, document)
    assert any("duplicate entry id" in p for p in problems)


def test_lint_flags_duplicate_claims(tmp_path: Path) -> None:
    page = tmp_path / "documentation" / "foo.md"
    page.parent.mkdir(parents=True)
    page.write_text("## Heading\n", encoding="utf-8")
    (tmp_path / "probe.py").write_text("# probe", encoding="utf-8")
    document = ContractDocument(
        "v",
        [
            _entry(entry_id="a", claim="same claim"),
            _entry(entry_id="b", claim="same claim"),
        ],
    )
    problems = lint(tmp_path, document)
    assert any("same claim" in p for p in problems)


def test_lint_flags_missing_probe_file(tmp_path: Path) -> None:
    page = tmp_path / "documentation" / "foo.md"
    page.parent.mkdir(parents=True)
    page.write_text("## Heading\n", encoding="utf-8")
    document = ContractDocument("v", [_entry(probe="does-not-exist.py")])
    problems = lint(tmp_path, document)
    assert any("does not exist" in p and "does-not-exist.py" in p for p in problems)


def test_lint_flags_missing_page_file(tmp_path: Path) -> None:
    (tmp_path / "probe.py").write_text("# probe", encoding="utf-8")
    document = ContractDocument("v", [_entry(page="documentation/missing.md#heading")])
    problems = lint(tmp_path, document)
    assert any('page "documentation/missing.md" does not exist' in p for p in problems)


def test_lint_flags_anchor_not_found_on_an_existing_page(tmp_path: Path) -> None:
    page = tmp_path / "documentation" / "foo.md"
    page.parent.mkdir(parents=True)
    page.write_text("## A Different Heading\n", encoding="utf-8")
    (tmp_path / "probe.py").write_text("# probe", encoding="utf-8")
    document = ContractDocument("v", [_entry(page="documentation/foo.md#heading")])
    problems = lint(tmp_path, document)
    assert any('anchor "#heading" not found' in p for p in problems)


def test_lint_flags_an_entry_point_with_no_coordinate(tmp_path: Path) -> None:
    page = tmp_path / "documentation" / "foo.md"
    page.parent.mkdir(parents=True)
    page.write_text("## Heading\n", encoding="utf-8")
    (tmp_path / "probe.py").write_text("# probe", encoding="utf-8")
    document = ContractDocument("v", [_entry(kind="entry-point")])
    problems = lint(tmp_path, document)
    assert any('entry-point requires "coordinate"' in p for p in problems)


# ---- decide ----------------------------------------------------------------


def test_decide_holds_when_observed_matches_expectation() -> None:
    outcome = decide(_entry(expect="true"), "0.2.1", "true")
    assert outcome.verdict == ContractVerdict.HOLDS


def test_decide_fails_and_names_all_four_facts_when_observed_differs() -> None:
    outcome = decide(
        _entry(
            entry_id="narrativetrace-output",
            expect="true",
            coordinate="narrativetrace",
        ),
        "0.2.2",
        "false",
    )
    assert outcome.verdict == ContractVerdict.FAILS
    assert "narrativetrace-output" in outcome.message
    assert '"true"' in outcome.message
    assert "0.2.2" in outcome.message
    assert '"false"' in outcome.message


# ---- the four historical instances this gate was built for -------------------------------
# Each fixture proves the DECISION LOGIC would have fired: a contract entry shaped like the real
# defect, paired with the probe result the real defect would have produced, run through the exact
# `decide()` `contract_check.py` uses. These are not re-runs of history (the defects are fixed);
# they pin the class of bug so a regression of the same shape is caught by this logic again,
# offline, without a release.


def test_row2_java_doc_coordinate_that_does_not_resolve_would_have_failed() -> None:
    # "docs cite 0.2.0, Central serves 0.2.1": an entry-point whose coordinate does not actually
    # resolve at the version under test reads as MISSING, never silently PRESENT.
    row2 = _entry(
        entry_id="entry-point-proxy",
        kind="entry-point",
        expect="PRESENT",
        coordinate="ai.narrativetrace:narrativetrace-proxy",
    )
    outcome = decide(row2, "0.2.0", "MISSING")
    assert outcome.verdict == ContractVerdict.FAILS


def test_row3_python_output_doc_says_true_wheel_default_false_would_have_failed() -> None:
    row3 = _entry(entry_id="output-default", kind="probed-default", expect="true")
    outcome = decide(row3, "0.1.1", "false")
    assert outcome.verdict == ContractVerdict.FAILS
    assert 'documented default "true"' in outcome.message
    assert 'reads "false"' in outcome.message


def test_row4_dotnet_doc_committed_after_publish_still_off_would_have_failed() -> None:
    # The doc author believed the config was already on; probing the PUBLISHED package directly
    # (never what the commit believed) is what catches it regardless of intent.
    row4 = _entry(entry_id="proxy-options-redaction", kind="probed-default", expect="true")
    outcome = decide(row4, "0.1.3", "false")
    assert outcome.verdict == ContractVerdict.FAILS


def test_row5_typescript_config_example_silent_no_op_would_have_failed() -> None:
    # The documented shape, applied to the published package, produces no such effect.
    row5 = _entry(
        entry_id="trace-object-methods",
        kind="config-shape",
        expect="return value redacted",
    )
    outcome = decide(row5, "0.1.1", "no effect")
    assert outcome.verdict == ContractVerdict.FAILS
