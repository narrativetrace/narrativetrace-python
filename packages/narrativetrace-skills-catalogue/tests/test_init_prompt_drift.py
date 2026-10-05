# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Docs-as-tests rule 8, applied to the init prompt: a prompt we publish is a prompt we replay,
so the published text and the replayed text may never drift apart.

The prompt lives in seven places — the English README and its three language mirrors (the prompt
itself stays in English on purpose; only the sentence introducing it is translated),
``documentation/llms.txt``, and the two Tier B cases whose ``prompt.md`` IS the prompt and nothing
else. This test is what makes "seven copies" safe: they are byte-identical or ``poe check`` fails.

Editing the prompt means editing all seven. The mirrors' blob-hash headers are a separate concern
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

_CASES_WHOSE_PROMPT_IS_THE_WHOLE_FILE = (
    "packages/narrativetrace-skills-catalogue/evals/add-narrative-tracing/"
    "init-prompt-empty-project/prompt.md",
    "packages/narrativetrace-skills-catalogue/evals/add-narrative-tracing/"
    "init-prompt-existing-project/prompt.md",
)

_FIRST_LINE = "Set up NarrativeTrace in this project and show me its first trace."

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
        copies = [_fenced_init_prompt(_REPO_ROOT / page) for page in _PAGES_WITH_A_FENCED_BLOCK]
        copies += [
            (_REPO_ROOT / case).read_text(encoding="utf-8").strip()
            for case in _CASES_WHOSE_PROMPT_IS_THE_WHOLE_FILE
        ]

        assert len(copies) == 7
        assert copies == [copies[0]] * len(copies)

    def test_the_replayed_prompt_is_the_one_an_agent_is_told_to_paste(self) -> None:
        published = _fenced_init_prompt(_REPO_ROOT / "README.md")

        assert published.startswith(_FIRST_LINE)
        assert "https://narrativetrace.ai/python/llms.txt" in published
        assert "uv run narrativetrace doctor" in published
        assert "never disable redaction" in published

    def test_trigger_yaml_carries_no_copy_of_the_prompt(self) -> None:
        """Unlike the seven pinned copies above, the trigger phrasing files are not one of them —
        a future copy pasted there would silently make it an eighth, ungated copy (the exact gap
        this port's own Java reference closed in its own milestone 5)."""
        for relative in _TRIGGER_FILES:
            text = (_REPO_ROOT / relative).read_text(encoding="utf-8")
            assert _FIRST_LINE not in text, f"{relative} now carries the init prompt"
