# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The always-on pointer an agent reads on its next session. Its text is the catalogue's own, so the
cases here pin the frame around it: the markers, the detected facts, and which commands a project is
told to run.

Named after the Java port's ``AgentsMdBlockTest`` so the two lists diff.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import carriers
import pytest

from narrativetrace_tooling.init import marked_block
from narrativetrace_tooling.init.agents_md_block import DOCS_URL, render_agents_md_block
from narrativetrace_tooling.init.project_state import ProjectState

MISSING: Any = None


def uv_project() -> ProjectState:
    return ProjectState(uv_project=True)


EXPECTED_BLOCK = """<!-- narrativetrace:start narrativetrace-skills==1.2.3 -->
## NarrativeTrace

NarrativeTrace turns this project's own method names, parameters and return values into a readable \
execution narrative — no log statements. Rendered traces land in `out/traces`.

### Agent skills installed in this project

- `doctor` — What doctor does.

### Commands

- `uv run narrativetrace doctor` — diagnose this install; read-only, and every finding names the \
skill that fixes it
- `uv run narrativetrace init --dry-run` — show what re-installing the skills would change, as a \
diff
- `uv run narrativetrace uninstall` — remove exactly what the installer wrote, this section included

Documentation: https://narrativetrace.ai/python/llms.txt

### Rules

- Apply `@not_traced` to the real parameter. Importing the marker and never applying it protects \
nothing.
- Never disable redaction to make a trace easier to read.
- Commit `.approved.nt` files; never commit a `.received.nt`.

<!-- narrativetrace:end -->
"""
"""Every word of the section, for one carrier and one snapshot.

This is the one assertion in the file that is not about a fragment, and it is the one that matters
most: the section is a PUBLISHED artifact, read by an agent that has no other context, so each
sentence is a contract rather than decoration. The fragment cases below say what each part is FOR;
this one says what it is. It is also what makes the renderer's prose mutation-testable at all — a
suite of "contains" assertions lets every reworded string survive.
"""


class TestTheSectionWordForWord:
    def test_renders_exactly_this_for_one_carrier_and_one_snapshot(self, tmp_path: Path) -> None:
        state = ProjectState(uv_project=True, output_directory="out/traces")

        block = render_agents_md_block(carriers.fake(tmp_path, "doctor"), state)

        assert block == EXPECTED_BLOCK


class TestTheSection:
    def test_is_one_well_formed_region_stamped_with_the_carrier(self) -> None:
        carrier = carriers.real()

        block = render_agents_md_block(carrier, uv_project())

        scan = marked_block.scan(block)
        assert scan.problems == ()
        assert len(scan.regions) == 1
        assert scan.regions[0].coordinate == carrier.coordinate
        assert block.startswith("<!-- narrativetrace:start ")
        assert block.endswith("<!-- narrativetrace:end -->\n")

    def test_lists_every_skill_with_its_catalogue_description_verbatim_and_in_order(self) -> None:
        carrier = carriers.real()

        block = render_agents_md_block(carrier, uv_project())

        previous = -1
        for skill in carrier.skills:
            line = f"- `{skill.name}` — {skill.description}"
            assert line in block
            at = block.index(line)
            assert at > previous, "catalogue order is kept"
            previous = at

    def test_names_where_traces_land(self, tmp_path: Path) -> None:
        carrier = carriers.fake(tmp_path, "a")

        detected = render_agents_md_block(carrier, ProjectState(output_directory="out/traces"))
        default = render_agents_md_block(carrier, ProjectState())

        assert "`out/traces`" in detected
        assert "`narrative-traces`" in default

    def test_points_at_the_runtimes_documentation_index(self, tmp_path: Path) -> None:
        block = render_agents_md_block(carriers.fake(tmp_path, "a"), uv_project())

        assert DOCS_URL == "https://narrativetrace.ai/python/llms.txt"
        assert f"Documentation: {DOCS_URL}" in block

    def test_carries_the_three_rules_the_evaluations_keep_tripping_over(
        self, tmp_path: Path
    ) -> None:
        block = render_agents_md_block(carriers.fake(tmp_path, "a"), uv_project())

        assert "`@not_traced`" in block
        assert "redaction" in block
        assert ".received.nt" in block

    def test_says_nothing_about_a_version_beyond_the_machine_written_stamp(
        self, tmp_path: Path
    ) -> None:
        block = render_agents_md_block(carriers.fake(tmp_path, "a"), uv_project())
        without_the_marker = block[block.index("\n") :]

        assert re.search(r"\d+\.\d+\.\d+", without_the_marker) is None

    def test_is_the_same_text_for_the_same_inputs(self, tmp_path: Path) -> None:
        carrier = carriers.fake(tmp_path, "a", "b")

        assert render_agents_md_block(carrier, uv_project()) == render_agents_md_block(
            carrier, uv_project()
        )

    def test_renders_with_unix_line_endings_and_no_stray_carriage_return(
        self, tmp_path: Path
    ) -> None:
        """A caller writing into a CRLF file converts the whole block at once, so the block itself
        has exactly one kind of terminator to convert."""
        block = render_agents_md_block(carriers.fake(tmp_path, "a"), uv_project())

        assert "\r" not in block


class TestTheCommandsItNames:
    """Whatever registers the verbs must register exactly these names, or the section sends every
    reader to a command that does not exist."""

    def test_names_the_uv_run_form_in_a_uv_project(self, tmp_path: Path) -> None:
        block = render_agents_md_block(carriers.fake(tmp_path, "a"), uv_project())

        assert "`uv run narrativetrace doctor`" in block
        assert "`uv run narrativetrace init --dry-run`" in block
        assert "`uv run narrativetrace uninstall`" in block

    def test_names_the_bare_command_where_there_is_no_uv_project(self, tmp_path: Path) -> None:
        block = render_agents_md_block(carriers.fake(tmp_path, "a"), ProjectState())

        assert "`narrativetrace doctor`" in block
        assert "`narrativetrace init --dry-run`" in block
        assert "`narrativetrace uninstall`" in block
        assert "uv run" not in block

    def test_names_the_preview_flag_this_runtime_actually_has(self, tmp_path: Path) -> None:
        """``--dry-run``, not the Java plugin's ``--diff``: nothing shadows ``--dry-run`` after
        ``uv run``, and the two runtimes' spellings are deliberately different."""
        block = render_agents_md_block(carriers.fake(tmp_path, "a"), uv_project())

        assert "--dry-run" in block
        assert "--diff" not in block


class TestGuards:
    def test_refuses_to_render_without_a_carrier_or_a_project(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError, match=r"carrier and a project state"):
            render_agents_md_block(MISSING, uv_project())
        with pytest.raises(TypeError, match=r"carrier and a project state"):
            render_agents_md_block(carriers.fake(tmp_path, "a"), MISSING)
