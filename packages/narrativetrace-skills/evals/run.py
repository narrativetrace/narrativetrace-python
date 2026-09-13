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
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
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
    canonical fixture."""
    manifest_path = _EVALS_DIR / skill / case_name / "case.json"
    if manifest_path.is_file():
        manifest: dict[str, str] = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest["fixture"]
    return "examples/sixty_seconds"


def _scaffold_fixture(fixture_relative_path: str) -> Path:
    """A fresh temp copy outside every repo tree (the study isolation rule) — never the repo's
    own fixture in place."""
    scratch = Path(tempfile.mkdtemp(prefix="nt-eval-"))
    shutil.copytree(_REPO_ROOT / fixture_relative_path, scratch, dirs_exist_ok=True)
    return scratch


def _run_grader(case_dir: Path, cwd: Path) -> str:
    try:
        subprocess.run(  # nosec B603, B607 # fixed argv (sh + a repo-local script path), no shell
            ["sh", str(case_dir / "graders" / "verify.sh")], cwd=cwd, check=True
        )
        return "pass"
    except (subprocess.CalledProcessError, OSError):
        return "fail"


def _append_ledger_row(row: dict[str, object]) -> None:
    with _LEDGER_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _assert_quota_available(platform: Platform, session_spend: list[QuotaSpendRow]) -> None:
    ledger = parse_quota_markdown(_QUOTA_PATH.read_text(encoding="utf-8"))
    combined = type(ledger)(allowances=ledger.allowances, spend=(*ledger.spend, *session_spend))
    decision = check_quota(combined, platform)
    if not decision.allowed:
        raise RuntimeError(decision.reason)


def _record_sporadic_spend(args: RunArgs) -> QuotaSpendRow:
    row = QuotaSpendRow(
        date=date.today().isoformat(),
        platform=args.platform,
        skill=args.skill,
        case_name=args.case_name,
        week=iso_week(date.today()),
    )
    append_spend_row(_QUOTA_PATH, row)
    return row


def _run_one_trial(args: RunArgs, case_dir: Path, prompt: str, trial: int) -> None:
    scratch = _scaffold_fixture(_case_fixture(args.skill, args.case_name))
    try:
        agent_command = args.agent_command or preset_agent_command(
            args.platform, args.model, args.skill
        )
        if agent_command:
            subprocess.run(  # nosec B602 - a reviewed preset/operator-supplied CLI invocation
                agent_command.replace("{prompt}", prompt), shell=True, cwd=scratch, check=True
            )
        else:
            print(
                "(no --agent-command given -- skipping the agent step, grading the fixture as-is)"
            )
        result = _run_grader(case_dir, scratch)
        _append_ledger_row(
            {
                "date": date.today().isoformat(),
                "skill": args.skill,
                "case": args.case_name,
                "platform": args.platform,
                "model": args.model,
                "trial": trial,
                "result": result,
            }
        )
        print(f"trial {trial}/{args.trials}: {result}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
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
            _assert_quota_available(args.platform, session_spend)
        _run_one_trial(args, case_dir, prompt, trial)
        if is_sporadic_platform(args.platform):
            session_spend.append(_record_sporadic_spend(args))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
