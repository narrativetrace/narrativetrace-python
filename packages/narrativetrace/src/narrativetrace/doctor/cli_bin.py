# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``narrativetrace`` console entry point: verb dispatch over the free CLI.

Three verbs: ``doctor`` diagnoses a project, ``init`` installs the NarrativeTrace agent skills and
the ``AGENTS.md`` section into it, ``uninstall`` removes exactly what ``init`` wrote.

Follows the ``narrativetrace-approve``/``narrativetrace-clarity`` CLIs' shape: stdlib
``argparse``-free hand-rolled dispatch (mirrors the TypeScript runtime's ``cli.ts``/``cli-bin.ts``
split — ``run_cli`` here takes injectable dependencies so tests never spawn a real process or touch
the real filesystem), ``main(argv=None) -> int`` returning the process exit code, no third-party CLI
framework.

This module is the launcher, not the tool: every check, the report, both renderings, and the whole
installer come from :mod:`narrativetrace_tooling`, the zero-dependency library this distribution
depends on. What is decided here is what only a process can decide — which verb was asked for, which
flags are recognised, what goes to stdout rather than stderr, and what the process exits with.

Exit codes, the same three for every verb: ``0`` the command ran and every check passed, or the plan
applied, or it was previewed (or ``--help``); ``1`` the command ran and could not finish the work —
a check failed, an action was refused, the carrier could not be opened, or the project could not be
read; ``2`` the command could not run at all (no verb, an unknown verb, or an unreadable flag).

**@llmNote** ``--dry-run`` exits 0 for every outcome of PLANNING, refusals included — a refusal in a
preview is something shown, not something that happened. It is not a blanket 0: a preview that could
not read the project at all still exits 1, because there is no plan to have shown.

**@llmNote** No verb makes a network call. ``init`` installs from the carrier this project already
resolves, or from whatever ``--from`` names locally — never from an index it would have to fetch.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final

from narrativetrace.doctor.environment import build_snapshot
from narrativetrace.doctor.feedback_cli import run_feedback
from narrativetrace.doctor.gh_auth_probe import gh_authenticated
from narrativetrace_tooling.doctor.doctor import run_doctor
from narrativetrace_tooling.doctor.render import render_human, render_json
from narrativetrace_tooling.init import (
    Carrier,
    InitOptions,
    InitPlan,
    ProjectState,
    Scope,
    Vendor,
    execute_plan,
    plan_init,
    plan_uninstall,
    project_family_version,
    read_project_state,
    render_plan,
    render_report,
    resolve_carrier,
    version_warning,
)

if TYPE_CHECKING:
    from narrativetrace_tooling.doctor.types import DoctorSnapshot, Env

_USAGE = """narrativetrace — one CLI over NarrativeTrace's open artifact formats

Usage:
  narrativetrace doctor [--json]
  narrativetrace init [--dry-run] [--write-existing] [--force] [--only <half>] [--vendor <vendor>]
                      [--from <dir|wheel>] [--json]
  narrativetrace uninstall [--dry-run] [--only <half>] [--json]
  narrativetrace feedback <draft|url|gh> --category <c> --step <s>
                          --did <t> --happened <t> --expected <t> [--language <tag>]
                          [--agent-product <p>] [--agent-model <m>] [--trace <path>] [--json]

Commands:
  doctor     Read-only project diagnosis: toolchain, configuration, and known traps. Zero network.
  init       Installs the NarrativeTrace agent skills and the AGENTS.md section into this project.
  uninstall  Removes exactly what init wrote, and nothing beside it.
  feedback   Drafts a problem report, checks it carries no values, and shows you how to file it.

Options:
  --json    Machine-readable output instead of human text.
  --help    Show this message."""

_FEEDBACK_USAGE = """narrativetrace feedback <draft|url|gh> [options]

Drafts a problem report about NarrativeTrace from this project: the distributions it resolved, the
doctor's own JSON report, and at most one structural trace. Every field is checked against the
value-free rules FIRST — the verb refuses to write a body file or build a URL while any rule
stands, and names the rule.

Channels:
  draft  Write and print the whole draft. Nothing is filed.
  url    Print the pre-filled issue-form URL. You open it and submit it yourself.
  gh     Print the exact `gh issue create` line. It is never run from here.

Options:
  --category <c>       prompt | skill | doctor | library. Required.
  --step <s>           Which check id, skill step or prompt step it happened at. Required.
  --did <t>            What you did. Required.
  --happened <t>       What happened instead. Required.
  --expected <t>       What you expected. Required.
  --language <tag>     The language the report is written in. en by default.
  --agent-product <p>  The agent product drafting this, as it reports itself.
  --agent-model <m>    The agent model, as it reports itself.
  --trace <path>       A path suffix naming the structural trace to attach.
  --json               Machine-readable output instead of human text.

Nothing is sent anywhere. Exit 0 = drafted, 1 = that channel is not available, 2 = could not run
(a missing flag, or a value-free rule refused the report)."""

_DOCTOR_USAGE = """narrativetrace doctor [--json]

Read-only. Checks toolchain/install state, configuration, and known traps against the current
project. Exit 0 = clean, 1 = findings, 2 = could not run."""

_DRY_RUN_OPTION = """\
  --dry-run         Show the plan and the unified diff, and write nothing. A refusal is shown
                    rather than applied, so a preview of one still exits 0."""

_SHARED_OPTIONS = """\
  --only <half>     skills | agents-md. Both halves by default.
  --json            Machine-readable output instead of human text."""

_INIT_ONLY_OPTIONS = """\
  --write-existing  Permission to touch an AGENTS.md or CLAUDE.md that is already there.
  --force           Permission to overwrite a skill directory somebody else owns.
  --vendor <vendor> claude | none. Detected from the project by default.
  --from <carrier>  A directory in the carrier's own layout, or a built wheel. By default the
                    narrativetrace-skills distribution this project resolves, and the copy the
                    narrativetrace distribution bundles when that one is not installed. Never
                    fetched: this CLI makes no network call."""

_EXIT_CODES = """\
Exit 0 = applied, or previewed; 1 = something was refused, or the project could not be read;
2 = the command could not run at all."""

_INIT_USAGE = f"""narrativetrace init [options]

Copies the NarrativeTrace agent skills into .agents/skills/ (and .claude/skills/ where the project
is one of that vendor's) and writes one marked section into AGENTS.md. Zero network.

Nothing refreshes the installed pages on a build — this runtime has no build hook at the right
altitude, and a test run that rewrote committed files would be a surprise diff. Re-run this verb
instead: on a project that already carries an install it replaces only our own pages and section,
with no flag. `narrativetrace doctor` reports when what is installed is stale.

{_DRY_RUN_OPTION}
{_INIT_ONLY_OPTIONS}
{_SHARED_OPTIONS}

{_EXIT_CODES}"""

_UNINSTALL_USAGE = f"""narrativetrace uninstall [options]

Removes exactly what init wrote: skill directories carrying its provenance line, the marked section,
and the one @AGENTS.md import line. Never touches anything else.

{_DRY_RUN_OPTION}
{_SHARED_OPTIONS}

{_EXIT_CODES}"""

_CARRIER_HINT = """This CLI never fetches anything. Install the carrier once and init will find it:
  uv add narrativetrace-skills
Or point --from at an unpacked carrier directory or a built wheel."""


@dataclass(frozen=True, slots=True)
class CliDeps:
    """Injectable seam (mirrors the TypeScript runtime's ``CliDeps``) so a test drives
    :func:`run_cli` without a real process, a real cwd, or a real filesystem walk.

    :param cwd: the project directory every verb reads, and the installer writes into
    :param env: the environment the doctor reads
    :param build_snapshot: the doctor's project walk
    :param open_carrier: the carrier a named path, or the ruled preference order, resolves to
    :param project_version: the NarrativeTrace release this project resolves, for the version guard
    :param gh_authenticated: whether an already-installed ``gh`` is signed in — the ONE
        outward-facing question this launcher asks, only on ``feedback gh``, and the one seam that
        lets all four of its outcomes be tested without starting a process
    :param log: where a report goes — stdout in the real process
    :param error: where a refusal, a usage message and the version warning go — stderr
    """

    cwd: str
    env: Env
    build_snapshot: Callable[[str, Env], DoctorSnapshot]
    open_carrier: Callable[[str | None], Carrier]
    project_version: Callable[[], str | None]
    log: Callable[[str], None]
    error: Callable[[str], None]
    gh_authenticated: Callable[[], bool] = gh_authenticated


_JSON: Final = "--json"

_HELP: Final = ("--help", "-h")

_SWITCHES: Final[dict[str, Callable[[InitOptions], InitOptions]]] = {
    "--dry-run": lambda options: replace(options, dry_run=True),
    "--write-existing": lambda options: replace(options, write_existing=True),
    "--force": lambda options: replace(options, force=True),
}
"""Every valueless installer flag, and the permission it grants the installer library."""

_ONLY: Final = "--only"

_VENDOR: Final = "--vendor"

_FROM: Final = "--from"

_VALUE_FLAGS: Final = (_ONLY, _VENDOR, _FROM)
"""The flags that take a value, written either ``--flag value`` or ``--flag=value``."""

_SCOPES: Final = {"skills": Scope.SKILLS, "agents-md": Scope.AGENTS_MD}

_VENDORS: Final = {"claude": Vendor.ON, "none": Vendor.OFF}


@dataclass(frozen=True, slots=True)
class InstallerArguments:
    """What ``init``/``uninstall`` were asked to do, read off a command line and nothing else.

    **@llmNote** A bad flag is DATA here (:attr:`error`), never an exception: the launcher prints
    it with the verb's usage and exits 2, the one exit code that means "could not run at all". The
    FIRST problem is the one reported — naming a later flag would name one nobody has read yet.

    :param options: what the installer library is asked for
    :param from_path: the carrier a person named, or ``None`` for the resolved one
    :param as_json: whether to print the machine-readable envelope instead of human text
    :param help_wanted: whether the verb's usage was asked for
    :param error: why the command line could not be read, or ``None`` when it could
    """

    options: InitOptions = field(default_factory=InitOptions)
    from_path: str | None = None
    as_json: bool = False
    help_wanted: bool = False
    error: str | None = None

    def __post_init__(self) -> None:
        assert _invariant(self), "a read command line must say what it read"


def _invariant(arguments: InstallerArguments) -> bool:
    """Returns whether a read command line is self-consistent: a problem that says something, and a
    named carrier that names something.

    Both halves are the difference between "nothing was given" and "something empty was given", and
    both are load-bearing at the dispatch: ``error == ""`` would exit 2 printing no reason, and
    ``from_path == ""`` would ask the carrier reader to open the current directory. The parser makes
    this true for every live instance; tests re-check it around each case.
    """
    return arguments.error != "" and arguments.from_path != ""


def parse_installer_arguments(arguments: Sequence[str]) -> InstallerArguments:
    """Reads the arguments that follow ``init`` or ``uninstall``.

    :raises TypeError: when no argument sequence is given
    """
    if arguments is None:
        raise TypeError("a command line is a sequence of arguments, never None")
    parsed = InstallerArguments()
    index = 0
    while index < len(arguments):
        parsed, index = _read_one(parsed, arguments, index)
    return parsed


def _read_one(
    parsed: InstallerArguments, arguments: Sequence[str], index: int
) -> tuple[InstallerArguments, int]:
    """Reads the argument at ``index`` and returns the state and the index after it."""
    argument = arguments[index]
    name, separator, inline = argument.partition("=")
    if name in _SWITCHES or name in _HELP or name == _JSON:
        return _switched(parsed, name), index + 1
    if name not in _VALUE_FLAGS:
        return _failed(parsed, f'unknown option: "{argument}"'), index + 1
    value = inline if separator else _at(arguments, index + 1)
    if not value:
        return _failed(parsed, f"{name} needs a value"), index + 1
    return _valued(parsed, name, value), index + (1 if separator else 2)


def _switched(parsed: InstallerArguments, name: str) -> InstallerArguments:
    """A flag that carries no value."""
    if name == _JSON:
        return replace(parsed, as_json=True)
    if name in _HELP:
        return replace(parsed, help_wanted=True)
    return replace(parsed, options=_SWITCHES[name](parsed.options))


def _valued(parsed: InstallerArguments, name: str, value: str) -> InstallerArguments:
    """A flag and the value written after it."""
    if name == _FROM:
        return replace(parsed, from_path=value)
    if name == _ONLY:
        return _scoped(parsed, value)
    return _vendored(parsed, value)


def _scoped(parsed: InstallerArguments, value: str) -> InstallerArguments:
    scope = _SCOPES.get(value)
    if scope is None:
        return _failed(parsed, f'{_ONLY} takes skills or agents-md, got "{value}"')
    return replace(parsed, options=replace(parsed.options, scope=scope))


def _vendored(parsed: InstallerArguments, value: str) -> InstallerArguments:
    vendor = _VENDORS.get(value)
    if vendor is None:
        return _failed(parsed, f'{_VENDOR} takes claude or none, got "{value}"')
    return replace(parsed, options=replace(parsed.options, vendor_claude=vendor))


def _failed(parsed: InstallerArguments, message: str) -> InstallerArguments:
    """Records why the line could not be read, keeping the FIRST problem found."""
    return parsed if parsed.error is not None else replace(parsed, error=message)


def _at(arguments: Sequence[str], index: int) -> str | None:
    return arguments[index] if index < len(arguments) else None


def _run_doctor_command(rest: Sequence[str], deps: CliDeps) -> int:
    """Runs ``doctor`` once argv has been recognized as that command. Returns the exit code."""
    if "--help" in rest or "-h" in rest:
        deps.log(_DOCTOR_USAGE)
        return 0
    as_json = "--json" in rest
    unknown = [arg for arg in rest if arg != "--json"]
    if unknown:
        deps.error(f"Unknown argument(s) for doctor: {', '.join(unknown)}\n\n{_DOCTOR_USAGE}")
        return 2
    snapshot = deps.build_snapshot(deps.cwd, deps.env)
    if snapshot.root_pyproject is None:
        deps.error(f"Could not run: no readable pyproject.toml found at {deps.cwd}")
        return 2
    report = run_doctor(snapshot)
    deps.log(render_json(report) if as_json else render_human(report))
    return report.exit_code


def _run_installer_command(*, install: bool, rest: Sequence[str], deps: CliDeps) -> int:
    """The two installer verbs: same flags, same output; one plans an install, one its removal."""
    parsed = parse_installer_arguments(rest)
    usage = _INIT_USAGE if install else _UNINSTALL_USAGE
    if parsed.help_wanted:
        deps.log(usage)
        return 0
    if parsed.error is not None:
        deps.error(f"{parsed.error}\n\n{usage}")
        return 2
    return _run_init(parsed, deps) if install else _run_uninstall(parsed, deps)


def _run_init(parsed: InstallerArguments, deps: CliDeps) -> int:
    """The carrier is opened BEFORE the project is read: a run that cannot find its skills has
    nothing to plan, and finding that out after walking the project only delays the same message."""
    try:
        carrier = deps.open_carrier(parsed.from_path)
    except (ValueError, OSError) as error:
        deps.error(f"{error}\n\n{_CARRIER_HINT}")
        return 1
    warning = version_warning(carrier, deps.project_version())
    if warning is not None:
        deps.error(warning)
    return _run_plan(lambda state: plan_init(state, carrier, parsed.options), parsed, deps)


def _run_uninstall(parsed: InstallerArguments, deps: CliDeps) -> int:
    return _run_plan(lambda state: plan_uninstall(state, parsed.options), parsed, deps)


def _run_plan(
    planner: Callable[[ProjectState], InitPlan], parsed: InstallerArguments, deps: CliDeps
) -> int:
    """Reads the project once, plans, and then either shows the plan or applies it.

    Exit 1 rather than 2 when the project cannot be read: the command was typed correctly, it could
    not do the work. That includes a project that stops being one AFTER the snapshot was taken — a
    plan is computed from the snapshot, so the executor is the second place that can meet the same
    "not a directory", and one escaping exception would break this launcher's whole contract, which
    is to return an exit code.
    """
    project = Path(deps.cwd)
    try:
        plan = planner(read_project_state(project))
        return _show_or_apply(plan, project, parsed, deps)
    except (TypeError, ValueError, OSError) as error:
        deps.error(str(error))
        return 1


def _show_or_apply(plan: InitPlan, project: Path, parsed: InstallerArguments, deps: CliDeps) -> int:
    """Prints the plan under ``--dry-run``, applies it otherwise, and returns its exit code."""
    if parsed.options.dry_run:
        deps.log(_as_one_message(render_plan(plan, parsed.as_json)))
        return plan.exit_code
    executed = execute_plan(plan, project)
    deps.log(_as_one_message(render_report(executed, parsed.as_json)))
    return executed.exit_code


def _as_one_message(rendered: str) -> str:
    """A plan's rendering with its final newline dropped, because :attr:`CliDeps.log` adds one.

    The installer's renderers end every line, the doctor's do not; both go through one ``print`` in
    the real process, so exactly one of the two needs this and the output carries one trailing
    newline either way.
    """
    return rendered.removesuffix("\n")


def run_cli(argv: Sequence[str], deps: CliDeps) -> int:
    """Parses ``argv`` and runs the requested command. Returns the process exit code."""
    if not argv:
        deps.error(_USAGE)
        return 2
    verb, *rest = argv
    if verb in _HELP:
        deps.log(_USAGE)
        return 0
    if verb == "doctor":
        return _run_doctor_command(rest, deps)
    if verb in ("init", "uninstall"):
        return _run_installer_command(install=verb == "init", rest=rest, deps=deps)
    if verb == "feedback":
        return run_feedback(rest, deps, _FEEDBACK_USAGE)
    deps.error(f"Unknown command: {verb}\n\n{_USAGE}")
    return 2


def _log_stdout(message: str) -> None:
    print(message)  # the CLI's own stdout, not debug output


def _log_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _open_resolved_carrier(from_path: str | None) -> Carrier:
    """The carrier the real process installs from: what ``--from`` names, else the ruled preference
    order (:func:`resolve_carrier`). Local either way — no branch reaches a network."""
    return resolve_carrier(Path(from_path) if from_path is not None else None)


def main(argv: Sequence[str] | None = None, *, cwd: str | None = None) -> int:
    """The ``narrativetrace`` console script entry point.

    ``cwd`` defaults to the real process cwd (``os.getcwd()``); pass it explicitly to run against
    a different project root without touching process-global state. The process cwd is not a test
    input to fake by monkeypatching -- ``os.getcwd()`` is read by other code in the process too
    (mutmut's mutation trampoline re-resolves its configured, relative source path against it on
    every call into mutated code, ``main`` included, and crashes if a monkeypatch points it
    somewhere that path doesn't exist -- see ``test_doctor_cli_bin.py``'s note on the same hazard).
    """
    args = list(sys.argv[1:] if argv is None else argv)
    deps = CliDeps(
        cwd=cwd if cwd is not None else os.getcwd(),
        env=os.environ,
        build_snapshot=build_snapshot,
        open_carrier=_open_resolved_carrier,
        project_version=project_family_version,
        log=_log_stdout,
        error=_log_stderr,
        gh_authenticated=gh_authenticated,
    )
    return run_cli(args, deps)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
