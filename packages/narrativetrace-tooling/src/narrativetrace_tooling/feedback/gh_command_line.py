# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The exact ``gh issue create`` line that files this report — PRINTED, never run.

Ports Java ``GhCommandLine``. INTENT (design D1 as ruled): the second yes-path, offered only when
``gh`` is present AND authenticated. It saves the browser step for people who already live in that
tool, and it is a convenience rather than the foundation: ``gh`` ships on hosted runners and is
absent from most ordinary machines, which is why the pre-filled URL is the default and this is not.

**@llmNote** This library never executes the line. Running it is the user's act, in their own shell,
with their own credential — and because ``gh`` is outside the skills' closed command vocabulary, an
agent that runs it is asked for permission by its harness as well. Two independent gates, neither of
which this code can bypass by printing something.

**@llmNote** The title is single-quoted with ``'\\''`` escaping, and that is a security property,
not formatting. The step comes from a project — a test name, a check id, whatever the agent read —
and an unquoted title containing ``;`` is a second command in a line we told somebody to paste into
their shell.
"""

from __future__ import annotations

import re
from typing import Final

from narrativetrace_tooling.feedback import public_repository
from narrativetrace_tooling.feedback.report import FeedbackReport

_WHITESPACE_RUN: Final = re.compile(r"\s+")


def gh_command_line(report: FeedbackReport, body_file: str) -> str:
    """The one-line invocation.

    :param body_file: where the body was written, as the user will type it
    :raises TypeError: when ``body_file`` is ``None``
    :raises ValueError: when the report is not a Python report, or the path is blank
    """
    public_repository.require_this_runtime(report)
    if body_file is None:
        raise TypeError("the gh line files the body from a FILE, never None")
    if not body_file.strip():
        raise ValueError("the gh line files the body from a FILE — there is no line without one")
    parts = [
        "gh issue create",
        f"--repo {public_repository.SLUG}",
        f"--template {public_repository.FORM}",
        f"--title {_single_quote(_one_line(public_repository.title_for(report)))}",
        f"--body-file {body_file.strip()}",
        *(f"--label {_one_line(label)}" for label in public_repository.labels_for(report)),
    ]
    return " ".join(parts)


def _one_line(value: str) -> str:
    """A printed command is one line: a newline inside it would be a second command."""
    return _WHITESPACE_RUN.sub(" ", value).strip()


def _single_quote(value: str) -> str:
    """POSIX single-quoting: the only quoting under which a shell interprets nothing."""
    escaped = value.replace("'", "'\\''")
    return f"'{escaped}'"
