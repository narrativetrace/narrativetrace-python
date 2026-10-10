# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The framework table (Phase 6 D1): one registry of which frameworks NarrativeTrace integrates
with, how a project proves it uses one, which distribution it adds, how that is wired, and which
doctor check watches the wiring. Row ids and check ids are a cross-port contract."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from narrativetrace_tooling.frameworks.evidence import UsesName
from narrativetrace_tooling.frameworks.table import (
    NO_TIER_B_CASE,
    ROWS,
    FrameworkRow,
    IntegrationModule,
    Marker,
    NoCheck,
    NoIntegration,
    Snippet,
    WiringCheck,
    detected,
    row,
    wiring_check_ids,
)


def _snippet() -> Snippet:
    return Snippet("x wired", "a/b.py", "wiring", (UsesName("X"),), "nothing is traced")


class TestTheRows:
    def test_the_rows_in_order(self) -> None:
        assert [r.id for r in ROWS] == [
            "pytest",
            "asgi",
            "opentelemetry",
            "structlog",
            "default-logger",
            "flask",
            "django",
        ]

    def test_the_wiring_check_ids_in_order(self) -> None:
        assert wiring_check_ids() == (
            "config.pytest-fixture",
            "config.asgi-middleware",
            "config.otel-listener",
            "config.structlog-processor",
            "config.flask-integration",
            "config.django-integration",
        )

    def test_the_default_logger_row_says_why_no_check_watches_it(self) -> None:
        binding = row("default-logger").check
        assert isinstance(binding, NoCheck)
        assert binding.reason.startswith("runtime-only")

    @pytest.mark.parametrize("framework", ["flask", "django"])
    def test_a_framework_with_no_integration_shipped_adds_nothing(self, framework: str) -> None:
        r = row(framework)
        assert r.module is None
        assert isinstance(r.wiring, NoIntegration)

    def test_the_asgi_row_names_its_tier_b_case_and_no_other_row_does(self) -> None:
        cases = {r.id: r.tier_b_case for r in ROWS if r.tier_b_case != NO_TIER_B_CASE}
        assert cases == {"asgi": "init-prompt-fastapi-project"}

    def test_every_snippet_fixture_exists_in_this_repository(self) -> None:
        root = next(p for p in Path(__file__).resolve().parents if (p / "uv.lock").is_file())
        for r in ROWS:
            if isinstance(r.wiring, Snippet):
                assert (root / r.wiring.fixture).is_file(), r.id

    def test_an_unknown_row_id_raises_naming_it(self) -> None:
        with pytest.raises(KeyError, match=r"\A'no framework row nope'\Z"):
            row("nope")


class TestDetection:
    def test_a_declared_marker_distribution_detects_the_row(self) -> None:
        assert detected(row("asgi"), frozenset({"starlette"}))
        assert detected(row("asgi"), frozenset({"fastapi"}))

    def test_an_undeclared_framework_is_not_detected(self) -> None:
        assert not detected(row("asgi"), frozenset({"flask", "pytest"}))

    def test_a_row_with_no_manifest_marker_is_never_detected(self) -> None:
        assert not detected(row("default-logger"), frozenset({"structlog", "pytest"}))

    def test_a_row_stands_down_while_a_row_it_defers_to_is_detected(self) -> None:
        deferring = FrameworkRow(
            "child",
            "Child",
            Marker("c", ("c",), ("asgi",)),
            None,
            NoIntegration("none"),
            WiringCheck("config.child-integration"),
            NO_TIER_B_CASE,
        )
        assert detected(deferring, frozenset({"c"}))
        assert not detected(deferring, frozenset({"c", "fastapi"}))

    def test_deferring_to_an_id_the_table_lacks_is_an_error_not_a_silent_pass(self) -> None:
        typo = FrameworkRow(
            "child",
            "Child",
            Marker("c", ("c",), ("asgii",)),
            None,
            NoIntegration("none"),
            WiringCheck("config.child-integration"),
            NO_TIER_B_CASE,
        )
        with pytest.raises(KeyError, match="asgii"):
            detected(typo, frozenset({"c"}))


class TestIntegrationModule:
    def test_referenced_by_its_own_distribution_normalized(self) -> None:
        module = IntegrationModule("narrativetrace-asgi")
        assert module.referenced_in(frozenset({"narrativetrace-asgi"}))
        assert not module.referenced_in(frozenset({"narrativetrace", "narrativetrace-asgix"}))

    def test_the_add_instruction_pins_the_projects_version(self) -> None:
        assert (
            IntegrationModule("narrativetrace-asgi").add_instruction("0.2.0")
            == 'uv add "narrativetrace-asgi==0.2.0"'
        )

    def test_a_dev_module_is_added_as_a_dev_dependency(self) -> None:
        assert (
            IntegrationModule("narrativetrace-pytest", dev=True).add_instruction("0.2.0")
            == 'uv add --dev "narrativetrace-pytest==0.2.0"'
        )


class TestRowContract:
    def test_a_row_id_is_kebab_case(self) -> None:
        with pytest.raises(ValueError, match=r"\Aa row id is kebab-case, got 'Bad_Id'\Z"):
            FrameworkRow(
                "Bad_Id",
                "X",
                Marker("x", ()),
                IntegrationModule("narrativetrace-x"),
                _snippet(),
                WiringCheck("config.x-y"),
                NO_TIER_B_CASE,
            )

    def test_a_row_names_its_framework(self) -> None:
        with pytest.raises(ValueError, match=r"\Arow x names no framework\Z"):
            FrameworkRow(
                "x",
                " ",
                Marker("x", ()),
                IntegrationModule("narrativetrace-x"),
                _snippet(),
                WiringCheck("config.x-y"),
                NO_TIER_B_CASE,
            )

    def test_a_row_names_a_tier_b_case_or_none(self) -> None:
        with pytest.raises(ValueError, match=r"\Arow x names a Tier B case or none\Z"):
            FrameworkRow(
                "x",
                "X",
                Marker("x", ()),
                IntegrationModule("narrativetrace-x"),
                _snippet(),
                WiringCheck("config.x-y"),
                "",
            )

    @pytest.mark.parametrize(
        "check_id", ["config.x", "x.y-z", "config.X-y", "config.x-", "config.-x", "config.x--y"]
    )
    def test_a_wiring_check_id_is_config_framework_thing(self, check_id: str) -> None:
        message = re.escape(f"a framework check id is config.<framework>-<thing>, got {check_id!r}")
        with pytest.raises(ValueError, match=rf"\A{message}\Z"):
            WiringCheck(check_id)

    def test_no_integration_means_no_module_and_the_other_way_round(self) -> None:
        with pytest.raises(ValueError, match=r"\Arow x: no integration shipped adds no module\Z"):
            FrameworkRow(
                "x",
                "X",
                Marker("x", ()),
                IntegrationModule("narrativetrace-x"),
                NoIntegration("none"),
                WiringCheck("config.x-y"),
                NO_TIER_B_CASE,
            )
        with pytest.raises(ValueError, match=r"\Arow x adds no module but ships wiring\Z"):
            FrameworkRow(
                "x",
                "X",
                Marker("x", ()),
                None,
                _snippet(),
                WiringCheck("config.x-y"),
                NO_TIER_B_CASE,
            )

    def test_a_snippet_needs_evidence_the_doctor_can_look_for(self) -> None:
        with pytest.raises(ValueError, match=r"\Asource wiring needs evidence the doctor"):
            Snippet("x", "a.py", "wiring", (), "nothing is traced")

    def test_a_marker_describes_itself(self) -> None:
        with pytest.raises(ValueError, match=r"\Aa marker's description must not be blank\Z"):
            Marker("  ", ("x",))
