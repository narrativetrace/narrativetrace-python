#!/usr/bin/env python3
# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier B trial runner. NEVER invoked by ``poe check`` — the owner runs this by hand or from the
nightly job, against a subscription CLI, never the metered API. Scaffolds the case's fixture into
a scratch directory (a fresh temp copy outside every repo tree), drives the requested agent CLI
against the prompt with the catalogue loaded, runs the case's grader, and appends one row to
``ledger/runs.jsonl``.

``--platform claude|codex|gemini`` fills ``--agent-command`` with that platform's preset
(``platform_presets.py``) — pass ``--agent-command`` explicitly to override it, e.g. a different
model flag shape::

    uv run python evals/run.py --skill narrativetrace-doctor --case happy-path \\
        --platform claude --model <cheapest-available>

Codex and Gemini are the two sporadic lanes: every trial on either platform first refuses to start
unless narrativetrace-skills' Tier A lints and Tier A2 replay are green at HEAD
(``tier_precondition.py``), and then unless ``ledger/quota.md`` still has weekly allowance left for
that platform (``quota.py``) — no override flag either way; fix the tests or edit the ledger.
Claude is exempt from both: it runs on the harness's own regular cadence, not the sporadic policy.

**Prompt safety.** The prompt text is never spliced into a shell command line: ``--agent-command``
is tokenised (shell-style quoting, resolved once) and the prompt is substituted into the resulting
argv elements, then run with no shell (``default_spawner``) — a prompt containing backticks,
``$(...)``, quotes, or newlines reaches the agent verbatim and inert. Paths (the case directory,
the fixture to scaffold) are always resolved from this module's own location, never from the
caller's cwd, so the runner works the same from the repo root or from this package's directory.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_EVALS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVALS_DIR.parent.parent.parent
_LEDGER_PATH = _EVALS_DIR.parent / "ledger" / "runs.jsonl"
_QUOTA_PATH = _EVALS_DIR.parent / "ledger" / "quota.md"

sys.path.insert(0, str(_EVALS_DIR))

from platform_presets import (  # noqa: E402 - see sys.path.insert above
    Platform,
    is_platform,
    is_sporadic_platform,
    preset_agent_command,
)
from quota import (  # noqa: E402
    QuotaSpendRow,
    append_spend_row,
    check_quota,
    iso_week,
    parse_quota_markdown,
)
from tier_precondition import assert_deterministic_tiers_green  # noqa: E402

Spawner = Callable[[Sequence[str], Path], None]
"""Runs ``argv`` in ``cwd`` and raises (``subprocess.CalledProcessError`` on a nonzero exit,
``OSError`` if the program can't even launch) instead of returning a status. Injected everywhere a
real CLI would otherwise run, so the whole scaffold -> drive agent -> grade -> ledger flow is
testable with a fake agent and no real subprocess."""

Clock = Callable[[], date]


def default_spawner(argv: Sequence[str], cwd: Path) -> None:
    """Production spawner: a real subprocess, argv only, never a shell. ``argv`` is always a fixed
    list built by this module (a preset or an operator-supplied ``--agent-command`` template,
    tokenised by ``_tokenize_agent_command``) — nothing here re-parses it as a command line."""
    subprocess.run(  # nosec B603 - argv is a fixed, pre-tokenised list; no shell involved
        list(argv), cwd=cwd, check=True
    )


@dataclass(frozen=True, slots=True)
class RunDeps:
    """The runner's injected seams: production defaults, overridden by fakes in tests."""

    spawn: Spawner = default_spawner
    clock: Clock = date.today
    ledger_path: Path = _LEDGER_PATH
    quota_path: Path = _QUOTA_PATH


@dataclass(frozen=True, slots=True)
class RunArgs:
    skill: str
    case_name: str
    platform: Platform
    model: str
    agent_command: str | None
    trials: int


def _parse_args(argv: list[str]) -> RunArgs:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", required=True)
    parser.add_argument("--case", required=True, dest="case_name")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--agent-command", default=None)
    parser.add_argument("--trials", type=int, default=1)
    parsed = parser.parse_args(argv)
    if not is_platform(parsed.platform):
        parser.error(f"--platform must be one of claude, codex, gemini; got {parsed.platform!r}")
    return RunArgs(
        skill=parsed.skill,
        case_name=parsed.case_name,
        platform=parsed.platform,
        model=parsed.model,
        agent_command=parsed.agent_command,
        trials=parsed.trials,
    )


def _case_fixture(skill: str, case_name: str) -> str:
    """A case directory may declare which fixture to scaffold; defaults to the skill's own
    canonical fixture. Resolved from this module's own location, never the caller's cwd."""
    manifest_path = _EVALS_DIR / skill / case_name / "case.json"
    if manifest_path.is_file():
        manifest: dict[str, str] = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest["fixture"]
    return "examples/sixty_seconds"


def _scaffold_fixture(fixture_relative_path: str) -> Path:
    """A fresh temp copy outside every repo tree (the study isolation rule) — never the repo's
    own fixture in place. Resolved from the repo root this module lives under, never the caller's
    cwd, so the runner works the same invoked from the repo root or this package's own directory."""
    scratch = Path(tempfile.mkdtemp(prefix="nt-eval-"))
    shutil.copytree(_REPO_ROOT / fixture_relative_path, scratch, dirs_exist_ok=True)
    return scratch


def _tokenize_agent_command(template: str, prompt: str) -> list[str]:
    """Tokenises ``template`` with shell-style quoting rules, then substitutes ``{prompt}`` inside
    each resulting token by plain string replacement — never by splicing the raw template into a
    shell command line. The prompt therefore reaches the agent as (all or part of) a single argv
    element and is never re-parsed by a shell: backticks, ``$(...)``, quotes, and newlines inside
    it arrive verbatim and inert."""
    return [token.replace("{prompt}", prompt) for token in shlex.split(template)]


def _run_grader(case_dir: Path, cwd: Path, spawn: Spawner) -> str:
    try:
        spawn(["sh", str(case_dir / "graders" / "verify.sh")], cwd)
        return "pass"
    except (subprocess.CalledProcessError, OSError):
        return "fail"


def _append_ledger_row(ledger_path: Path, row: dict[str, object]) -> None:
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _assert_quota_available(
    quota_path: Path, platform: Platform, session_spend: list[QuotaSpendRow], today: date
) -> None:
    ledger = parse_quota_markdown(quota_path.read_text(encoding="utf-8"))
    combined = type(ledger)(allowances=ledger.allowances, spend=(*ledger.spend, *session_spend))
    decision = check_quota(combined, platform, now=today)
    if not decision.allowed:
        raise RuntimeError(decision.reason)


def _record_sporadic_spend(quota_path: Path, args: RunArgs, today: date) -> QuotaSpendRow:
    row = QuotaSpendRow(
        date=today.isoformat(),
        platform=args.platform,
        skill=args.skill,
        case_name=args.case_name,
        week=iso_week(today),
    )
    append_spend_row(quota_path, row)
    return row


def _run_one_trial(args: RunArgs, case_dir: Path, prompt: str, trial: int, deps: RunDeps) -> None:
    scratch = _scaffold_fixture(_case_fixture(args.skill, args.case_name))
    try:
        agent_command = args.agent_command or preset_agent_command(
            args.platform, args.model, args.skill
        )
        if agent_command:
            deps.spawn(_tokenize_agent_command(agent_command, prompt), scratch)
        else:
            print(
                "(no --agent-command given -- skipping the agent step, grading the fixture as-is)"
            )
        result = _run_grader(case_dir, scratch, deps.spawn)
        _append_ledger_row(
            deps.ledger_path,
            {
                "date": deps.clock().isoformat(),
                "skill": args.skill,
                "case": args.case_name,
                "platform": args.platform,
                "model": args.model,
                "trial": trial,
                "result": result,
            },
        )
        print(f"trial {trial}/{args.trials}: {result}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def run_trials(args: RunArgs, deps: RunDeps | None = None) -> int:
    """The runner's core flow, independent of ``sys.argv`` — the seam unit tests drive directly
    with a fake spawner, a fixed clock, and temp ledger/quota paths."""
    deps = deps or RunDeps()
    if is_sporadic_platform(args.platform):
        assert_deterministic_tiers_green(str(_REPO_ROOT))

    case_dir = _EVALS_DIR / args.skill / args.case_name
    prompt_path = case_dir / "prompt.md"
    if not prompt_path.is_file():
        raise FileNotFoundError(f"No case found at {case_dir}")
    prompt = prompt_path.read_text(encoding="utf-8")

    session_spend: list[QuotaSpendRow] = []
    for trial in range(1, args.trials + 1):
        if is_sporadic_platform(args.platform):
            _assert_quota_available(deps.quota_path, args.platform, session_spend, deps.clock())
        _run_one_trial(args, case_dir, prompt, trial, deps)
        if is_sporadic_platform(args.platform):
            session_spend.append(_record_sporadic_spend(deps.quota_path, args, deps.clock()))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    return run_trials(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
