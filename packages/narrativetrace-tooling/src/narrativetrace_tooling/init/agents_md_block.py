# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders the managed section the installer writes into a consumer's ``AGENTS.md``.

INTENT: the always-on pointer. An agent that never saw an install prompt reads this section at the
start of its next session, finds the skills by name, and knows which command diagnoses the project —
the discovery channel that costs no description budget and needs no tool.

What goes in, in this order: one line on what NarrativeTrace is here and where traces land, the
skills with the catalogue's own descriptions, the commands, the documentation pointer, and the three
rules the evaluations keep tripping over.

**@llmNote** Nothing project-specific goes in beyond what the snapshot DETECTED — the output
directory and whether commands should be spelled ``uv run …``. No inference, no generated coding
rules, and no version talk: the coordinate on the opening marker is a machine-written stamp, and it
is the only version this block ever carries.

**@llmNote** The commands named here are a contract with whatever registers the verbs: a section
that names ``init`` when the CLI spells it something else sends every reader to a command that does
not exist. The tests pin the exact spellings, in both the ``uv``-project and bare forms.

**@llmNote** Renders with ``\\n`` throughout. A caller writing into a file that uses another line
ending converts with :func:`~narrativetrace_tooling.init.marked_block.with_eol`.
"""

from __future__ import annotations

from typing import Final

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.carrier import Carrier
from narrativetrace_tooling.init.project_state import ProjectState

DOCS_URL: Final = "https://narrativetrace.ai/python/llms.txt"
"""The runtime's documentation index, the one link an agent needs from here."""

_UV_PREFIX: Final = "uv run "


def render_agents_md_block(carrier: Carrier, state: ProjectState) -> str:
    """The whole section, opening marker through closing marker, ending with a newline."""
    if carrier is None or state is None:
        raise TypeError("a carrier and a project state are needed to render")
    lines = [
        f"{marked_block.START} {carrier.coordinate} -->",
        *_introduction(state),
        *_skills(carrier),
        *_commands(state),
        *_rules(),
        marked_block.END,
    ]
    block = "\n".join(lines) + "\n"
    assert marked_block.scan(block).has_exactly_one_region(), "the block must be one region"
    return block


def _introduction(state: ProjectState) -> list[str]:
    return [
        "## NarrativeTrace",
        "",
        "NarrativeTrace turns this project's own method names, parameters and return values into a"
        " readable execution narrative — no log statements. Rendered traces land in"
        f" `{state.output_directory}`.",
        "",
    ]


def _skills(carrier: Carrier) -> list[str]:
    return [
        "### Agent skills installed in this project",
        "",
        *(f"- `{skill.name}` — {skill.description}" for skill in carrier.skills),
        "",
    ]


def _commands(state: ProjectState) -> list[str]:
    run = _UV_PREFIX if state.uv_project else ""
    return [
        "### Commands",
        "",
        f"- `{run}narrativetrace doctor` — diagnose this install; read-only, and every finding"
        " names the skill that fixes it",
        f"- `{run}narrativetrace init --dry-run` — show what re-installing the skills would change,"
        " as a diff",
        f"- `{run}narrativetrace uninstall` — remove exactly what the installer wrote, this section"
        " included",
        "",
        f"Documentation: {DOCS_URL}",
        "",
    ]


def _rules() -> list[str]:
    return [
        "### Rules",
        "",
        "- Apply `@not_traced` to the real parameter. Importing the marker and never applying it"
        " protects nothing.",
        "- Never disable redaction to make a trace easier to read.",
        "- Commit `.approved.nt` files; never commit a `.received.nt`.",
        "",
    ]
