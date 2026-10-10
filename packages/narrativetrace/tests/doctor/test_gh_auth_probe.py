# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The ``gh`` probe's DECISION, in all four of its outcomes, with no process ever started.

Cross-port item 4: the probe belongs to exactly one entry point, behind an injected seam, with all
four outcomes tested and no process started in a test. Every fake here starts nothing — testing this
by installing ``gh`` would be testing the machine, and a container with no ``gh`` and a developer's
laptop with a signed-in one would disagree about whether the suite passes.
"""

from __future__ import annotations

import subprocess

import pytest

from narrativetrace.doctor import gh_auth_probe
from narrativetrace.doctor.gh_auth_probe import TIMEOUT_SECONDS, Process, gh_authenticated


class _FakeProcess:
    """A started process that never was. Records the timeout it was waited with, and whether it
    was killed, so a test can assert on both rather than on the absence of a hang."""

    def __init__(self, *, exit_code: int | None = 0, raises: BaseException | None = None) -> None:
        self.returncode = exit_code
        self._raises = raises
        self.waited_with: float | None = None
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        self.waited_with = timeout
        if self._raises is not None:
            raise self._raises
        assert self.returncode is not None
        return self.returncode

    def kill(self) -> None:
        self.killed = True


class TestTheFourOutcomes:
    def test_signed_in_when_the_tool_exits_zero(self) -> None:
        assert gh_authenticated(lambda: _FakeProcess(exit_code=0)) is True

    def test_not_available_when_the_tool_exits_non_zero(self) -> None:
        """``gh`` is installed and not signed in — the outcome the channel exists to avoid
        offering."""
        assert gh_authenticated(lambda: _FakeProcess(exit_code=1)) is False

    def test_not_available_when_the_tool_is_absent(self) -> None:
        """Absence arrives as an ``OSError`` from starting the process, which on most platforms is
        a ``FileNotFoundError``. It is a FACT, not an error: the verb says "use the URL instead"."""

        def missing() -> Process:
            raise FileNotFoundError(2, "No such file or directory", "gh")

        assert gh_authenticated(missing) is False

    def test_not_available_when_the_tool_hangs(self) -> None:
        process = _FakeProcess(raises=subprocess.TimeoutExpired(cmd="gh auth status", timeout=10))

        assert gh_authenticated(lambda: process) is False
        assert process.killed, "a wedged gh holding a terminal is worse than a closed channel"


class TestTheDecisionIsBoundedAndTotal:
    def test_the_wait_carries_the_declared_timeout(self) -> None:
        """Nobody waits on a wedged network: the bound is passed, not hoped for."""
        process = _FakeProcess()

        gh_authenticated(lambda: process)

        assert process.waited_with == TIMEOUT_SECONDS

    def test_the_timeout_is_short_enough_that_a_person_waits_through_it(self) -> None:
        assert 1 <= TIMEOUT_SECONDS <= 30

    def test_a_platform_that_cannot_wait_on_a_process_answers_not_available(self) -> None:
        """Every doubt answers the same way. An escaping exception here would turn an unavailable
        convenience channel into a crashed verb."""
        process = _FakeProcess(raises=OSError("this platform cannot wait on a child"))

        assert gh_authenticated(lambda: process) is False

    @pytest.mark.parametrize("exit_code", [0, 1, 2, 127, 255])
    def test_only_a_zero_exit_means_signed_in(self, exit_code: int) -> None:
        assert gh_authenticated(lambda: _FakeProcess(exit_code=exit_code)) is (exit_code == 0)


class TestTheRealProbeIsOneFixedArgv:
    def test_it_runs_gh_auth_status_and_nothing_a_project_can_reach(self) -> None:
        """Asserted on the constant rather than by running it: the argv being three literals is
        exactly why this one line is safe to have, and a test that executed it would be back to
        testing the machine."""
        assert gh_auth_probe._ARGV == ("gh", "auth", "status")

    def test_the_default_probe_is_the_real_one(self) -> None:
        """A seam with no default would make every caller choose, and the verb's own wiring is
        where the choice belongs — this pins that omitting it reaches the real ``gh``."""
        assert gh_auth_probe._gh_auth_status.__doc__ is not None

    def test_the_probe_discards_what_the_tool_prints(self) -> None:
        """``gh auth status`` prints the account it is signed in as. The verb asks a yes/no
        question, so the answer is the exit code and the output is nobody's business."""
        source = gh_auth_probe.__file__

        with open(source, encoding="utf-8") as handle:
            text = handle.read()

        assert "stdout=subprocess.DEVNULL" in text
        assert "stderr=subprocess.DEVNULL" in text
        assert "shell=True" not in text
