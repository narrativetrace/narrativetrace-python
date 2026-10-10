# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Docs-as-tests rule 8, applied to the init prompt: a prompt we publish is a prompt we replay,
so the published text and the replayed text may never drift apart.

The prompt lives in the English README and its three language mirrors (the prompt itself stays in
English on purpose; only the sentence introducing it is translated), in ``documentation/llms.txt``,
and in every Tier B case whose ``prompt.md`` IS the prompt and nothing else. This test is what makes
that safe: they are byte-identical or ``poe check`` fails.

The case copies are DISCOVERED rather than listed — every ``prompt.md`` under ``evals/`` whose first
line is the prompt's — with the four expected paths asserted to be among them. A listed-only
comparison cannot see a copy nobody listed, and the registry cases of Phase 4 milestone 4 were
exactly that: two new copies of the published prompt in two new case directories.

Editing the prompt means editing every copy. The mirrors' blob-hash headers are a separate concern
(``poe translation-check``); this test only compares the prompt block.
"""

from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


_REPO_ROOT = _repo_root()

_PAGES_WITH_A_FENCED_BLOCK = (
    "README.md",
    "LEAME.md",
    "LEIAME.md",
    "自述文件.md",
    "documentation/llms.txt",
)

_EVALS_DIR = _REPO_ROOT / "packages" / "narrativetrace-skills-catalogue" / "evals"

_CASES_THAT_MUST_REPLAY_THE_PROMPT = (
    "add-narrative-tracing/init-prompt-empty-project/prompt.md",
    "add-narrative-tracing/init-prompt-existing-project/prompt.md",
    "add-narrative-tracing/registry-claude-marketplace/prompt.md",
    "add-narrative-tracing/registry-npx-skills/prompt.md",
)
"""The cases this repository is known to replay the published prompt through. Asserted to be AMONG
the discovered copies, never to be all of them: a new case nobody listed here is still gated."""

_FIRST_LINE = "Set up NarrativeTrace in this project and show me its first trace."


def _discovered_case_copies() -> tuple[Path, ...]:
    """Every ``prompt.md`` under ``evals/`` that opens with the published prompt's first line.

    Discovery, not a list: a copy nobody listed is exactly the copy that drifts, and a case
    directory is cheap to add.
    """
    return tuple(
        sorted(
            path
            for path in _EVALS_DIR.rglob("prompt.md")
            if path.read_text(encoding="utf-8").lstrip().startswith(_FIRST_LINE)
        )
    )


_TRIGGER_FILES = (
    "packages/narrativetrace-skills-catalogue/evals/add-narrative-tracing/trigger.yaml",
    "packages/narrativetrace-skills-catalogue/evals/narrativetrace-doctor/trigger.yaml",
)


def _fenced_init_prompt(page: Path) -> str:
    """The one fenced block on `page` that opens with the prompt's first line, fences stripped."""
    lines = page.read_text(encoding="utf-8").split("\n")
    for index in range(len(lines) - 1):
        if lines[index].startswith("```") and lines[index + 1].startswith(_FIRST_LINE):
            body: list[str] = []
            for line in lines[index + 1 :]:
                if line == "```":
                    return "\n".join(body).strip()
                body.append(line)
            break
    raise AssertionError(f"{page} carries no fenced init-prompt block")


class TestInitPromptDrift:
    def test_every_published_copy_of_the_init_prompt_is_byte_identical(self) -> None:
        case_copies = _discovered_case_copies()
        copies = [_fenced_init_prompt(_REPO_ROOT / page) for page in _PAGES_WITH_A_FENCED_BLOCK]
        copies += [path.read_text(encoding="utf-8").strip() for path in case_copies]

        assert len(copies) == len(_PAGES_WITH_A_FENCED_BLOCK) + len(case_copies)
        assert copies == [copies[0]] * len(copies)

    def test_every_case_known_to_replay_the_prompt_is_among_the_discovered_copies(self) -> None:
        """Discovery finds a copy nobody listed; this finds a LISTED case whose copy stopped being
        the prompt — a case renamed, moved, or quietly rewritten to replay something else."""
        discovered = {path.relative_to(_EVALS_DIR).as_posix() for path in _discovered_case_copies()}

        assert set(_CASES_THAT_MUST_REPLAY_THE_PROMPT) <= discovered

    def test_the_two_registry_cases_replay_the_prompt_and_nothing_of_their_own(self) -> None:
        """A registry case differs from an init-prompt case only in how the pages got there, so its
        prompt is the published text and nothing beside it. A case that added its own sentence —
        "the skills are already installed", say — would measure a prompt nobody publishes."""
        for case in ("registry-claude-marketplace", "registry-npx-skills"):
            prompt = _EVALS_DIR / "add-narrative-tracing" / case / "prompt.md"
            published = _fenced_init_prompt(_REPO_ROOT / "README.md")

            assert prompt.read_text(encoding="utf-8").strip() == published

    def test_the_replayed_prompt_is_the_one_an_agent_is_told_to_paste(self) -> None:
        published = _fenced_init_prompt(_REPO_ROOT / "README.md")

        assert published.startswith(_FIRST_LINE)
        assert "https://narrativetrace.ai/python/llms.txt" in published
        assert "uv run narrativetrace doctor" in published
        assert "never disable redaction" in published

    def test_trigger_yaml_carries_no_copy_of_the_prompt(self) -> None:
        """The trigger phrasing files are not one of the pinned copies, and discovery above does not
        reach them either: it looks only at `prompt.md` files. A copy pasted into a trigger file
        would therefore be an ungated one — the exact gap this port's own Java reference closed in
        its own milestone 5 — so it is named and forbidden here instead."""
        for relative in _TRIGGER_FILES:
            text = (_REPO_ROOT / relative).read_text(encoding="utf-8")
            assert _FIRST_LINE not in text, f"{relative} now carries the init prompt"
