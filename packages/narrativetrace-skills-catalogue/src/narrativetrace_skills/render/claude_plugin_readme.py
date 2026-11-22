# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders ``.claude/README.md``: the plugin folder's README, which Anthropic's plugin directory
shows as the listing description and whose security scan reads for behaviour the plugin does not
disclose. It says what the plugin is, what its skills run, fetch and send, and under which licence
it ships.

Every disclosed fact is derived from the typed catalogue, never typed twice: the skill names and
their one-line summaries from each skill's ``description``, every command the skills run (their
steps' commands and their ``verify`` commands, which run in the same turn) from
:func:`~narrativetrace_skills.lints.executed_commands`, listed verbatim and grouped by the tool
that runs them, the packages the install steps add from those commands, and the licence, homepage
and repository from the
:class:`~narrativetrace_skills.marketplace.MarketplaceListing`. A command added to a skill reaches
the README with the next render, and ``scripts/skills_render.py --check`` fails the build until it
does.

The README names no version number, for the reason the plugin manifest does not: a release that
leaves the skills alone leaves this folder byte-identical. The Python skills install without a
version, so there is no lookup to disclose: the package manager resolves the newest release from
PyPI.

**@llmNote** The statements about what the feedback skill sends are not derived: they are the
contract of that skill (it drafts, shows the draft, asks once, then prints a URL and never opens
it), pinned by the skill's own tests and by the verb's own design (it makes no request of its own,
opens no browser and runs no ``gh``; its third channel, which the skill never uses, only asks an
installed ``gh`` whether it is signed in). The two file names it states are the verb's own
(``narrativetrace.doctor.feedback_cli``), pinned by a test. Change them only together with that
skill.
"""

from __future__ import annotations

import re

from narrativetrace_skills.lints import executed_commands
from narrativetrace_skills.marketplace import MarketplaceListing
from narrativetrace_skills.skill import Skill, first_token

_NO_WARRANTY = (
    "NarrativeTrace is provided as is: no warranty, and no guarantee that it fits your purpose. "
    "Use it at your own risk."
)

# Section 7 of LICENSE-APACHE, line for line; a test pins it against that file.
_APACHE_DISCLAIMER = (
    "7. Disclaimer of Warranty. Unless required by applicable law or",
    "agreed to in writing, Licensor provides the Work (and each",
    'Contributor provides its Contributions) on an "AS IS" BASIS,',
    "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or",
    "implied, including, without limitation, any warranties or conditions",
    "of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A",
    "PARTICULAR PURPOSE. You are solely responsible for determining the",
    "appropriateness of using or redistributing the Work and assume any",
    "risks associated with Your exercise of permissions under this License.",
)

_DRAFT_FILE = "build/narrativetrace/feedback/feedback-draft.md"
_BODY_FILE = "build/narrativetrace/feedback/feedback-body.md"
_GITHUB = "https://github.com/"
_PYTHON_SCRIPT = "uv run python -c"


def render_claude_plugin_readme(listing: MarketplaceListing, skills: tuple[Skill, ...]) -> str:
    return "".join(
        [
            _introduction(listing, skills),
            _skill_list(skills),
            _what_the_skills_run(skills),
            _what_the_skills_fetch(skills),
            _what_the_skills_send(listing),
            _license_and_links(listing),
        ]
    )


def _introduction(listing: MarketplaceListing, skills: tuple[Skill, ...]) -> str:
    return (
        f"# {listing.name}\n\n"
        f"{listing.description} This plugin carries {len(skills)} skills and nothing else: no "
        "hooks, no MCP servers, no executables. Each skill is a page of instructions that Claude "
        "follows in your Python project, using your own `uv` and Claude Code's normal permission "
        "prompts.\n\n"
        "Install it from this repository's marketplace:\n\n"
        "```\n"
        f"/plugin marketplace add {_slug(listing)}\n"
        f"/plugin install {listing.name}@{listing.name}\n"
        "```\n\n"
    )


def _skill_list(skills: tuple[Skill, ...]) -> str:
    lines = "".join(f"- `{skill.canonical_name}`: {_summary(skill)}\n" for skill in skills)
    return f"## Skills\n\n{lines}\n"


def _distinct_commands(skills: tuple[Skill, ...]) -> list[str]:
    """Every distinct command the skills run, verifies included, in the order the catalogue first
    spells them."""
    return list(dict.fromkeys(command for skill in skills for command in executed_commands(skill)))


def _code_block(lines: list[str]) -> str:
    return "```\n" + "\n".join(lines) + "\n```\n\n"


def _installs(command: str) -> bool:
    return command.startswith(("uv add", "uv sync"))


def _runs_your_code(command: str) -> bool:
    """Your tests and your own scripts: the project's code, not NarrativeTrace's."""
    return command.startswith("uv run pytest") or (
        command.startswith("uv run python ") and not command.startswith(_PYTHON_SCRIPT)
    )


def _reads_only(command: str) -> bool:
    return command.startswith(_PYTHON_SCRIPT)


def _group_of(command: str) -> str:
    """Which bucket a command belongs to, by what it does to the project."""
    if first_token(command) == "git":
        return "git"
    if _installs(command):
        return "install"
    if _runs_your_code(command):
        return "yours"
    if _reads_only(command):
        return "reads"
    return "narrativetrace"


def _run_groups(commands: list[str]) -> dict[str, list[str]]:
    """The commands, bucketed by what they do to the project: installs, NarrativeTrace's own
    command line, the project's own code, read-only checks, and git."""
    groups: dict[str, list[str]] = {
        "install": [],
        "narrativetrace": [],
        "yours": [],
        "reads": [],
        "git": [],
    }
    for command in commands:
        groups[_group_of(command)].append(command)
    return groups


def _what_the_skills_run(skills: tuple[Skill, ...]) -> str:
    groups = _run_groups(_distinct_commands(skills))
    return "".join(
        [
            "## What the skills run\n\n",
            "The plugin pre-approves no command. The first time a skill runs one of these in your "
            "project, Claude Code asks you. Every command is listed here exactly as the skills "
            "spell it.\n\n",
            "- `uv`, to add the NarrativeTrace packages to your project and to bring its "
            "environment up to date. `uv add` edits your `pyproject.toml` and `uv.lock`:\n\n",
            _code_block(groups["install"]),
            "- `uv`, to run the NarrativeTrace command line and the two commands the "
            "NarrativeTrace packages put in your project. `uv run narrativetrace init --dry-run` "
            "only previews an install and writes nothing. `feedback draft` and `feedback url` "
            "write the two report files described below, and the Clarity scan writes its report "
            "under `build/narrativetrace/`. Applying an install and promoting an approval "
            "baseline with `narrativetrace-approve` are separate steps that wait for your yes. "
            "Some of these pipe their output into a short `python -c` check that only reads "
            "it:\n\n",
            _code_block(groups["narrativetrace"]),
            "- `uv`, to run your own tests and your own scripts, which are your project's code "
            "and do what they do. NarrativeTrace writes its trace files under `narrative-traces/` "
            "and, in approval mode, `test-narratives/` as they run:\n\n",
            _code_block(groups["yours"]),
            "- `uv run python -c`, short scripts that read files in your project and print them "
            "or check them, and change nothing:\n\n",
            _code_block(groups["reads"]),
            "- `git`, to read which files are in your project:\n\n",
            _code_block(groups["git"]),
            "Two skills also edit your project's files. The install skill adds the NarrativeTrace "
            "packages to your `pyproject.toml` and shows a first trace in a small script; the "
            "Clarity skill adds its package as a development dependency, renames the identifiers "
            "its report flags in your source files, and re-runs your tests after the renames.\n\n",
        ]
    )


def _added_packages(skills: tuple[Skill, ...]) -> list[str]:
    """The distributions the skills' own ``uv add`` commands install, sorted."""
    added = {
        token
        for command in _distinct_commands(skills)
        if command.startswith("uv add")
        for token in command.split()[2:]
        if not token.startswith("-")
    }
    return sorted(added)


def _what_the_skills_fetch(skills: tuple[Skill, ...]) -> str:
    packages = ", ".join(f"`{name}`" for name in _added_packages(skills))
    return (
        "## What the skills fetch\n\n"
        "- The skills pin no NarrativeTrace version and look nothing up themselves: they install "
        "without a version, so `uv` resolves the newest release from PyPI, as it resolves any "
        f"dependency. The packages they add are {packages}.\n"
        "- `uv run` first brings your project's environment up to date from the same index, as it "
        "does whenever you run it.\n"
        "- Your own `uv` then resolves what those packages depend on. The skills fetch nothing "
        "else.\n\n"
    )


def _what_the_skills_send(listing: MarketplaceListing) -> str:
    return (
        "## What the skills send\n\n"
        "Nothing leaves your machine from this plugin: no skill uploads, posts or transmits "
        "anything, and it has no hooks, MCP servers or network code of its own.\n\n"
        "`narrativetrace-feedback` is the one skill about reporting a defect in NarrativeTrace "
        f"itself. It drafts a report from your project into `{_DRAFT_FILE}` and `{_BODY_FILE}` "
        "(the install coordinates, the doctor's JSON report and at most one structural trace, "
        "and it refuses to write a report that carries a value from your own run), shows you the "
        "whole draft, and asks once whether to file it. Only after your yes does it print a "
        f"pre-filled issue address ({listing.repository}/issues/new?...) and the name of the body "
        "file to paste. The command line it runs opens no browser and makes no request of its "
        "own. The skill never opens that address, never runs the command it prints, and never "
        "runs `gh`: nothing is sent unless you open the address yourself, in your own browser, "
        "under your own account, and the issue you file is public.\n\n"
    )


def _license_and_links(listing: MarketplaceListing) -> str:
    quoted = "\n".join(f"> {line}" for line in _APACHE_DISCLAIMER)
    return (
        "## License and links\n\n"
        f"The skills in this plugin are licensed under {listing.license}.\n\n"
        f"- Homepage: {listing.homepage}\n"
        f"- Repository: {listing.repository}\n\n"
        f"{_NO_WARRANTY}\n\n"
        f"The Apache-2.0 text, [LICENSE-APACHE]({listing.repository}/blob/main/LICENSE-APACHE), "
        f"section 7:\n\n{quoted}\n\n"
        'Section 8, "Limitation of Liability", of the same file limits liability further '
        "(Apache-licensed parts only).\n\n"
        "The NarrativeTrace runtime that these skills install is licensed under the Business "
        f"Source License 1.1; see [LICENSE]({listing.repository}/blob/main/LICENSE).\n"
    )


def _summary(skill: Skill) -> str:
    """The first sentence of the description; a "Use when" lead-in is cut at its first colon."""
    description = skill.description
    end = description.find(". ")
    sentence = description if end < 0 else description[: end + 1]
    if sentence.startswith("Use when") and ":" in sentence:
        return f"{sentence[: sentence.index(':')]}."
    return sentence


def _slug(listing: MarketplaceListing) -> str:
    """``owner/name`` of a GitHub repository URL, the form ``/plugin marketplace add`` takes."""
    return re.sub(f"^{re.escape(_GITHUB)}", "", listing.repository)
