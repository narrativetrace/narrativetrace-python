# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The capture layer says once per process that a ``*args`` catch-all cannot name its arguments.

Python reads parameter names from the signature, so the one case it cannot read is a ``*args``
catch-all: its values collapse into a single ``args: [...]`` entry. The warning names the symptom
and the fix; it never guesses names from source.
"""

from __future__ import annotations

import pytest

from narrativetrace import trace_object, traced
from narrativetrace.context import ContextVarNarrativeContext
from narrativetrace.trace_object import reset_catch_all_warning


class Gateway:
    def send(self, *args: object) -> int:
        return len(args)

    def forward(self, *args: object) -> int:
        return len(args)

    @traced("first", "second")
    def named(self, *args: object) -> int:
        return len(args)

    def plain(self, first: int, second: int) -> int:
        return first + second


@pytest.fixture(autouse=True)
def fresh_process_state() -> None:
    reset_catch_all_warning()


def _call(method: str, *args: object) -> None:
    getattr(trace_object(Gateway(), ContextVarNarrativeContext()), method)(*args)


def test_a_catch_all_method_warns_with_the_symptom_and_the_fix(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _call("send", 1, 2)

    assert capsys.readouterr().err == (
        "narrativetrace: Gateway.send takes *args, so its arguments render as one "
        'args: [...] value; name them with @traced("first", "second", ...)\n'
    )


def test_the_warning_is_once_per_process_not_once_per_method(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _call("send", 1)
    _call("send", 1)
    _call("forward", 1)

    assert capsys.readouterr().err.count("takes *args") == 1


def test_names_given_to_traced_silence_the_warning(capsys: pytest.CaptureFixture[str]) -> None:
    _call("named", 1, 2)

    assert capsys.readouterr().err == ""


def test_a_method_with_ordinary_parameters_does_not_warn(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _call("plain", 1, 2)

    assert capsys.readouterr().err == ""


def test_a_broken_stderr_never_fails_the_traced_call(monkeypatch: pytest.MonkeyPatch) -> None:
    class Closed:
        def write(self, _text: str) -> int:
            raise ValueError("I/O operation on closed file")

        def flush(self) -> None:
            raise ValueError("I/O operation on closed file")

    monkeypatch.setattr("sys.stderr", Closed())

    service = trace_object(Gateway(), ContextVarNarrativeContext())
    assert service.send(1, 2, 3) == 3
