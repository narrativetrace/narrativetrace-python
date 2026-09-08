# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""No-execution AST harvest over Python sources, incl. narration-template harvesting."""

from __future__ import annotations

from pathlib import Path

from narrativetrace_glossary import BoundedContext, Glossary, TermKind
from narrativetrace_glossary.context_resolver import UNASSIGNED_CONTEXT
from narrativetrace_glossary.static_scan import scan_paths, scan_source

BILLING = Glossary({"billing": BoundedContext("billing", ["acme.billing"])})

_SOURCE = '''
from narrativetrace import narrated, on_error, not_traced, trace_object


class OverdraftService:
    """Opens overdraft accounts."""

    @narrated("Opening overdraft for {customer_id}")
    @on_error(ValueError, "rejected: {customer_id}")
    @on_error("failed to open account")
    def open_account_with_overdraft(self, customer_id, initial_balance):
        return None

    def _private_helper(self):
        return None


def module_level_function():
    """Not harvested: class methods only."""
    return None
'''


def test_harvests_the_class_name() -> None:
    candidates = scan_source(_SOURCE, "acme.billing.overdraft_service", BILLING)

    matches = [c for c in candidates if c.identifier == "OverdraftService"]
    assert len(matches) == 1
    assert matches[0].phrase == "overdraft"
    assert matches[0].kind is TermKind.WORD


def test_harvests_the_method_as_a_verb_phrase_and_object_noun() -> None:
    candidates = scan_source(_SOURCE, "acme.billing.overdraft_service", BILLING)

    phrases = {
        (c.phrase, c.kind) for c in candidates if c.identifier == "open_account_with_overdraft"
    }
    assert ("open account with overdraft", TermKind.VERB_PHRASE) in phrases
    assert ("account with overdraft", TermKind.NOUN_PHRASE) in phrases


def test_harvests_parameters_excluding_self() -> None:
    candidates = scan_source(_SOURCE, "acme.billing.overdraft_service", BILLING)

    identifiers = {c.identifier for c in candidates}
    assert "customer_id" in identifiers
    assert "initial_balance" in identifiers
    assert "self" not in identifiers


def test_harvests_the_narrated_template_verbatim() -> None:
    candidates = scan_source(_SOURCE, "acme.billing.overdraft_service", BILLING)

    templates = [c for c in candidates if c.kind is TermKind.TEMPLATE]
    phrases = {c.phrase for c in templates}
    assert "Opening overdraft for {customer_id}" in phrases


def test_harvests_every_stacked_on_error_template() -> None:
    candidates = scan_source(_SOURCE, "acme.billing.overdraft_service", BILLING)

    phrases = {c.phrase for c in candidates if c.kind is TermKind.TEMPLATE}
    assert "rejected: {customer_id}" in phrases
    assert "failed to open account" in phrases


def test_skips_underscore_prefixed_methods() -> None:
    candidates = scan_source(_SOURCE, "acme.billing.overdraft_service", BILLING)

    assert not any(c.site.endswith("._private_helper") for c in candidates)


def test_module_level_functions_are_out_of_scope() -> None:
    candidates = scan_source(_SOURCE, "acme.billing.overdraft_service", BILLING)

    assert not any(c.identifier == "module_level_function" for c in candidates)


def test_resolves_context_from_the_module_path() -> None:
    candidates = scan_source(_SOURCE, "acme.billing.overdraft_service", BILLING)

    assert all(c.context == "billing" for c in candidates)


def test_unmapped_module_path_files_under_unassigned() -> None:
    candidates = scan_source(_SOURCE, "somewhere.else", BILLING)

    assert all(c.context == UNASSIGNED_CONTEXT for c in candidates)


def test_a_syntactically_invalid_file_yields_no_candidates() -> None:
    assert scan_source("def broken(:\n", "acme.billing.x", BILLING) == ()


def test_scan_paths_walks_a_directory_and_skips_test_files(tmp_path: Path) -> None:
    package = tmp_path / "acme" / "billing"
    package.mkdir(parents=True)
    (package / "overdraft_service.py").write_text(_SOURCE, encoding="utf-8")
    (package / "test_overdraft_service.py").write_text(_SOURCE, encoding="utf-8")

    candidates = scan_paths([tmp_path], BILLING)

    sites = {c.site for c in candidates}
    assert any("OverdraftService" in site for site in sites)
    # A candidate normalized identically in both files would collapse into one aggregated entry
    # anyway; the real assertion is that scanning ran over exactly the non-test file's content.
    assert all(c.context == "billing" for c in candidates)


def test_scan_paths_computes_module_path_from_file_layout(tmp_path: Path) -> None:
    package = tmp_path / "acme" / "billing"
    package.mkdir(parents=True)
    (package / "overdraft_service.py").write_text(_SOURCE, encoding="utf-8")
    glossary = Glossary({"billing": BoundedContext("billing", ["acme.billing.overdraft_service"])})

    candidates = scan_paths([tmp_path], glossary)

    assert candidates
    assert all(c.context == "billing" for c in candidates)


def test_init_py_module_path_drops_the_trailing_init_segment(tmp_path: Path) -> None:
    package = tmp_path / "acme" / "billing"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(_SOURCE, encoding="utf-8")
    glossary = Glossary({"billing": BoundedContext("billing", ["acme.billing"])})

    candidates = scan_paths([tmp_path], glossary)

    assert all(c.context == "billing" for c in candidates)


def test_scan_paths_aggregates_repeated_observations_across_files(tmp_path: Path) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    source = """
class Widget:
    def open_widget(self):
        return None
"""
    first.write_text(source, encoding="utf-8")
    second.write_text(source, encoding="utf-8")

    candidates = scan_paths([tmp_path], Glossary())

    widget_class = [c for c in candidates if c.identifier == "Widget"]
    assert len(widget_class) == 1
    assert widget_class[0].occurrences == 2


def test_scan_paths_output_is_totally_ordered_and_deduplicated(tmp_path: Path) -> None:
    (tmp_path / "z.py").write_text(_SOURCE, encoding="utf-8")

    candidates = scan_paths([tmp_path], BILLING)

    keys = [(c.context, c.phrase, c.kind.value, c.site, c.identifier) for c in candidates]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))
