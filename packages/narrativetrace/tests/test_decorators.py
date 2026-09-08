# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for the metadata decorators and error-context resolution."""

from __future__ import annotations

import pytest

from narrativetrace.decorators import (
    narrated,
    not_traced,
    on_error,
    read_method_metadata,
    resolve_error_context,
    traced,
)


class TestAttributes:
    def test_narrated(self) -> None:
        @narrated("Greeting {name}")
        def greet(name: str) -> None: ...

        assert read_method_metadata(greet).narrated_template == "Greeting {name}"

    def test_not_traced_accumulates(self) -> None:
        @not_traced("password")
        @not_traced("cvv")
        def pay(password: str, cvv: str) -> None: ...

        assert read_method_metadata(pay).not_traced_params == frozenset({"password", "cvv"})

    def test_traced_names(self) -> None:
        @traced("a", "b")
        def variadic(*args: int) -> None: ...

        assert read_method_metadata(variadic).traced_names == ("a", "b")

    def test_on_error_stacks(self) -> None:
        @on_error(KeyError, "missing key")
        @on_error(ValueError, "bad value")
        def op() -> None: ...

        errors = read_method_metadata(op).on_errors
        assert (KeyError, "missing key") in errors
        assert (ValueError, "bad value") in errors

    def test_bare_on_error_is_catch_all(self) -> None:
        @on_error("something failed")
        def op() -> None: ...

        assert read_method_metadata(op).on_errors == ((Exception, "something failed"),)

    def test_on_error_rejects_bad_args(self) -> None:
        with pytest.raises(TypeError):
            on_error(123)


class TestResolveErrorContext:
    def test_no_match_returns_none(self) -> None:
        errors = ((KeyError, "k"),)
        assert resolve_error_context(errors, ValueError(), {}) is None

    def test_matches_by_raised_type(self) -> None:
        errors = ((KeyError, "missing"), (ValueError, "bad"))
        assert resolve_error_context(errors, ValueError(), {}) == "bad"

    def test_most_specific_wins(self) -> None:
        class SpecificError(ValueError): ...

        errors = ((ValueError, "general"), (SpecificError, "specific"))
        assert resolve_error_context(errors, SpecificError(), {}) == "specific"

    def test_catch_all_matches_any(self) -> None:
        errors = ((Exception, "failed to {op}"),)
        assert resolve_error_context(errors, RuntimeError(), {"op": "charge"}) == "failed to charge"

    def test_template_resolved_against_values(self) -> None:
        errors = ((KeyError, "no {key}"),)
        assert resolve_error_context(errors, KeyError(), {"key": "order"}) == "no order"
