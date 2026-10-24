# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""List 2 of the instrumentation exclusions: the configurable, module-named list with a shipped
default. Parsing, precedence, reporting and every attachment surface carrying the same key."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from narrativetrace.config import ConfigResolver
from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.exclusions import DEFAULT_EXCLUDE, ExcludedModules, _configured
from narrativetrace.trace_object import trace_object

_CWD_AT_COLLECTION = os.getcwd()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NARRATIVETRACE_EXCLUDE", raising=False)
    # Config discovery reads `Path.cwd()`; fake it, never a real chdir (see the B-141 test below).
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    # The configured list is cached per real `os.getcwd()`, which no longer moves per test.
    _configured.cache_clear()


@pytest.fixture
def ctx() -> ContextVarNarrativeContext:
    return ContextVarNarrativeContext()


def _service_in(module_name: str) -> object:
    """An instance of a business-shaped class whose type claims ``module_name``."""

    class Service:
        def work(self) -> int:
            return 1

    Service.__module__ = module_name
    return Service()


def test_no_test_here_moves_the_process_off_its_working_directory() -> None:
    """B-141: a real ``chdir`` starves mutmut's trampoline, which re-resolves its relative
    ``source_paths`` against the live cwd on every call into mutated code, so the mutation gate
    collected no stats. Config discovery is steered by faking ``Path.cwd()``, never by a chdir."""
    assert os.getcwd() == _CWD_AT_COLLECTION


class TestParsing:
    def test_prefixes_split_on_semicolons_and_trim(self) -> None:
        assert ExcludedModules.parse(" a.b ; c ").prefixes == ("a.b", "c")

    @pytest.mark.parametrize("spelled", ["a.b.*", "a.b.**", "a.b."])
    def test_a_trailing_wildcard_or_dot_means_the_package_and_its_children(
        self, spelled: str
    ) -> None:
        assert ExcludedModules.parse(spelled).prefixes == ("a.b",)

    def test_an_empty_value_is_an_empty_list(self) -> None:
        assert ExcludedModules.parse("").prefixes == ()

    def test_empty_entries_between_semicolons_are_dropped(self) -> None:
        assert ExcludedModules.parse("a;;b;").prefixes == ("a", "b")

    @pytest.mark.parametrize("bad", ["a b", "a..b", "1a", "a-b", "a/b", "*"])
    def test_an_entry_that_is_not_a_dotted_module_name_is_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match=r"\Aexclude entry .* is not a dotted module name\Z"):
            ExcludedModules.parse(bad)

    @pytest.mark.parametrize("value", ["a.b;a.b", "a.b;a.b.*", " a.b ; a.b."])
    def test_a_prefix_given_twice_is_rejected(self, value: str) -> None:
        with pytest.raises(ValueError, match=r"\Aexclude lists a.b more than once\Z"):
            ExcludedModules.parse(value)


class TestMatching:
    def test_a_module_equal_to_a_prefix_matches(self) -> None:
        assert ExcludedModules.parse("acme.mocks").match("acme.mocks") == "acme.mocks"

    def test_a_submodule_matches(self) -> None:
        assert ExcludedModules.parse("acme.mocks").match("acme.mocks.deep") == "acme.mocks"

    def test_a_sibling_sharing_the_prefix_text_does_not_match(self) -> None:
        assert ExcludedModules.parse("acme.mocks").match("acme.mocksx") is None

    def test_a_parent_of_the_prefix_does_not_match(self) -> None:
        assert ExcludedModules.parse("acme.mocks").match("acme") is None

    def test_none_and_empty_module_never_match(self) -> None:
        excluded = ExcludedModules.parse("acme")
        assert excluded.match(None) is None
        assert excluded.match("") is None


class TestDefault:
    def test_the_shipped_default_is_what_an_absent_key_resolves_to(self) -> None:
        assert ExcludedModules.resolve(ConfigResolver()).prefixes == DEFAULT_EXCLUDE

    def test_the_default_names_the_mocking_library_and_the_test_runner(self) -> None:
        assert {"unittest", "pytest", "_pytest"} <= set(DEFAULT_EXCLUDE)

    def test_every_default_entry_is_a_valid_unique_prefix(self) -> None:
        assert ExcludedModules.parse(";".join(DEFAULT_EXCLUDE)).prefixes == DEFAULT_EXCLUDE


class TestResolution:
    def test_an_explicit_value_replaces_the_default_rather_than_extending_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NARRATIVETRACE_EXCLUDE", "acme.mocks")
        assert ExcludedModules.resolve(ConfigResolver()).prefixes == ("acme.mocks",)

    def test_an_empty_environment_value_disables_the_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NARRATIVETRACE_EXCLUDE", "")
        assert ExcludedModules.resolve(ConfigResolver()).prefixes == ()

    def test_narrativetrace_toml_carries_the_key(self, tmp_path: Path) -> None:
        (tmp_path / "narrativetrace.toml").write_text('exclude = "acme.mocks;acme.fakes"\n')
        assert ExcludedModules.resolve(ConfigResolver(tmp_path)).prefixes == (
            "acme.mocks",
            "acme.fakes",
        )

    def test_narrativetrace_toml_accepts_an_array(self, tmp_path: Path) -> None:
        (tmp_path / "narrativetrace.toml").write_text('exclude = ["acme.mocks", "acme.fakes"]\n')
        assert ExcludedModules.resolve(ConfigResolver(tmp_path)).prefixes == (
            "acme.mocks",
            "acme.fakes",
        )

    def test_pyproject_carries_the_key(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[tool.narrativetrace]\nexclude = "acme.mocks"\n')
        assert ExcludedModules.resolve(ConfigResolver(tmp_path)).prefixes == ("acme.mocks",)

    def test_the_environment_beats_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "narrativetrace.toml").write_text('exclude = "from.file"\n')
        monkeypatch.setenv("NARRATIVETRACE_EXCLUDE", "from.env")
        assert ExcludedModules.resolve(ConfigResolver(tmp_path)).prefixes == ("from.env",)

    def test_a_malformed_value_raises_when_resolved_directly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NARRATIVETRACE_EXCLUDE", "not a module")
        with pytest.raises(ValueError):
            ExcludedModules.resolve(ConfigResolver())


class TestTraceObject:
    def test_an_included_and_excluded_target_is_not_traced(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        service = _service_in("acme.mocks.fake")
        proxy = trace_object(service, ctx, exclude="acme.mocks")
        assert proxy is service
        proxy.work()  # type: ignore[attr-defined]
        assert ctx.capture_trace().is_empty

    def test_a_target_outside_every_prefix_is_traced(self, ctx: ContextVarNarrativeContext) -> None:
        trace_object(_service_in("acme.billing"), ctx, exclude="acme.mocks").work()  # type: ignore[attr-defined]
        assert [n.signature.method_name for n in ctx.capture_trace().roots] == ["work"]

    def test_a_sibling_sharing_the_prefix_text_is_traced(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        trace_object(_service_in("acme.mocksx"), ctx, exclude="acme.mocks").work()  # type: ignore[attr-defined]
        assert [n.signature.method_name for n in ctx.capture_trace().roots] == ["work"]

    def test_the_explicit_option_replaces_the_default(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        service = _service_in("unittest.mock")
        trace_object(service, ctx, exclude="").work()  # type: ignore[attr-defined]
        assert [n.signature.method_name for n in ctx.capture_trace().roots] == ["work"]

    def test_the_shipped_default_applies_when_no_option_is_given(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        service = _service_in("unittest.mock")
        assert trace_object(service, ctx) is service

    def test_a_real_mock_object_is_not_traced(self, ctx: ContextVarNarrativeContext) -> None:
        target = mock.MagicMock()
        assert trace_object(target, ctx) is target

    def test_the_environment_key_reaches_trace_object(
        self, ctx: ContextVarNarrativeContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("NARRATIVETRACE_EXCLUDE", "acme.billing")
        service = _service_in("acme.billing")
        assert trace_object(service, ctx) is service

    def test_a_config_file_key_reaches_trace_object(
        self, ctx: ContextVarNarrativeContext, tmp_path: Path
    ) -> None:
        (tmp_path / "narrativetrace.toml").write_text('exclude = "acme.billing"\n')
        service = _service_in("acme.billing")
        assert trace_object(service, ctx) is service

    def test_a_malformed_explicit_option_raises_before_any_work(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        with pytest.raises(ValueError):
            trace_object(_service_in("acme"), ctx, exclude="not a module")

    def test_a_malformed_configured_value_never_throws_into_the_host(
        self,
        ctx: ContextVarNarrativeContext,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("NARRATIVETRACE_EXCLUDE", "not a module")
        service = _service_in("unittest.mock")
        assert trace_object(service, ctx) is service  # fell back to the shipped default
        assert "not a dotted module name" in capsys.readouterr().err

    def test_two_competing_config_files_never_throw_into_the_host(
        self,
        ctx: ContextVarNarrativeContext,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (tmp_path / "narrativetrace.toml").write_text('exclude = "acme.billing"\n')
        (tmp_path / "pyproject.toml").write_text('[tool.narrativetrace]\nexclude = "acme"\n')
        service = _service_in("unittest.mock")
        assert trace_object(service, ctx) is service  # the shipped default applied
        assert "Found competing NarrativeTrace configuration" in capsys.readouterr().err

    def test_an_excluded_module_object_is_accepted_as_the_option(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        service = _service_in("acme.mocks")
        assert trace_object(service, ctx, exclude=ExcludedModules.parse("acme.mocks")) is service

    def test_a_sequence_of_prefixes_is_accepted_as_the_option(
        self, ctx: ContextVarNarrativeContext
    ) -> None:
        service = _service_in("acme.fakes")
        assert trace_object(service, ctx, exclude=["acme.mocks", "acme.fakes"]) is service


class TestReporting:
    def test_one_line_per_matched_prefix_not_per_target(
        self, ctx: ContextVarNarrativeContext, capsys: pytest.CaptureFixture[str]
    ) -> None:
        excluded = ExcludedModules.parse("acme.mocks;acme.fakes;acme.never")
        for module in ("acme.mocks.a", "acme.mocks.b", "acme.fakes", "acme.mocks"):
            trace_object(_service_in(module), ctx, exclude=excluded)
        lines = capsys.readouterr().err.splitlines()
        assert len(lines) == 2
        assert "acme.mocks" in lines[0]
        assert "acme.fakes" in lines[1]

    def test_the_line_names_the_class_the_prefix_and_what_happens(
        self, ctx: ContextVarNarrativeContext, capsys: pytest.CaptureFixture[str]
    ) -> None:
        trace_object(_service_in("acme.mocks.a"), ctx, exclude=ExcludedModules.parse("acme.mocks"))
        assert capsys.readouterr().err == (
            "narrativetrace: cannot trace acme.mocks.a.Service (excluded module acme.mocks); "
            "its calls run untraced\n"
        )

    def test_a_target_that_is_not_excluded_reports_nothing(
        self, ctx: ContextVarNarrativeContext, capsys: pytest.CaptureFixture[str]
    ) -> None:
        trace_object(_service_in("acme.billing"), ctx, exclude="acme.mocks")
        assert capsys.readouterr().err == ""

    def test_a_closed_stderr_never_breaks_the_host(
        self, ctx: ContextVarNarrativeContext, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Closed:
            def write(self, _text: str) -> int:
                raise ValueError("I/O operation on closed file")

            def flush(self) -> None:
                raise ValueError("I/O operation on closed file")

        monkeypatch.setattr(sys, "stderr", Closed())
        service = _service_in("acme.mocks")
        assert trace_object(service, ctx, exclude="acme.mocks") is service

    def test_a_module_less_type_is_traced(self, ctx: ContextVarNarrativeContext) -> None:
        service = _service_in("acme")
        type(service).__module__ = None  # type: ignore[assignment]
        trace_object(service, ctx, exclude="acme").work()  # type: ignore[attr-defined]
        assert [n.signature.method_name for n in ctx.capture_trace().roots] == ["work"]
