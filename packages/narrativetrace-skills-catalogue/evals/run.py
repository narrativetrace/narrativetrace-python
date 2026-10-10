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

**Every trial** runs behind recording stand-ins for ``gh`` (exit 0) and ``curl`` (exit 6, except
the published site, served through the real curl) first on ``PATH``, against a throwaway vendor
configuration with the subscription login seeded in, and with its transcript and the stand-ins' log
in a work directory OUTSIDE the project that only the grader is told about
(``trial_environment``). A case that declares ``"turns"`` is a conversation: each scripted reply is
a turn of its own in one resumed session (``case_turns``, ``agent_turns``). A trial that does not
pass keeps its evidence under this package's ``build/evals/`` before the work directory goes.

**A registry case** (``case.json`` declaring ``"registry"``, from ``registry_delivery``'s closed
vocabulary) is driven differently in two ways, each because of what such a case measures — the
state a registry left behind, not the prompt alone. The harness puts NONE of its own pages in the
project; and the registry's own documented commands run first, in the project, against a ``git
archive`` of ``HEAD``'s registry surface staged beside it. A failed pre-step CRASHES the trial and
writes no ledger row: an absent vendor tool is not a verdict about the registry path.

**A checkout case** (``"install": "checkout"``) measures behaviour the published release predates:
every distribution of this checkout is built into the work directory, ``UV_FIND_LINKS`` points the
agent's own ``uv`` at those wheels, and this checkout's rendered skill pages are copied in.

**A repository case** (``"vcs": "git"``) is a project that already lives in a git repository, as a
real one does: after the fixture is scaffolded (and any checkout pages are copied in) it is
committed with a throwaway author named inline, before the agent's first turn. For a skill whose
first step lists tracked files.

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
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import NamedTuple, Protocol

_EVALS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _EVALS_DIR.parent.parent.parent
_LEDGER_PATH = _EVALS_DIR.parent / "ledger" / "runs.jsonl"
_QUOTA_PATH = _EVALS_DIR.parent / "ledger" / "quota.md"
_EVIDENCE_ROOT = _EVALS_DIR.parent / "build" / "evals"
"""Where a failed or crashed trial's transcript and stand-in log are kept -- this package's own
``build/``, which git ignores, so evidence never lands in a commit by accident."""

sys.path.insert(0, str(_EVALS_DIR))

from agent_turns import AgentTurns  # noqa: E402
from case_turns import scripted_replies_for  # noqa: E402
from isolated_agent_config import (  # noqa: E402
    config_dir,
    real_config_dir,
    seed_login,
)
from platform_presets import (  # noqa: E402 - see sys.path.insert above
    Platform,
    is_platform,
    is_sporadic_platform,
)
from quota import (  # noqa: E402
    QuotaSpendRow,
    append_spend_row,
    check_quota,
    iso_week,
    parse_quota_markdown,
)
from registry_delivery import RegistryDelivery, registry_for_case  # noqa: E402
from tier_precondition import assert_deterministic_tiers_green  # noqa: E402
from trial_environment import TrialEnvironment  # noqa: E402


class Spawner(Protocol):
    """Runs ``argv`` in ``cwd`` with ``env`` ADDED to the ambient environment, and raises
    (``subprocess.CalledProcessError`` on a nonzero exit, ``OSError`` if the program can't even
    launch) instead of returning a status. Injected everywhere a real CLI would otherwise run, so
    the whole scaffold -> deliver -> drive agent -> grade -> ledger flow is testable with a fake
    agent and no real subprocess.

    ``env`` is how the trial's own environment -- the recording stand-ins first on ``PATH``, the
    isolated vendor configuration -- reaches every command of it. ``stdout_to``, when given, is the
    transcript the child's standard output is APPENDED to (an agent turn); its errors stay visible
    to whoever started the trial."""

    def __call__(
        self,
        argv: Sequence[str],
        cwd: Path,
        env: Mapping[str, str],
        stdout_to: Path | None = None,
    ) -> None: ...


Clock = Callable[[], date]

_LAUNCHER_SESSION_VARIABLES = frozenset(
    {
        "CLAUDECODE",
        "CLAUDE_PID",
        "CLAUDE_EFFORT",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_CHILD_SESSION",
        "CLAUDE_CODE_MESSAGING_SOCKET",
        "CLAUDE_CODE_MESSAGING_TOKEN",
        "CLAUDE_CODE_SESSION_ATTENDED",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_EXECPATH",
    }
)
"""What an agent session that LAUNCHED this runner leaves in the environment: its id, its
messaging socket and token, its effort level. Inherited, they make the trial's own agent a child
of the launcher -- a trial measured against the operator's session, not the product (found
2026-10-08, running the runner from inside one). Never the login: that is a file, seeded on
purpose (``isolated_agent_config``)."""


def default_spawner(
    argv: Sequence[str], cwd: Path, env: Mapping[str, str], stdout_to: Path | None = None
) -> None:
    """Production spawner: a real subprocess, argv only, never a shell. ``argv`` is always a fixed
    list built by this module (a preset or an operator-supplied ``--agent-command`` template,
    tokenised by ``_tokenize_agent_command``) — nothing here re-parses it as a command line.

    ``env`` is MERGED over the ambient environment rather than replacing it: a vendor CLI that lost
    ``PATH``, ``HOME`` or the terminal it inherited would fail for a reason the case never touched.
    The launcher's own session variables are the one exception
    (:data:`_LAUNCHER_SESSION_VARIABLES`). Standard input is ``/dev/null``: the agent CLI otherwise
    waits three seconds on every turn for input nobody sends.
    """
    ambient = {k: v for k, v in os.environ.items() if k not in _LAUNCHER_SESSION_VARIABLES}
    child_env = {**ambient, **env}
    if stdout_to is None:
        subprocess.run(  # nosec B603 - argv is a fixed, pre-tokenised list; no shell involved
            list(argv), cwd=cwd, check=True, env=child_env, stdin=subprocess.DEVNULL
        )
        return
    with stdout_to.open("a", encoding="utf-8") as transcript:
        subprocess.run(  # nosec B603 - argv is a fixed, pre-tokenised list; no shell involved
            list(argv),
            cwd=cwd,
            check=True,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=transcript,
        )


@dataclass(frozen=True, slots=True)
class RunDeps:
    """The runner's injected seams: production defaults, overridden by fakes in tests."""

    spawn: Spawner = default_spawner
    clock: Clock = date.today
    ledger_path: Path = _LEDGER_PATH
    quota_path: Path = _QUOTA_PATH
    new_session_id: Callable[[], str] = field(default=lambda: str(uuid.uuid4()))
    evidence_root: Path = _EVIDENCE_ROOT


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
    try:
        shutil.copytree(_REPO_ROOT / fixture_relative_path, scratch, dirs_exist_ok=True)
    except BaseException:
        # The directory exists before the copy that failed: without this, every mistyped
        # fixture path leaves an empty nt-eval-* behind.
        shutil.rmtree(scratch, ignore_errors=True)
        raise
    return scratch


def _tokenize_agent_command(template: str, prompt: str) -> list[str]:
    """Tokenises ``template`` with shell-style quoting rules, then substitutes ``{prompt}`` inside
    each resulting token by plain string replacement — never by splicing the raw template into a
    shell command line. The prompt therefore reaches the agent as (all or part of) a single argv
    element and is never re-parsed by a shell: backticks, ``$(...)``, quotes, and newlines inside
    it arrive verbatim and inert."""
    return [token.replace("{prompt}", prompt) for token in shlex.split(template)]


_CLI_PROJECT_VARIABLE = "NARRATIVETRACE_CLI_PROJECT"
"""Where the installer THIS CHECKOUT provides lives, for a grader that has to read it.

Told to the grader and to nobody else. A registry case's adoption proof must run the installer at
``HEAD`` — the PUBLISHED release predates the adoption and symlink-safety behaviour that proof is
about — while the agent's own step 3 runs whatever the project resolved from PyPI, which is what a
reader has. An agent handed this pointer could install from the checkout instead, and the case
would stop measuring the released product.
"""


def _run_grader(case_dir: Path, cwd: Path, spawn: Spawner, env: Mapping[str, str]) -> str:
    grader_env = {**env, _CLI_PROJECT_VARIABLE: str(_REPO_ROOT)}
    try:
        spawn(["sh", str(case_dir / "graders" / "verify.sh")], cwd, grader_env)
        return "pass"
    except (subprocess.CalledProcessError, OSError):
        return "fail"


def _delivery_for(case_dir: Path, work_dir: Path) -> RegistryDelivery:
    """How this case's skill pages reach the project. A case that declares a registry runs its
    registry's commands in the trial's own work directory, outside every repository tree: the
    staged snapshot the registry tool reads and the throwaway vendor configuration it installs into
    both live there."""
    registry = registry_for_case(case_dir)
    if registry is None:
        return RegistryDelivery()
    print(f"registry pre-step: {registry}")
    return RegistryDelivery(registry, work_dir)


def _seed_the_isolated_configuration(work_dir: Path) -> None:
    """The throwaway configuration EVERY trial runs against, carrying the one thing a fresh one
    cannot do without: the subscription login. Said out loud, because a trial with no login does not
    fail here — it fails three steps later when the agent answers "Not logged in", a long way from
    the cause."""
    real = real_config_dir()
    seeded = seed_login(real, work_dir)
    found = (
        f"subscription login seeded from {real}"
        if seeded
        else f"NO login found in {real} — the agent may refuse to start"
    )
    print(f"isolated agent configuration under {config_dir(work_dir)} ({found})")


def _run_pre_step(delivery: RegistryDelivery, scratch: Path, spawn: Spawner) -> None:
    """The registry's own delivery, before the agent starts: the staged snapshot, then the
    documented commands a reader runs, in order, in the project itself.

    :raises RuntimeError: if any of them fails — the trial CRASHED rather than failed, so it leaves
        no ledger row: an absent vendor tool or an unreachable registry is not a verdict about the
        registry path.
    """
    if not delivery.delivers_the_skills:
        return
    delivery.staged_snapshot.mkdir(parents=True, exist_ok=True)
    for command in delivery.commands(_REPO_ROOT):
        try:
            spawn(command, scratch, delivery.environment)
        except (subprocess.CalledProcessError, OSError) as error:
            raise RuntimeError(
                f"registry pre-step failed: {list(command)} — the registry delivered nothing, so "
                "there is no registry state to grade and this trial writes no ledger row"
            ) from error


_CHECKOUT_INSTALL = "checkout"
"""The one ``"install"`` a case may declare: this checkout's build, not the published release."""

_FIND_LINKS_VARIABLE = "UV_FIND_LINKS"
"""How a wheel directory reaches a ``uv`` line the AGENT types. uv prefers a find-links source
over the index for the same version (verified 2026-10-08: the lock recorded the local directory as
``narrativetrace``'s registry), so this checkout's 0.2.0 wins over PyPI's 0.2.0."""


def _installs_from_the_checkout(case_dir: Path) -> bool:
    """Whether ``case_dir`` declares ``"install": "checkout"``.

    :raises ValueError: for any other declared value (a closed vocabulary: data that may name an
        install source is a supply-chain seam this harness does not have), or for a registry case
        that also declares one -- a registry case's pages are the registry's by definition.
    """
    manifest_path = case_dir / "case.json"
    if not manifest_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "install" not in manifest:
        return False
    if manifest["install"] != _CHECKOUT_INSTALL:
        raise ValueError(
            f'{manifest_path} declares "install": {manifest["install"]!r} -- the only install a '
            f'case may declare is "{_CHECKOUT_INSTALL}"'
        )
    if "registry" in manifest:
        raise ValueError(
            f"{manifest_path} declares both a registry and a checkout install -- a registry "
            "case's pages are the ones its registry delivered"
        )
    return True


_GIT_VCS = "git"
"""The one ``"vcs"`` a case may declare: the project starts as a committed git repository."""


def _declares_a_git_repository(case_dir: Path) -> bool:
    """Whether ``case_dir`` declares ``"vcs": "git"``.

    :raises ValueError: for any other declared value (a closed vocabulary, as for ``"install"``).
    """
    manifest_path = case_dir / "case.json"
    if not manifest_path.is_file():
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "vcs" not in manifest:
        return False
    if manifest["vcs"] != _GIT_VCS:
        raise ValueError(
            f'{manifest_path} declares "vcs": {manifest["vcs"]!r} -- the only vcs a case may '
            f'declare is "{_GIT_VCS}"'
        )
    return True


def _commit_the_project(scratch: Path, spawn: Spawner) -> None:
    """Makes the scratch project a git repository holding everything it has, as a real project is
    when an agent is first asked to work in it. The author is named inline: the trial never reads
    or writes anyone's git configuration, and a signing setup cannot stop the commit.

    :raises RuntimeError: if git fails -- a crash, not a verdict, so no ledger row.
    """
    author = [
        "-c",
        "user.name=fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "-c",
        "commit.gpgsign=false",
    ]
    commands = (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", *author, "commit", "-q", "-m", "the fixture, as the project starts"],
    )
    try:
        for command in commands:
            spawn(command, scratch, {})
    except (subprocess.CalledProcessError, OSError) as error:
        raise RuntimeError(
            "setting up the project's git repository failed, so there is no project to work in "
            "and this trial writes no ledger row"
        ) from error


class _Declared(NamedTuple):
    """What a case's ``case.json`` asks of the project it starts from, read and validated once."""

    from_checkout: bool
    in_repository: bool


def _declarations_of(case_dir: Path) -> _Declared:
    return _Declared(_installs_from_the_checkout(case_dir), _declares_a_git_repository(case_dir))


def _install_from_the_checkout(scratch: Path, work_dir: Path, spawn: Spawner) -> dict[str, str]:
    """Builds every distribution of this checkout into the trial's work directory, copies this
    checkout's rendered skill pages into the project, and returns what points the agent's own
    ``uv`` at those wheels.

    For a case measuring behaviour the PUBLISHED release predates (the feedback verb, the
    feedback skill): against PyPI's 0.2.0 such a case grades the calendar, not the product. The
    agent is told nothing beyond the variable ``uv`` itself reads, so it still runs the commands a
    reader runs. The pages carry no installer provenance -- graders stay off
    ``config.skills-installed``, as Java's do.

    :raises RuntimeError: if the build fails -- a crash, not a verdict, so no ledger row.
    """
    wheels = work_dir / "wheels"
    try:
        spawn(["uv", "build", "--wheel", "--all-packages", "-o", str(wheels)], _REPO_ROOT, {})
    except (subprocess.CalledProcessError, OSError) as error:
        raise RuntimeError(
            "building this checkout's wheels failed, so there is no build to install and this "
            "trial writes no ledger row"
        ) from error
    for layout in (".agents", ".claude"):
        pages = _REPO_ROOT / layout / "skills"
        if pages.is_dir():
            shutil.copytree(pages, scratch / layout / "skills", dirs_exist_ok=True)
    return {_FIND_LINKS_VARIABLE: str(wheels)}


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


def _drive_the_conversation(
    turns: AgentTurns,
    scratch: Path,
    env: Mapping[str, str],
    environment: TrialEnvironment,
    spawn: Spawner,
) -> None:
    """Every turn, in order: the user's words into the transcript first, then the agent's own turn
    with its standard output appended after them.

    A turn that fails raises and stops the trial, so no later turn runs and the grader never does:
    a second turn driven after a failed first is an approval answering a question never asked.
    """
    if not turns.first_turn_command:
        print("(no --agent-command given -- skipping the agent step, grading the fixture as-is)")
        return
    for turn in range(1, turns.turn_count + 1):
        prompt = turns.prompt_for_turn(turn)
        environment.record_user_turn(turn, prompt)
        argv = _tokenize_agent_command(turns.command_for_turn(turn), prompt)
        spawn(argv, scratch, env, environment.transcript)


def _keep_the_evidence(
    environment: TrialEnvironment, deps: RunDeps, args: RunArgs, trial: int, passed: bool
) -> None:
    """Every trial's record, copied out before its work directory is deleted: a failed or crashed
    one under ``trial-<n>``, a passing one under ``trial-<n>-pass`` — a pass is evidence too (the
    demonstration transcript, and the only way to see a grader did not pass a trial for the wrong
    reason), kept apart so it never reads as a failure."""
    if not environment.transcript.is_file():
        return
    name = f"trial-{trial}-pass" if passed else f"trial-{trial}"
    kept = environment.keep_evidence_under(deps.evidence_root / args.skill / args.case_name / name)
    print(f"evidence kept under {kept}")


def _run_one_trial(args: RunArgs, case_dir: Path, prompt: str, trial: int, deps: RunDeps) -> None:
    """One trial, in throwaway directories outside every repository tree: the scratch project the
    agent works in, and a work directory holding the trial's evidence (transcript, stand-in log),
    the recording stand-ins, the isolated vendor configuration with the login seeded, and -- for a
    registry case -- the staged snapshot. Both are deleted when the trial ends, whatever its
    outcome; every trial keeps its evidence first (a passing one under ``trial-<n>-pass``).

    Everything a case declares is read and checked BEFORE anything runs: a malformed conversation
    or install is refused with nothing spent.
    """
    declared = _declarations_of(case_dir)
    turns = AgentTurns.of(
        args.platform,
        args.model,
        args.skill,
        args.agent_command,
        prompt,
        scripted_replies_for(case_dir),
        deps.new_session_id(),
    )
    work_dir = Path(tempfile.mkdtemp(prefix="nt-eval-work-"))
    environment = TrialEnvironment.under(work_dir, os.environ.get("PATH", ""))
    passed = False
    try:
        result = _run_in(work_dir, environment, args, case_dir, turns, declared, deps)
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
        passed = result == "pass"
    finally:
        _keep_the_evidence(environment, deps, args, trial, passed)
        shutil.rmtree(work_dir, ignore_errors=True)


def _run_in(  # noqa: PLR0913 - one trial's already-validated inputs, passed through once
    work_dir: Path,
    environment: TrialEnvironment,
    args: RunArgs,
    case_dir: Path,
    turns: AgentTurns,
    declared: _Declared,
    deps: RunDeps,
) -> str:
    """Scaffold, deliver, drive every turn and grade, in a scratch project deleted afterwards.

    :param declared: whether the case installs from the checkout, and whether its project starts
        as a git repository
    :returns: ``"pass"`` or ``"fail"``, the grader's verdict
    :raises: whatever crashed the trial -- a failed pre-step, build or agent turn -- so the caller
        writes no ledger row for it
    """
    delivery = _delivery_for(case_dir, work_dir)
    _seed_the_isolated_configuration(work_dir)
    scratch = _scaffold_fixture(_case_fixture(args.skill, args.case_name))
    try:
        installed = (
            _install_from_the_checkout(scratch, work_dir, deps.spawn)
            if declared.from_checkout
            else {}
        )
        if declared.in_repository:
            _commit_the_project(scratch, deps.spawn)
        _run_pre_step(delivery, scratch, deps.spawn)
        agent_env = {**delivery.environment, **environment.agent_environment, **installed}
        _drive_the_conversation(turns, scratch, agent_env, environment, deps.spawn)
        grader_env = {**delivery.environment, **environment.grader_environment, **installed}
        return _run_grader(case_dir, scratch, deps.spawn, grader_env)
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
