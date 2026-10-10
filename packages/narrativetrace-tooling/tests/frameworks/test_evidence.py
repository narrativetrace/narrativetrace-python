# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What in a project's Python source proves a row's wiring was applied. Read with :mod:`ast`, so an
import, a comment or a string naming the thing is never mistaken for using it."""

from __future__ import annotations

import pytest

from narrativetrace_tooling.frameworks.evidence import RequestsFixture, UsesName, is_test_source


class TestUsesName:
    @pytest.mark.parametrize(
        "source",
        [
            "app.add_middleware(NarrativeTraceMiddleware, context=context)",
            "app = NarrativeTraceMiddleware(inner, context)",
            "middleware = [Middleware(NarrativeTraceMiddleware, context=context)]",
            "import nt_asgi\napp.add_middleware(nt_asgi.NarrativeTraceMiddleware)",
        ],
    )
    def test_a_use_in_code_is_evidence(self, source: str) -> None:
        assert UsesName("NarrativeTraceMiddleware").found_in(source)

    @pytest.mark.parametrize(
        "source",
        [
            "from narrativetrace_asgi import NarrativeTraceMiddleware",
            "from narrativetrace_asgi import (\n    NarrativeTraceMiddleware,\n)",
            "# app.add_middleware(NarrativeTraceMiddleware)",
            '"""Add NarrativeTraceMiddleware to the app."""',
            "app.add_middleware(NarrativeTraceMiddlewareX)",
            "app.add_middleware(MyNarrativeTraceMiddleware)",
        ],
    )
    def test_an_import_a_comment_a_string_or_a_near_miss_name_is_not(self, source: str) -> None:
        assert not UsesName("NarrativeTraceMiddleware").found_in(source)

    @pytest.mark.parametrize("source", ["def broken(:\n", "\x00", "(" * 200_000])
    def test_a_file_that_does_not_parse_is_no_evidence_and_no_crash(self, source: str) -> None:
        assert not UsesName("NarrativeTraceMiddleware").found_in(source)

    def test_an_assignment_target_alone_is_not_a_use(self) -> None:
        assert not UsesName("narrative_context_processor").found_in(
            "narrative_context_processor = None"
        )


class TestRequestsFixture:
    @pytest.mark.parametrize(
        "source",
        [
            "def test_it(narrative_trace):\n    pass",
            "async def test_it(db, *, narrative_trace):\n    pass",
            "class TestX:\n    def test_it(self, narrative_trace):\n        pass",
            '@pytest.mark.usefixtures("narrative_trace")\ndef test_it():\n    pass',
            'def test_it(request):\n    request.getfixturevalue("narrative_trace")',
        ],
    )
    def test_a_test_requesting_the_fixture_is_evidence(self, source: str) -> None:
        assert RequestsFixture("narrative_trace").found_in(source)

    @pytest.mark.parametrize(
        "source",
        [
            "# def test_it(narrative_trace): pass",
            'NAME = "narrative_trace"',
            "def test_it(narrative_trace_other):\n    pass",
            'print("narrative_trace")',
        ],
    )
    def test_a_comment_a_bare_string_or_a_near_miss_is_not(self, source: str) -> None:
        assert not RequestsFixture("narrative_trace").found_in(source)


class TestIsTestSource:
    @pytest.mark.parametrize(
        "path",
        [
            "test_app.py",
            "pkg/app_test.py",
            "conftest.py",
            "tests/helpers.py",
            "src/test/factory.py",
            "tests\\unit\\builders.py",
        ],
    )
    def test_pytests_own_conventions_are_test_sources(self, path: str) -> None:
        assert is_test_source(path)

    @pytest.mark.parametrize(
        "path", ["app.py", "contest/app.py", "latest/app.py", "testing/app.py", "attest.py"]
    )
    def test_a_near_miss_is_application_source(self, path: str) -> None:
        assert not is_test_source(path)
