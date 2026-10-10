# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""INTENT: the environment every command of one trial runs with, and the evidence a grader reads
afterwards -- the transcript, the recording ``gh``/``curl`` stand-ins, and their log. Ports Java's
``TrialEnvironment``.

All of it lives in a work directory OUTSIDE the scaffolded project. That is the whole point: the
agent cannot read what it is being graded on, and cannot write it either, so a transcript is
evidence rather than something the subject produced about itself. Only the grader is told where
the two files are.

**@llmNote** The stand-ins are installed on EVERY trial's PATH, not only the feedback cases'. Two
reasons, and the second is the stronger one. First, no trial can then file a real issue or reach a
network, whatever an agent decides to run: ``gh`` and ``curl`` are outside every skill's closed
command vocabulary, so nothing legitimate loses anything by it. Second, ``gh`` being merely ABSENT
makes "the agent tried to file an issue" and "the agent did not try" the same observation -- a
``command not found`` says nothing about intent, and intent is exactly what the approval gate
measures. The ``curl`` stand-in serves one host, the published site, because reading ``llms.txt``
is the product's own first instruction (Java, 2026-10-08: Haiku 5.5 refused a lossy page-tool
summary, reached for curl, hit exit 6 six times out of six and stopped -- a harness verdict).

**@sideEffects** :meth:`TrialEnvironment.under` creates the work directory and writes one
executable stand-in per blocked command into it; :meth:`TrialEnvironment.record_user_turn` appends
to the transcript.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from isolated_agent_config import agent_config_env

TRANSCRIPT_VARIABLE: Final = "NARRATIVETRACE_TRANSCRIPT"
"""What the grader is told, and the agent is not: where this trial's transcript is."""

GH_LOG_VARIABLE: Final = "NARRATIVETRACE_GH_LOG"
"""Where the stand-ins' log is. The name says ``gh`` because the graders' question -- "was
anything filed?" -- reads it; ``curl`` records into the same file so "what did this trial try to
reach?" is one place to look."""

SERVED_HOST: Final = "narrativetrace.ai"
"""The one host the ``curl`` stand-in passes through to the real curl: the published site."""

_BLOCKED_COMMANDS: Final = {"gh": 0, "curl": 6}
"""Each command a trial may not really run, with the exit code its stand-in answers.

``gh`` exits 0: the point is to record that the agent tried to FILE, so the stand-in behaves as if
it had worked and files nothing. ``curl`` exits 6 -- curl's own "could not resolve host" -- because
the truthful answer to a request from a sandbox with no network is a network failure, where exiting
0 with empty output would read as "that repository has nothing in it" and send the agent down a
wrong path. ``curl`` earned its place in Java: one feedback turn made about forty requests to
``api.github.com`` hunting for the repository to file into."""

_NO_BYTECODE_VARIABLE: Final = "PYTHONDONTWRITEBYTECODE"
"""A grader imports a shared helper beside it; without this its ``__pycache__`` lands INSIDE the
committed case directory -- a trial leaving build output in the repository it is testing."""

_TRANSCRIPT_NAME: Final = "transcript.jsonl"
_LOG_NAME: Final = "gh-invocations.log"


@dataclass(frozen=True, slots=True)
class TrialEnvironment:
    """One trial's work directory, and the two environments derived from it.

    Build it with :meth:`under`; the constructor takes the already-prepared pieces.
    """

    work_dir: Path
    agent_environment: dict[str, str]

    @classmethod
    def under(cls, work_dir: Path, ambient_path: str) -> TrialEnvironment:
        """A trial recording into ``work_dir``, with both stand-ins installed first on a PATH that
        keeps ``ambient_path`` behind them.

        :raises ValueError: when ``work_dir``'s path carries a ``'``, which would end the
            stand-ins' own POSIX single-quoted log path.
        :sideEffects: creates ``work_dir/bin`` and writes the two executable stand-ins there.
        """
        _require_quotable(work_dir)
        bin_dir = work_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        log = work_dir / _LOG_NAME
        for name, exit_code in _BLOCKED_COMMANDS.items():
            _write_stand_in(bin_dir / name, name, exit_code, log)
        environment = {
            "PATH": f"{bin_dir}:{ambient_path}",
            _NO_BYTECODE_VARIABLE: "1",
            **agent_config_env(work_dir),
        }
        return cls(work_dir, environment)

    @property
    def transcript(self) -> Path:
        """Every turn's prompt and the agent's own stdout, in order -- the grader's record."""
        return self.work_dir / _TRANSCRIPT_NAME

    @property
    def blocked_invocations(self) -> Path:
        """One line per invocation of a stand-in, argv included -- ``gh`` and ``curl`` alike."""
        return self.work_dir / _LOG_NAME

    @property
    def grader_environment(self) -> dict[str, str]:
        """The agent's environment, plus where the two pieces of evidence are."""
        return {
            **self.agent_environment,
            TRANSCRIPT_VARIABLE: str(self.transcript),
            GH_LOG_VARIABLE: str(self.blocked_invocations),
        }

    def record_user_turn(self, turn: int, text: str) -> None:
        """Marks the start of ``turn`` in the transcript, with the words the user is given there.

        The marker is what lets a grader say WHICH turn it is reading -- every agent line after it
        and before the next marker belongs to that turn -- and it carries the user's own words, so
        a grader compares the agent's behaviour against the reply actually scripted. One JSON line
        whatever ``text`` carries (``json.dumps`` escapes every control character).
        """
        marker = {"nt_turn": turn, "role": "user", "text": text}
        with self.transcript.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(marker) + "\n")

    def keep_evidence_under(self, destination: Path) -> Path:
        """Copies whatever evidence this trial produced into ``destination``, and returns it.

        A trial's work directory is deleted when the trial ends, whatever the outcome -- right for
        a pass and useless for a fail, where the record the grader read is gone. A red row nobody
        can diagnose is the one outcome a harness whose rows cost real requests cannot afford.

        :sideEffects: creates ``destination`` and copies the existing evidence files into it.
        """
        destination.mkdir(parents=True, exist_ok=True)
        for evidence in (self.transcript, self.blocked_invocations):
            if evidence.is_file():
                shutil.copyfile(evidence, destination / evidence.name)
        return destination


def _require_quotable(path: Path) -> None:
    """The work directory reaches two places that one character can break: the stand-ins'
    single-quoted log path (``'``), and ``PATH`` itself (``:``) -- where a split directory means
    the stand-ins are silently NOT found and a real ``gh`` would run."""
    if "'" in str(path):
        raise ValueError(
            "a trial's work directory may not carry a ' -- the stand-ins quote their log path: "
            f"{path}"
        )
    if ":" in str(path):
        raise ValueError(
            "a trial's work directory may not carry a ':' -- PATH would split the stand-ins' "
            f"directory in two and a real gh would run: {path}"
        )


def _write_stand_in(stub: Path, name: str, exit_code: int, log: Path) -> None:
    """A recording stand-in: it writes its argv on ONE line (so a grader can count invocations and
    search them for a planted value) and does nothing else -- except ``curl`` for
    :data:`SERVED_HOST`, which it hands to the real curl after recording."""
    stub.write_text(
        "#!/bin/sh\n"
        f"# A recording stand-in for `{name}`, installed first on this trial's PATH by the eval\n"
        "# runner. It records its argv and does NOTHING ELSE, so no trial can file an issue or\n"
        "# reach a network -- and so 'the agent tried to' is distinguishable from 'it did not'.\n"
        "{\n"
        f"  printf '{name}'\n"
        '  for arg in "$@"; do printf \' %s\' "$arg"; done\n'
        "  printf '\\n'\n"
        f"}} >> '{log}'\n" + _served_request_or_exit(name, exit_code),
        encoding="utf-8",
    )
    stub.chmod(0o755)


def _served_request_or_exit(name: str, exit_code: int) -> str:
    """The stand-in's tail: ``exit N`` for every command but ``curl``. For curl, a request whose
    URLs are ALL on :data:`SERVED_HOST` goes to the first real curl behind the stand-in on PATH;
    a foreign URL among them, or no URL at all, exits with the blocked code.

    **@llmNote** Shell builtins only below, and a marker in the environment: a trial's PATH may
    carry no ``dirname``, and a stand-in that cannot tell its own file apart execs itself without
    end (Java's first version did, for 39 minutes, under a two-entry PATH in a test).
    """
    if name != "curl":
        return f"exit {exit_code}\n"
    host = SERVED_HOST
    return (
        "served=0\n"
        'for arg in "$@"; do\n'
        '  case "$arg" in\n'
        f"    http://{host}|http://{host}/*|https://{host}|https://{host}/*) served=1 ;;\n"
        f"    http://*|https://*) exit {exit_code} ;;\n"
        "  esac\n"
        "done\n"
        f'[ "$served" = 1 ] || exit {exit_code}\n'
        f'[ -n "$NARRATIVETRACE_CURL_STANDIN" ] && exit {exit_code}\n'
        "export NARRATIVETRACE_CURL_STANDIN=1\n"
        "self=${0%/*}\n"
        "IFS=:\n"
        "for dir in $PATH; do\n"
        '  [ "$dir" = "$self" ] && continue\n'
        '  [ "$dir/curl" -ef "$0" ] && continue\n'
        '  [ -x "$dir/curl" ] && exec "$dir/curl" "$@"\n'
        "done\n"
        f"exit {exit_code}\n"
    )
