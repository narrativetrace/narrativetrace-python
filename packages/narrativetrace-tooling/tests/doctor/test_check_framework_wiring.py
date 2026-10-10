# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``config.<framework>-*`` — one generic check per framework-table row (Phase 6 D3): detected but
not referenced fails, referenced but never wired fails, a project that uses neither passes, and a
framework with no integration shipped is reported, never guessed at. The fix the doctor prints is
the fix the doctor accepts (cross-port item 3): every row's own snippet, dropped into a project,
turns its check green."""

from __future__ import annotations

import pytest
from snapshot_factory_types import MakeSnapshot

from narrativetrace_tooling.doctor.checks.framework_wiring import (
    VERSION_PLACEHOLDER,
    framework_wiring_check,
)
from narrativetrace_tooling.doctor.doc_urls import DOC
from narrativetrace_tooling.frameworks.table import ROWS, Snippet, row, rows_with_wiring_checks
from narrativetrace_tooling.frameworks.wiring_snippets import text

_ASGI = framework_wiring_check(row("asgi"))
_FLASK = framework_wiring_check(row("flask"))


def _pyproject(*dependencies: str) -> str:
    quoted = ", ".join(f'"{d}"' for d in dependencies)
    return f"[project]\nname = 'svc'\ndependencies = [{quoted}]\n"


class TestNotDetected:
    @pytest.mark.parametrize("framework", [r for r in rows_with_wiring_checks()])
    def test_a_project_that_uses_neither_passes(self, make_snapshot: MakeSnapshot, framework):  # type: ignore[no-untyped-def]
        finding = framework_wiring_check(framework)(make_snapshot())
        assert finding.status == "pass"
        assert finding.message == f"{framework.name} not detected — nothing to wire"


class TestDetectedNotReferenced:
    def test_fails_and_the_fix_adds_the_module_pinned_then_wires_it(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            source_files={"pyproject.toml": _pyproject("fastapi")}, narrativetrace_version="0.2.0"
        )

        finding = _ASGI(snapshot)

        assert finding.status == "fail"
        assert finding.id == "config.asgi-middleware"
        assert finding.message == (
            "FastAPI / Starlette (ASGI) detected (a fastapi or starlette dependency) but "
            "narrativetrace-asgi is not referenced — no request is traced"
        )
        assert finding.fix == (
            'Add narrativetrace-asgi: uv add "narrativetrace-asgi==0.2.0". Then add '
            "NarrativeTraceMiddleware on the ASGI app, with an exporter, adapted to this "
            "project's own app and services (from packages/narrativetrace-asgi/tests/"
            "asgi_wiring.py):\n" + text("asgi")
        )
        assert finding.doc_url == DOC["framework_table"]
        assert finding.skill == "add-narrative-tracing"

    def test_a_project_resolving_no_release_gets_the_placeholder_not_a_guess(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(source_files={"pyproject.toml": _pyproject("starlette")})
        assert f'"narrativetrace-asgi=={VERSION_PLACEHOLDER}"' in _ASGI(snapshot).fix

    def test_a_dev_module_is_added_with_dev(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(
            source_files={"pyproject.toml": _pyproject("pytest")}, narrativetrace_version="0.2.0"
        )
        finding = framework_wiring_check(row("pytest"))(snapshot)
        assert finding.fix.startswith(
            'Add narrativetrace-pytest: uv add --dev "narrativetrace-pytest==0.2.0". Then'
        )

    def test_a_manifest_above_the_walked_tree_is_not_read(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        """Manifests and wiring are read over the SAME tree. A parent's pyproject found by walking
        up (a run from a subdirectory, or a directory inside a bigger project) declares frameworks
        whose wiring lives outside the walk, so reading it would fail the project for wiring the
        doctor never looked at."""
        snapshot = make_snapshot(root_pyproject={"project": {"dependencies": ["fastapi"]}})
        assert (
            _ASGI(snapshot).message == "FastAPI / Starlette (ASGI) not detected — nothing to wire"
        )


class TestReferencedNeverWired:
    def test_fails_and_the_fix_is_the_wiring_alone(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(
            source_files={
                "pyproject.toml": _pyproject("fastapi", "narrativetrace-asgi"),
                "app.py": "from narrativetrace_asgi import NarrativeTraceMiddleware\n",
            }
        )

        finding = _ASGI(snapshot)

        assert finding.status == "fail"
        assert finding.message == (
            "narrativetrace-asgi is referenced but its wiring (NarrativeTraceMiddleware on the "
            "ASGI app, with an exporter) is never applied — no request is traced"
        )
        assert finding.fix.startswith("Apply the wiring: add NarrativeTraceMiddleware on the")

    def test_referenced_without_the_framework_still_checks_the_wiring(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(source_files={"pyproject.toml": _pyproject("narrativetrace-asgi")})
        assert _ASGI(snapshot).status == "fail"

    def test_wiring_in_a_non_python_file_is_not_evidence(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(
            source_files={
                "pyproject.toml": _pyproject("fastapi", "narrativetrace-asgi"),
                "setup.cfg": "[x]\nnote = app.add_middleware(NarrativeTraceMiddleware)\n",
            }
        )
        assert _ASGI(snapshot).status == "fail"


class TestTheFixIsTheFixTheDoctorAccepts:
    @pytest.mark.parametrize(
        "framework", [r for r in rows_with_wiring_checks() if isinstance(r.wiring, Snippet)]
    )
    def test_the_rows_own_snippet_turns_its_check_green(  # type: ignore[no-untyped-def]
        self, make_snapshot: MakeSnapshot, framework
    ) -> None:
        assert framework.module is not None
        snapshot = make_snapshot(
            source_files={
                "pyproject.toml": _pyproject(
                    *framework.marker.distributions, framework.module.distribution
                ),
                "src/svc/wiring.py": text(framework.id),
            }
        )

        finding = framework_wiring_check(framework)(snapshot)

        assert finding.status == "pass", finding.message
        assert finding.message == (
            f"{framework.module.distribution} is wired: {framework.wiring.description}"
        )


class TestACommentNamingTheWiringIsNotTheWiring:
    """The row's own snippet, every line commented out (or quoted as a docstring), is a project
    that still has nothing wired. Read through :mod:`ast`, a comment is never a token — the same
    guarantee Java's comment-stripping scanner gives its text patterns."""

    @staticmethod
    def _snapshot(make_snapshot: MakeSnapshot, framework, wiring: str):  # type: ignore[no-untyped-def]
        return make_snapshot(
            source_files={
                "pyproject.toml": _pyproject(
                    *framework.marker.distributions, framework.module.distribution
                ),
                "src/svc/wiring.py": wiring,
            }
        )

    @pytest.mark.parametrize(
        "framework", [r for r in rows_with_wiring_checks() if isinstance(r.wiring, Snippet)]
    )
    def test_the_rows_own_snippet_in_comments_leaves_the_check_failing(  # type: ignore[no-untyped-def]
        self, make_snapshot: MakeSnapshot, framework
    ) -> None:
        commented = "".join(f"# {line}\n" for line in text(framework.id).splitlines())

        finding = framework_wiring_check(framework)(
            self._snapshot(make_snapshot, framework, commented)
        )

        assert finding.status == "fail"
        assert "never applied" in finding.message

    @pytest.mark.parametrize(
        "framework", [r for r in rows_with_wiring_checks() if isinstance(r.wiring, Snippet)]
    )
    def test_the_rows_own_snippet_in_a_docstring_leaves_the_check_failing(  # type: ignore[no-untyped-def]
        self, make_snapshot: MakeSnapshot, framework
    ) -> None:
        quoted = f'"""\n{text(framework.id)}\n"""\n'

        finding = framework_wiring_check(framework)(
            self._snapshot(make_snapshot, framework, quoted)
        )

        assert finding.status == "fail"

    def test_a_trailing_comment_does_not_hide_the_real_wiring_before_it(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        framework = row("asgi")
        wired = text("asgi") + "\n# NarrativeTraceMiddleware is applied above\n"

        finding = framework_wiring_check(framework)(self._snapshot(make_snapshot, framework, wired))

        assert finding.status == "pass"


class TestNoIntegrationShipped:
    def test_a_detected_framework_with_no_integration_is_reported_as_a_pass(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(source_files={"requirements.txt": "Flask==3.0\n"})

        finding = _FLASK(snapshot)

        assert finding.status == "pass"
        assert finding.id == "config.flask-integration"
        assert finding.message == (
            "Flask detected (a flask dependency) — no integration shipped; leave it alone and "
            "trace its services with trace_object"
        )
        assert finding.fix == ""


class TestConstruction:
    def test_a_row_without_a_wiring_check_has_no_check_to_build(self) -> None:
        with pytest.raises(
            ValueError, match=r"\Arow default-logger has no config\.<framework>-\* check\Z"
        ):
            framework_wiring_check(row("default-logger"))

    def test_every_row_the_table_checks_builds_a_check(self) -> None:
        built = [framework_wiring_check(r) for r in ROWS if r in rows_with_wiring_checks()]
        assert len(built) == len(rows_with_wiring_checks())
