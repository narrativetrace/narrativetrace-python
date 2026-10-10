# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Which distributions a project DECLARES, read from its manifests the way people write them:
every ``pyproject.toml`` form (PEP 621, PEP 735 groups, uv's and Poetry's own tables),
``requirements*.txt``, ``setup.cfg``, ``setup.py`` and ``Pipfile``. Text only — never an install,
never a lockfile (a lockfile names what something ELSE pulled in, which proves nothing about what
the project uses)."""

from __future__ import annotations

import pytest

from narrativetrace_tooling.frameworks.manifests import (
    declared_distributions,
    is_manifest,
    normalize,
)


class TestNormalize:
    @pytest.mark.parametrize("raw", ["FastAPI", "fastapi", "Fast_API", "fast.api", "fast-_-api"])
    def test_follows_pep_503(self, raw: str) -> None:
        assert normalize(raw) in {"fastapi", "fast-api"}
        assert normalize(raw) == normalize(raw.lower())

    def test_separator_runs_collapse_to_one_dash(self) -> None:
        assert normalize("Open__Telemetry..API") == "open-telemetry-api"


class TestPyproject:
    def test_reads_project_dependencies_with_extras_markers_and_specifiers(self) -> None:
        text = """
[project]
dependencies = [
    "FastAPI[standard]>=0.110",
    "structlog ; python_version >= '3.12'",
    "opentelemetry_api==1.37.0",
]
"""
        assert declared_distributions({"pyproject.toml": text}) == frozenset(
            {"fastapi", "structlog", "opentelemetry-api"}
        )

    def test_reads_optional_dependencies_and_dependency_groups(self) -> None:
        text = """
[project.optional-dependencies]
web = ["starlette"]
[dependency-groups]
dev = ["pytest>=8", {include-group = "web"}]
"""
        assert declared_distributions({"pyproject.toml": text}) == frozenset(
            {"starlette", "pytest"}
        )

    def test_reads_uv_dev_dependencies(self) -> None:
        text = '[tool.uv]\ndev-dependencies = ["pytest"]\n'
        assert declared_distributions({"pyproject.toml": text}) == frozenset({"pytest"})

    def test_reads_poetry_tables_and_skips_python_itself(self) -> None:
        text = """
[tool.poetry.dependencies]
python = "^3.12"
Flask = "^3"
[tool.poetry.dev-dependencies]
pytest = "*"
[tool.poetry.group.lint.dependencies]
structlog = { version = "*" }
"""
        assert declared_distributions({"pyproject.toml": text}) == frozenset(
            {"flask", "pytest", "structlog"}
        )

    def test_build_requirements_are_not_the_projects_dependencies(self) -> None:
        text = '[build-system]\nrequires = ["hatchling", "fastapi"]\n'
        assert declared_distributions({"pyproject.toml": text}) == frozenset()

    def test_a_commented_out_dependency_is_not_declared(self) -> None:
        text = '[project]\ndependencies = [\n  # "fastapi",\n  "structlog",\n]\n'
        assert declared_distributions({"pyproject.toml": text}) == frozenset({"structlog"})

    def test_reads_every_modules_pyproject_by_file_name(self) -> None:
        files = {
            "pyproject.toml": '[project]\ndependencies = ["structlog"]\n',
            "services/api/pyproject.toml": '[project]\ndependencies = ["fastapi"]\n',
        }
        assert declared_distributions(files) == frozenset({"structlog", "fastapi"})

    def test_a_near_miss_file_name_is_not_a_manifest(self) -> None:
        files = {"notpyproject.toml": '[project]\ndependencies = ["fastapi"]\n'}
        assert declared_distributions(files) == frozenset()

    def test_an_unparseable_pyproject_declares_nothing_and_does_not_crash(self) -> None:
        assert declared_distributions({"pyproject.toml": "[project\n"}) == frozenset()

    def test_wrongly_shaped_tables_declare_nothing_and_do_not_crash(self) -> None:
        text = '[project]\ndependencies = "fastapi"\noptional-dependencies = ["x"]\n'
        assert declared_distributions({"pyproject.toml": text}) == frozenset()


class TestRequirementsFiles:
    def test_reads_names_and_skips_comments_options_and_includes(self) -> None:
        text = """
# web stack
fastapi[all]==0.110  # pinned
-r base.txt
--index-url https://example.invalid/simple
-e ./vendored/lib
structlog
   Starlette >= 0.37
"""
        assert declared_distributions({"requirements.txt": text}) == frozenset(
            {"fastapi", "structlog", "starlette"}
        )

    @pytest.mark.parametrize(
        "path", ["requirements-dev.txt", "requirements/test.txt", "src/requirements_web.txt"]
    )
    def test_every_conventional_requirements_path_is_read(self, path: str) -> None:
        assert declared_distributions({path: "fastapi\n"}) == frozenset({"fastapi"})

    @pytest.mark.parametrize(
        "path", ["notes.txt", "myrequirements.txt", "requirementsx.txt", "requirements.md"]
    )
    def test_a_txt_file_that_is_not_a_requirements_file_is_not_read(self, path: str) -> None:
        assert declared_distributions({path: "fastapi\n"}) == frozenset()

    def test_a_url_requirement_with_a_name_counts(self) -> None:
        text = "flask @ https://example.invalid/flask.whl\n"
        assert declared_distributions({"requirements.txt": text}) == frozenset({"flask"})


class TestSetupFiles:
    def test_reads_setup_cfg_install_and_extras_requires(self) -> None:
        text = """
[options]
install_requires =
    fastapi>=0.110
    # structlog
[options.extras_require]
otel = opentelemetry-api
"""
        assert declared_distributions({"setup.cfg": text}) == frozenset(
            {"fastapi", "opentelemetry-api"}
        )

    def test_an_unparseable_setup_cfg_declares_nothing(self) -> None:
        assert declared_distributions({"setup.cfg": "install_requires = fastapi"}) == frozenset()

    def test_reads_setup_py_keyword_lists(self) -> None:
        text = """
from setuptools import setup
setup(
    name="svc",
    install_requires=["fastapi>=0.110"],
    extras_require={"dev": ["pytest"]},
    tests_require=["structlog"],
)
"""
        assert declared_distributions({"setup.py": text}) == frozenset(
            {"fastapi", "pytest", "structlog"}
        )

    def test_a_setup_py_that_does_not_parse_declares_nothing(self) -> None:
        assert declared_distributions({"setup.py": "setup(install_requires=["}) == frozenset()

    def test_a_name_in_setup_py_outside_its_requirement_keywords_is_not_declared(self) -> None:
        text = 'setup(name="fastapi-demo", description="uses fastapi")\n'
        assert declared_distributions({"setup.py": text}) == frozenset()


class TestPipfile:
    def test_reads_packages_and_dev_packages(self) -> None:
        text = '[packages]\nfastapi = "*"\n[dev-packages]\npytest = "*"\n'
        assert declared_distributions({"Pipfile": text}) == frozenset({"fastapi", "pytest"})


class TestIsManifest:
    @pytest.mark.parametrize(
        "path",
        [
            "pyproject.toml",
            "svc/pyproject.toml",
            "Pipfile",
            "setup.cfg",
            "setup.py",
            "requirements.txt",
            "requirements/web.txt",
            "deploy\\requirements-prod.txt",
        ],
    )
    def test_every_form_the_reader_reads(self, path: str) -> None:
        assert is_manifest(path)

    @pytest.mark.parametrize(
        "path",
        [
            "Pipfile.lock",
            "uv.lock",
            "myrequirements.txt",
            "requirementsx.txt",
            "requirements.md",
            "setup.py.bak",
        ],
    )
    def test_a_near_miss_is_not_one(self, path: str) -> None:
        assert not is_manifest(path)
