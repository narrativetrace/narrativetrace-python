# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tier B platform presets: fills ``run.py``'s ``--agent-command`` seam for each of the four
supported CLIs so a trial can be started with just ``--platform`` — never invented for a platform
the seam doesn't name, and always overridable by passing ``--agent-command`` explicitly (the
preset is a default, not a lock-in).
"""

from __future__ import annotations

from typing import Literal

Platform = Literal["claude", "codex", "antigravity", "cursor"]
PLATFORMS: tuple[Platform, ...] = ("claude", "codex", "antigravity", "cursor")

# Codex, Antigravity and Cursor sit on cheaper plans and run under the sporadic policy (never
# scheduled, promotion points only, quota-guarded, Tier A/A2-green precondition). Claude runs on
# the harness's own regular cadence and is exempt from all three.
SPORADIC_PLATFORMS: frozenset[Platform] = frozenset({"codex", "antigravity", "cursor"})


def is_platform(value: str) -> bool:
    return value in PLATFORMS


def is_sporadic_platform(platform: Platform) -> bool:
    return platform in SPORADIC_PLATFORMS


def cli_tool(platform: Platform) -> str:
    """The executable a trial on ``platform`` starts — what a skip line names when the lane cannot
    run. Cursor's headless CLI is ``agent``, not ``cursor``; Antigravity's is ``agy``."""
    return {"cursor": "agent", "antigravity": "agy"}.get(platform, platform)


def is_read_only_skill(skill: str) -> bool:
    """``narrativetrace-doctor`` is scoped read-only by design ("diagnosis only, and read-only:
    it never edits, generates, or deletes a file"); every other cataloged skill installs or edits
    files. Used to pick the least-privileged sandbox/approval mode a trial needs."""
    return skill == "narrativetrace-doctor"


CLAUDE_TOOLS = "Bash,Read,Edit,Write,WebFetch,Skill"
"""What the Claude CLI may do in a trial, as one comma-separated ``--allowed-tools`` list.

Derived from the published init prompt, not from convenience: step 1 is "Read
https://narrativetrace.ai/python/llms.txt first" (``WebFetch``), steps 2-5 create or extend a
project, preview/apply the installer, and add the redaction test (``Read``, ``Edit``, ``Write``,
``Bash`` for the preview/apply commands), step 6 runs the program and the doctor (``Bash``), and
step 4 opens "if the ``add-narrative-tracing`` skill is now available, follow it" (``Skill``). A
preset that grants less than its prompt asks for measures the sandbox instead of the skill — a
trial where the agent is refused mid-step-1 and stops is a harness result wearing a product
result's clothes, and a REGISTRY case whose agent cannot invoke a skill measures nothing the
registry delivered. The list is quoted in the preset so ``run.py#_tokenize_agent_command`` keeps it
as ONE argv element; split across six arguments it is a different command.
"""


STREAMED_TRANSCRIPT = "--output-format stream-json --verbose"
"""The machine-readable stream, because a grader reads the agent's TOOL CALLS and not only its
closing text. **@llmNote** ``--verbose`` is not decoration: without it this CLI exits 1 having
written nothing to stdout or stderr (Java, verified 2026-10-05) -- indistinguishable from an agent
that did nothing."""

NO_ACCOUNT_CONNECTORS = "--strict-mcp-config"
"""Only the MCP servers an ``--mcp-config`` names, and the preset names none. The seeded login
otherwise attaches the ACCOUNT's connectors -- mail, drive, calendar, write tools among them -- to
a configuration that is fresh in every other respect (verified in this container 2026-10-08:
``mcp_servers`` went from six connectors to ``[]``, and stayed empty across ``--resume``). A network
path no PATH stand-in covers is not contained, and a configuration wider than the product measures
the operator's account."""

SESSION_PLACEHOLDER = "{session}"
"""What a multi-turn template carries where the trial's own session id goes."""


CURSOR_COMMAND = 'agent -p "{prompt}" --output-format text --force'
"""Cursor's headless CLI (``agent -p``, verified against cursor.com/docs/cli/headless 2026-10-10).
``--force`` applies edits and runs commands without a confirmation nobody is there to give, for
EVERY skill — the doctor included, which diagnoses by running a command, and a preset narrower than
the prompt measures the sandbox. No ``--model``: the runner's model argument is a ledger label, and
one that is not a Cursor model name would fail the trial before the agent starts."""


def _codex_command(model: str, skill: str) -> str:
    sandbox = "read-only" if is_read_only_skill(skill) else "workspace-write"
    return f'codex exec --sandbox {sandbox} --model {model} "{{prompt}}"'


ANTIGRAVITY_FLAGS = "--output-format text --dangerously-skip-permissions"
"""Antigravity's headless CLI (``agy -p``, verified against ``agy --help`` of CLI 1.3.3 and a real
print-mode run on 2026-10-10). ``--dangerously-skip-permissions`` is the only headless
auto-approval the CLI has -- no ``--yolo``, no approval mode; ``--mode plan`` exists but a doctor
trial RUNS a command, so plan mode would measure the sandbox -- and it therefore rides every skill,
exactly like Cursor's ``--force``. ``--model`` IS passed: the ledger's model is one of ``agy
models``' slugs (``gemini-3.8-flash-low`` is the cheapest), so the Cursor lane's reason for omitting
it does not apply."""


def preset_agent_command(platform: Platform, model: str, skill: str) -> str:
    """The default ``--agent-command`` template for ``platform``, ``{prompt}``-substituted by
    ``run.py``. Each CLI uses its own subscription login — the harness never passes an API key,
    so no preset ever threads one through."""
    if platform == "claude":
        return (
            f'claude -p "{{prompt}}" --model {model} --allowed-tools "{CLAUDE_TOOLS}" '
            f"{STREAMED_TRANSCRIPT} {NO_ACCOUNT_CONNECTORS}"
        )
    if platform == "codex":
        return _codex_command(model, skill)
    if platform == "cursor":
        return CURSOR_COMMAND
    return f'agy -p "{{prompt}}" --model {model} {ANTIGRAVITY_FLAGS}'


def preset_first_turn_command(platform: Platform, model: str, skill: str) -> str | None:
    """How ``platform`` opens a conversation the runner will drive further, or ``None`` when its
    own multi-turn flags have never been verified in the container the trials run in."""
    return _multi_turn(platform, model, skill, f"--session-id {SESSION_PLACEHOLDER}")


def preset_resumed_turn_command(platform: Platform, model: str, skill: str) -> str | None:
    """How ``platform`` continues that same conversation -- RESUMED, not forked, so every later
    turn names the id turn 1 was given -- or ``None`` for the same reason."""
    return _multi_turn(platform, model, skill, f"--resume {SESSION_PLACEHOLDER}")


def _multi_turn(platform: Platform, model: str, skill: str, session_flag: str) -> str | None:
    """The single-turn preset plus one session flag and nothing else, so a multi-turn trial is the
    same sandbox, tools and transcript format as a single-turn one.

    **@llmNote** ``None`` for every platform but Claude, and for BOTH halves. Antigravity is the
    near miss: ``agy --conversation <id>`` resumes one, but no flag lets the runner choose the id on
    turn 1 -- the id would have to be read back out of the first turn's output, which has not been
    verified in the container. A platform that could
    open a conversation but not resume it would run its "second turn" as a FRESH session with no
    memory of the draft, where "nothing was filed" is true for a reason unrelated to the gate.
    Claude's pair was verified by hand in this container (2026-10-08, ``claude-haiku-5-5``): the
    resumed turn recalled a word only the first turn had been told.
    """
    if platform != "claude":
        return None
    return f"{preset_agent_command(platform, model, skill)} {session_flag}"
