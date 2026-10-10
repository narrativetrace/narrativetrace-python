# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Adversarial pass over Phase 6 (framework wiring, manifests, evidence, the feedback gate's
doctor-report decoding). Each test name states the behaviour a correct implementation is expected to
have; a failing test here is a finding, never a reason to weaken the assertion.

The tests build :class:`DoctorSnapshot` values directly, so they depend on no conftest fixture.
"""

from __future__ import annotations

import json

import pytest

from narrativetrace_tooling.doctor.checks.framework_wiring import framework_wiring_check
from narrativetrace_tooling.doctor.doc_urls import DOC
from narrativetrace_tooling.doctor.types import DoctorSnapshot
from narrativetrace_tooling.feedback.check import DOCTOR_REPORT_FIELD, violations
from narrativetrace_tooling.feedback.rules import EMAIL, HOME_PATH
from narrativetrace_tooling.frameworks.evidence import RequestsFixture, UsesName
from narrativetrace_tooling.frameworks.manifests import (
    declared_distributions,
    is_manifest,
    normalize,
)
from narrativetrace_tooling.frameworks.table import (
    FrameworkRow,
    IntegrationModule,
    Marker,
    NoCheck,
    NoIntegration,
    WiringCheck,
    detected,
    row,
)
from narrativetrace_tooling.frameworks.wiring_snippets import parse

_ASGI_PYPROJECT = (
    '[project]\nname = "s"\ndependencies = ["fastapi", "narrativetrace-asgi==0.2.0"]\n'
)
_PYTEST_PYPROJECT = (
    '[project]\nname = "s"\ndependencies = ["pytest"]\n'
    '[dependency-groups]\ndev = ["narrativetrace-pytest==0.2.0"]\n'
)
_PYTEST_DEV_PYPROJECT = (
    '[project]\nname = "s"\n[dependency-groups]\ndev = ["pytest", "narrativetrace-pytest==0.2.0"]\n'
)
ASGI_WIRED = "app = FastAPI()\napp.add_middleware(NarrativeTraceMiddleware, context=ctx)\n"


def _snap(files: dict[str, str], version: str | None = "0.2.0") -> DoctorSnapshot:
    return DoctorSnapshot(
        cwd="/p",
        python_version="3.12.4",
        env={},
        root_pyproject=None,
        narrativetrace_config={},
        source_files=files,
        narrativetrace_version=version,
    )


def _declared(path: str, text: str) -> frozenset[str]:
    return declared_distributions({path: text})


# --- manifests -----------------------------------------------------------------------------------


class TestManifestForms:
    def test_a_requirement_with_an_environment_marker_declares_its_name(self) -> None:
        names = _declared("requirements.txt", 'fastapi>=0.100 ; python_version >= "3.9"\n')
        assert "fastapi" in names

    def test_an_extras_bracket_declares_the_bare_distribution(self) -> None:
        names = _declared("requirements.txt", "narrativetrace-asgi[httpx,otel]==0.2.0\n")
        assert "narrativetrace-asgi" in names
        assert "httpx" not in names and "otel" not in names

    def test_a_direct_url_requirement_declares_its_name(self) -> None:
        text = "narrativetrace-asgi @ https://example.invalid/narrativetrace_asgi-0.2.0.whl\n"
        assert "narrativetrace-asgi" in _declared("requirements.txt", text)

    def test_hash_continuation_lines_declare_nothing_and_the_name_line_still_counts(self) -> None:
        text = (
            "fastapi==0.110.0 \\\n"
            "    --hash=sha256:aaaa \\\n"
            "    --hash=sha256:bbbb\n"
            "starlette==0.36.0 \\\n"
            "    --hash=sha256:cccc\n"
        )
        names = _declared("requirements.txt", text)
        assert {"fastapi", "starlette"} <= names
        assert not any("hash" in n for n in names)

    def test_a_crlf_requirements_file_declares_every_name(self) -> None:
        names = _declared("requirements.txt", "fastapi==0.1\r\nflask==2.0\r\n")
        assert {"fastapi", "flask"} <= names

    def test_a_byte_order_mark_on_requirements_txt_does_not_hide_the_first_name(self) -> None:
        names = _declared("requirements.txt", "\ufefffastapi==0.1\nflask==2.0\n")
        assert "fastapi" in names

    def test_a_byte_order_mark_on_pyproject_does_not_hide_its_dependencies(self) -> None:
        text = '\ufeff[project]\nname = "svc"\ndependencies = ["fastapi"]\n'
        assert "fastapi" in _declared("pyproject.toml", text)

    def test_uppercase_and_underscored_names_compare_as_pep_503_says(self) -> None:
        names = declared_distributions({"requirements.txt": "FastAPI_Core==1.0\n"})
        assert "fastapi-core" in names
        assert normalize("Narrative.Trace__ASGI") == "narrative-trace-asgi"

    def test_a_pipfile_package_given_as_a_table_is_declared(self) -> None:
        text = '[packages.fastapi]\nversion = "*"\nextras = ["standard"]\n'
        assert "fastapi" in _declared("Pipfile", text)

    def test_a_poetry_dependency_given_as_a_list_of_constraints_is_declared(self) -> None:
        text = (
            "[tool.poetry.dependencies]\n"
            'python = "^3.12"\n'
            'fastapi = [{version = "^0.110", python = "<3.13"}, {version = "^0.111"}]\n'
        )
        names = _declared("pyproject.toml", text)
        assert "fastapi" in names
        assert "python" not in names

    def test_a_pep_735_include_group_entry_does_not_hide_its_sibling_names(self) -> None:
        text = (
            '[dependency-groups]\ntest = ["pytest>=8", {include-group = "lint"}]\nlint = ["ruff"]\n'
        )
        names = _declared("pyproject.toml", text)
        assert {"pytest", "ruff"} <= names

    def test_a_setup_py_keyword_bound_to_a_module_variable_declares_its_names(self) -> None:
        text = 'REQUIRES = ["fastapi>=0.1"]\nsetup(name="svc", install_requires=REQUIRES)\n'
        assert "fastapi" in _declared("setup.py", text)

    def test_a_setup_cfg_marker_and_inline_comment_still_declare_the_name(self) -> None:
        text = "[options]\ninstall_requires =\n    fastapi ; python_version>'3'  # web\n"
        assert "fastapi" in _declared("setup.cfg", text)

    def test_a_dev_requirements_file_named_with_a_prefix_is_read(self) -> None:
        # Real-world name for a development requirements file; the doctor should see its names.
        assert "fastapi" in _declared("dev-requirements.txt", "fastapi==0.1\n")

    def test_a_pip_tools_requirements_in_source_file_is_read(self) -> None:
        assert "fastapi" in _declared("requirements.in", "fastapi\n")


class TestManifestPaths:
    @pytest.mark.parametrize(
        "path",
        ["deploy\\requirements.txt", "deploy\\requirements\\base.txt", "pkg\\setup.py"],
    )
    def test_a_windows_separated_manifest_path_is_a_manifest(self, path: str) -> None:
        assert is_manifest(path)

    @pytest.mark.parametrize(
        "path",
        [
            "myrequirements/base.txt",
            "requirementsX/base.txt",
            "requirements.txt.bak",
            "Pipfile.lock",
            "poetry.lock",
            "uv.lock",
            "pyproject.toml.bak",
        ],
    )
    def test_a_prefix_sharing_sibling_or_a_lock_file_is_never_read(self, path: str) -> None:
        assert not is_manifest(path)

    def test_a_requirement_under_a_requirements_directory_is_read_by_its_own_name(self) -> None:
        assert "fastapi" in _declared("requirements/prod.txt", "fastapi==0.1\n")


# --- evidence ------------------------------------------------------------------------------------


class TestEvidenceForms:
    def test_an_aliased_import_used_under_its_alias_is_evidence_of_wiring(self) -> None:
        source = (
            "from narrativetrace_asgi import NarrativeTraceMiddleware as M\napp.add_middleware(M)\n"
        )
        assert UsesName("NarrativeTraceMiddleware").found_in(source)

    def test_an_alias_assignment_that_reads_the_name_is_evidence(self) -> None:
        source = (
            "from narrativetrace_asgi import NarrativeTraceMiddleware\n"
            "M = NarrativeTraceMiddleware\napp.add_middleware(M)\n"
        )
        assert UsesName("NarrativeTraceMiddleware").found_in(source)

    def test_a_name_only_in_a_parameter_annotation_is_not_evidence_of_use(self) -> None:
        source = (
            "from narrativetrace_asgi import NarrativeTraceMiddleware\n"
            "def build(mw: NarrativeTraceMiddleware) -> None:\n    pass\n"
        )
        assert not UsesName("NarrativeTraceMiddleware").found_in(source)

    def test_a_string_annotation_naming_the_middleware_is_not_evidence(self) -> None:
        source = 'def build(mw: "NarrativeTraceMiddleware") -> None:\n    pass\n'
        assert not UsesName("NarrativeTraceMiddleware").found_in(source)

    def test_a_use_inside_a_lambda_is_evidence(self) -> None:
        source = "make = lambda app: app.add_middleware(NarrativeTraceMiddleware)\n"
        assert UsesName("NarrativeTraceMiddleware").found_in(source)

    def test_a_decorator_naming_the_middleware_is_evidence(self) -> None:
        source = "@NarrativeTraceMiddleware\ndef handler():\n    pass\n"
        assert UsesName("NarrativeTraceMiddleware").found_in(source)

    def test_a_fixture_requested_by_another_fixture_is_evidence(self) -> None:
        source = "import pytest\n@pytest.fixture\ndef client(narrative_trace):\n    return 1\n"
        assert RequestsFixture("narrative_trace").found_in(source)

    def test_usefixtures_naming_the_fixture_among_several_is_evidence(self) -> None:
        source = '@pytest.mark.usefixtures("db", "narrative_trace")\ndef test_it():\n    pass\n'
        assert RequestsFixture("narrative_trace").found_in(source)


# --- table ---------------------------------------------------------------------------------------


class TestTableInvariants:
    @pytest.mark.parametrize("row_id", ["Asgi", "asgi\n", "asgi_middleware", "-asgi"])
    def test_a_row_id_that_is_not_kebab_case_is_refused(self, row_id: str) -> None:
        with pytest.raises(ValueError, match="kebab-case"):
            FrameworkRow(
                row_id,
                "X",
                Marker("a dep", ("x",)),
                None,
                NoIntegration("none"),
                NoCheck("reason"),
                "none",
            )

    def test_a_whitespace_only_framework_name_is_refused(self) -> None:
        with pytest.raises(ValueError, match="names no framework"):
            FrameworkRow(
                "x",
                "   ",
                Marker("a dep", ("x",)),
                None,
                NoIntegration("none"),
                NoCheck("reason"),
                "none",
            )

    def test_a_blank_marker_description_is_refused(self) -> None:
        with pytest.raises(ValueError, match="must not be blank"):
            Marker("   ", ("x",))

    @pytest.mark.parametrize("check_id", ["config.asgi-middleware\n", "config.asgi-middleware "])
    def test_a_wiring_check_id_with_surrounding_whitespace_is_refused(self, check_id: str) -> None:
        with pytest.raises(ValueError):
            WiringCheck(check_id)

    def test_a_marker_distribution_declared_in_any_case_still_detects_its_row(self) -> None:
        declared = declared_distributions({"requirements.txt": "FastAPI==0.1\n"})
        assert detected(row("asgi"), declared)

    def test_an_integration_is_referenced_when_its_distribution_is_declared_in_any_case(
        self,
    ) -> None:
        integration = IntegrationModule("narrativetrace-asgi")
        assert integration.referenced_in(frozenset({"narrativetrace-asgi"}))


# --- wiring snippets -----------------------------------------------------------------------------


class TestWiringSnippetResource:
    def test_a_crlf_resource_yields_bodies_without_carriage_returns(self) -> None:
        markdown = (
            "## asgi\r\n\r\n<!-- snippet: packages/x/tests/w.py region=wiring -->\r\n"
            "```python\r\napp.add_middleware(M)\r\n```\r\n"
        )
        entry = parse(markdown)["asgi"]
        assert entry.body == "app.add_middleware(M)\n"
        assert "\r" not in entry.body

    def test_a_snippet_marker_with_no_path_is_a_named_error_not_an_index_error(self) -> None:
        markdown = "## asgi\n<!-- snippet: -->\n```python\nx = 1\n```\n"
        try:
            result = parse(markdown)
        except ValueError:
            return
        assert "asgi" not in result


class TestFrameworkWiringCheck:
    def test_wiring_present_only_in_a_test_file_leaves_the_real_app_unwired(self) -> None:
        snapshot = _snap(
            {
                "pyproject.toml": _ASGI_PYPROJECT,
                "app/main.py": "app = FastAPI()\n",
                "tests/test_app.py": ASGI_WIRED,
            }
        )
        finding = framework_wiring_check(row("asgi"))(snapshot)
        assert finding.status == "fail"

    def test_wiring_in_a_file_that_does_not_parse_is_not_applied(self) -> None:
        snapshot = _snap(
            {
                "pyproject.toml": _ASGI_PYPROJECT,
                "app/main.py": ASGI_WIRED + "def broken(:\n",
            }
        )
        finding = framework_wiring_check(row("asgi"))(snapshot)
        assert finding.status == "fail"
        assert "is referenced but its wiring" in finding.message

    def test_an_integration_referenced_through_an_extra_counts_as_referenced(self) -> None:
        snapshot = _snap(
            {
                "pyproject.toml": _ASGI_PYPROJECT.replace("asgi==", "asgi[httpx]=="),
                "app/main.py": ASGI_WIRED,
            }
        )
        finding = framework_wiring_check(row("asgi"))(snapshot)
        assert finding.status == "pass"
        assert finding.message == (
            "narrativetrace-asgi is wired: NarrativeTraceMiddleware on the ASGI app, with an "
            "exporter"
        )

    def test_a_framework_detected_only_by_a_requirements_file_fails_with_the_add_line(
        self,
    ) -> None:
        snapshot = _snap({"requirements.txt": "fastapi==0.110.0\n"})
        finding = framework_wiring_check(row("asgi"))(snapshot)
        assert finding.status == "fail"
        assert finding.fix.startswith(
            'Add narrativetrace-asgi: uv add "narrativetrace-asgi==0.2.0"'
        )

    def test_an_aliased_middleware_import_wired_in_the_app_passes_the_check(self) -> None:
        snapshot = _snap(
            {
                "pyproject.toml": _ASGI_PYPROJECT,
                "app/main.py": (
                    "from narrativetrace_asgi import NarrativeTraceMiddleware as M\n"
                    "app = FastAPI()\napp.add_middleware(M, context=ctx)\n"
                ),
            }
        )
        assert framework_wiring_check(row("asgi"))(snapshot).status == "pass"

    def test_a_conftest_that_only_defines_the_fixture_does_not_wire_it(self) -> None:
        snapshot = _snap(
            {
                "pyproject.toml": _PYTEST_PYPROJECT,
                "tests/conftest.py": (
                    "import pytest\n@pytest.fixture\ndef narrative_trace():\n    return 1\n"
                ),
            }
        )
        assert framework_wiring_check(row("pytest"))(snapshot).status == "fail"

    def test_a_test_that_requests_the_pytest_fixture_wires_the_pytest_row(self) -> None:
        snapshot = _snap(
            {
                "pyproject.toml": _PYTEST_DEV_PYPROJECT,
                "tests/test_it.py": "def test_it(narrative_trace):\n    pass\n",
            }
        )
        assert framework_wiring_check(row("pytest"))(snapshot).status == "pass"

    def test_a_flask_project_gets_the_leave_it_alone_wording_from_a_requirements_file(
        self,
    ) -> None:
        snapshot = _snap({"requirements.txt": "Flask==3.0.0\n"})
        finding = framework_wiring_check(row("flask"))(snapshot)
        assert finding.status == "pass"
        assert finding.message == (
            "Flask detected (a flask dependency) — no integration shipped; leave it alone "
            "and trace its services with trace_object"
        )
        assert finding.fix == ""
        assert finding.doc_url == DOC["framework_table"]

    def test_a_django_project_detected_through_a_poetry_table_passes_with_no_fix(self) -> None:
        snapshot = _snap({"pyproject.toml": '[tool.poetry.dependencies]\ndjango = "^5.0"\n'})
        finding = framework_wiring_check(row("django"))(snapshot)
        assert finding.status == "pass"
        assert "Django detected (a django dependency)" in finding.message
        assert finding.fix == ""

    def test_an_unresolved_release_pins_the_add_line_to_the_placeholder(self) -> None:
        snapshot = _snap({"requirements.txt": "starlette==0.36.0\n"}, version=None)
        finding = framework_wiring_check(row("asgi"))(snapshot)
        assert '"narrativetrace-asgi==<your narrativetrace version>"' in finding.fix


# --- feedback doctor-report decoding -------------------------------------------------------------


def _violated(report: str) -> set[str]:
    return {v.rule.id for v in violations({DOCTOR_REPORT_FIELD: report})}


class TestDoctorReportDecoding:
    def test_an_email_used_as_a_key_of_the_doctor_report_is_refused(self) -> None:
        report = json.dumps({"alice@example.com": "ok", "findings": []})
        assert any(v.rule is EMAIL for v in violations({DOCTOR_REPORT_FIELD: report}))

    def test_an_email_nested_inside_arrays_and_objects_is_refused(self) -> None:
        report = json.dumps({"findings": [{"fix": ["add this", ["owner: a@example.com"]]}]})
        assert any(v.rule is EMAIL for v in violations({DOCTOR_REPORT_FIELD: report}))

    def test_a_truncated_doctor_report_is_read_as_text_and_its_email_is_refused(self) -> None:
        report = '{"message": "reach a@example.com"'
        assert any(v.rule is EMAIL for v in violations({DOCTOR_REPORT_FIELD: report}))

    def test_a_home_path_used_as_a_key_of_the_doctor_report_is_refused(self) -> None:
        report = json.dumps({"/home/alice/project": "ok"})
        assert any(v.rule is HOME_PATH for v in violations({DOCTOR_REPORT_FIELD: report}))

    def test_a_bare_json_string_that_is_an_email_is_refused(self) -> None:
        assert any(
            v.rule is EMAIL for v in violations({DOCTOR_REPORT_FIELD: json.dumps("a@example.com")})
        )

    def test_a_clean_doctor_report_with_a_decorator_fix_line_is_filable(self) -> None:
        report = json.dumps(
            {"findings": [{"fix": "add\n@app.get('/x')\ndef f(): ...", "status": "fail"}]}
        )
        assert violations({DOCTOR_REPORT_FIELD: report}) == ()

    def test_the_same_email_in_a_person_written_field_names_that_field(self) -> None:
        found = violations({"happened": "I saw a@example.com"})
        assert [(v.field, v.rule.id) for v in found] == [("happened", EMAIL.id)]
