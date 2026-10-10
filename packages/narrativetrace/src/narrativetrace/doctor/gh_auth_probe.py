# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Asks an already-installed ``gh`` whether it is signed in — the one question that decides whether
the ``gh`` channel of ``narrativetrace feedback`` is offered at all.

Ports Java ``GhAuthProbe``. INTENT: ``gh issue create`` is the convenience path (design D1), and
offering it to somebody who has no ``gh``, or an unauthenticated one, is offering them an error
message. ``gh auth status`` answers exactly that question using that tool's own credential; this
launcher holds none and never will.

**@llmNote** This probe is the ONLY outward-facing thing the ``narrativetrace`` process causes, and
it causes it indirectly: ``gh`` validates its token against the host. That is the user's tool making
the user's call. The launcher still makes no request of its own, holds no credential and files
nothing — which is the invariant this note exists to keep honest.

**@llmNote** THE PROBE BELONGS TO EXACTLY ONE ENTRY POINT (cross-port item 4). This runtime has one
— the ``narrativetrace`` console script — and that is where it lives. A second copy anywhere (the
``narrativetrace-approve`` script, a pytest plugin hook, a skill's own shell line) would be a second
thing to keep true about whether the channel is open.

**@llmNote** Absence, a non-zero exit, a timeout and a platform that cannot start a process all
answer the SAME way: not available. An unavailable channel is a fact, never an error — the verb says
"use the URL instead" and exits 1.

**@llmNote** :class:`Probe` is the seam, for the same reason
:class:`~narrativetrace.doctor.cli_bin.CliDeps` is one: the DECISION — which outcomes mean "signed
in" — is the part worth testing, and testing it by installing a tool is testing the machine instead.
:func:`_gh_auth_status` is the one function that touches a real process, and every test of the
decision drives a fake that starts nothing.

**@sideEffects** Starts one short-lived subprocess, with its output discarded.
"""

from __future__ import annotations

import subprocess  # nosec B404 - one fixed argv, no shell; see _gh_auth_status
from collections.abc import Callable
from typing import Final, Protocol

TIMEOUT_SECONDS: Final = 10.0
"""Long enough for a token check, short enough that nobody waits on a wedged network."""

_ARGV: Final = ("gh", "auth", "status")
"""A fixed argv of three literals — nothing a project, a flag or a report can reach, which is what
makes this safe to have at all."""


class Process(Protocol):
    """The three things the decision needs from a started process. A :class:`subprocess.Popen`
    satisfies this; so does a test fake that starts nothing."""

    returncode: int | None

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


Probe = Callable[[], Process]
"""Starts the probe's process. The real one runs ``gh auth status``; a test fakes it."""


def gh_authenticated(probe: Probe | None = None) -> bool:
    """Whether ``gh`` is present AND signed in. Any doubt answers ``False``.

    :param probe: the seam — omit it for the real ``gh auth status``
    """
    start = probe if probe is not None else _gh_auth_status
    try:
        process = start()
    except OSError:
        return False
    return _exited_clean(process)


def _exited_clean(process: Process) -> bool:
    """Whether the started process said yes before the timeout. A timeout is killed rather than
    left behind: a wedged ``gh`` holding a terminal is worse than an unavailable channel."""
    try:
        return process.wait(timeout=TIMEOUT_SECONDS) == 0
    except subprocess.TimeoutExpired:
        process.kill()
        return False
    except OSError:
        return False


def _gh_auth_status() -> Process:  # pragma: no cover - would start a process; see this module
    """The real probe: ``gh auth status``, output discarded, no shell.

    The ONE function here no test executes, on purpose: cross-port item 4 is "all four outcomes
    tested and NO PROCESS STARTED IN A TEST", and a container with no ``gh`` and a laptop with a
    signed-in one would disagree about whether the suite passes. What CAN be asserted about this
    line is asserted — that :data:`_ARGV` is three literals, that both streams are discarded, that
    no shell is involved — by reading this module's own source in
    ``tests/doctor/test_gh_auth_probe.py``. It was also exercised for real, once, by hand: the
    ``gh`` channel on a container without ``gh`` printed the unavailable message and exited 1.
    """
    return subprocess.Popen(  # nosec B603 - fixed argv of literals, shell=False, output discarded
        _ARGV,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
