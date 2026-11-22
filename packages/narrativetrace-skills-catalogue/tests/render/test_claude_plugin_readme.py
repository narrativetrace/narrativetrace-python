# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The plugin README is what Anthropic's directory shows as the listing description, and its
security scan reads it for behaviour the plugin does not disclose. These tests derive each
disclosed fact from the catalogue's own data independently of the renderer, so a command added to
a skill and not disclosed fails here."""

from __future__ import annotations

import re
from pathlib import Path

from narrativetrace_skills.catalogue_index import MARKETPLACE, SKILLS
from narrativetrace_skills.lints import executed_commands
from narrativetrace_skills.render.claude_plugin_readme import render_claude_plugin_readme

from narrativetrace.doctor.feedback_cli import BODY_FILE, DRAFT_FILE


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


_README = render_claude_plugin_readme(MARKETPLACE, SKILLS)
_FENCE = re.compile(r"```.*?```", re.DOTALL)
# A `python -c` script that changes a file: a write, a delete, a directory or a subprocess that
# could. The README may call the scripts it lists read-only only while none of these appears.
_WRITES = re.compile(
    r"write_text|write_bytes|\bopen\(|\.unlink|rmdir|mkdir|\.rename|\.touch|shutil|\bos\."
)


def _all_commands() -> list[str]:
    seen: list[str] = []
    for skill in SKILLS:
        for command in executed_commands(skill):
            if command not in seen:
                seen.append(command)
    return seen


class TestSkillList:
    def test_lists_every_skill_by_name_with_its_descriptions_first_sentence(self) -> None:
        for skill in SKILLS:
            first_sentence = re.split(r"(?<=\.)\s", skill.description, maxsplit=1)[0]
            line = next(ln for ln in _README.splitlines() if f"`{skill.canonical_name}`" in ln)
            assert line.startswith("- "), skill.canonical_name
            assert first_sentence.split(":", 1)[0].strip().rstrip(".") in line

    def test_states_how_many_skills_the_plugin_carries(self) -> None:
        assert f"carries {len(SKILLS)} skills and nothing else" in _README


class TestWordCount:
    def test_has_at_least_forty_words_outside_code_blocks(self) -> None:
        # The directory's rule: words inside code blocks are not counted.
        assert len(_FENCE.sub(" ", _README).split()) >= 40


class TestWhatTheSkillsRun:
    def test_lists_every_command_the_skills_run_verbatim(self) -> None:
        commands = _all_commands()
        assert len(commands) > 20
        for command in commands:
            assert command in _README, command

    def test_lists_commands_in_code_blocks_grouped_by_the_tool_that_runs_them(self) -> None:
        assert "- `uv`" in _README
        assert "- `git`" in _README
        git_commands = [c for c in _all_commands() if c.startswith("git ")]
        assert git_commands
        git_section = _README.split("- `git`", 1)[1]
        for command in git_commands:
            assert command in git_section

    def test_says_the_plugin_pre_approves_no_command(self) -> None:
        assert "pre-approves no command" in _README
        assert "allowed-tools" not in _README

    def test_names_the_commands_that_write_and_says_the_rest_only_read(self) -> None:
        for statement in (
            "uv add",
            "pyproject.toml",
            "uv.lock",
            "narrativetrace-approve",
            "feedback draft",
            "feedback-draft.md",
            "uv run narrativetrace init --dry-run",
        ):
            assert statement in _README, statement

    def test_every_python_c_script_it_calls_read_only_really_only_reads(self) -> None:
        # The README states the listed `python -c` checks only read; pin that on the scripts.
        scripts = [c for c in _all_commands() if "python -c" in c]
        assert scripts
        for script in scripts:
            assert _WRITES.search(script) is None, script

    def test_names_the_files_the_install_skill_edits(self) -> None:
        assert "adds the NarrativeTrace packages" in _README
        assert "renames the identifiers its report flags" in _README


class TestWhatTheSkillsFetch:
    def test_says_the_skills_pin_no_version_and_the_package_manager_resolves_the_newest(
        self,
    ) -> None:
        assert "pin no NarrativeTrace version" in _README
        assert "PyPI" in _README
        assert "newest release" in _README

    def test_names_every_package_the_skills_add_and_nothing_pinned(self) -> None:
        added: set[str] = set()
        for command in _all_commands():
            if command.startswith("uv add"):
                added.update(t for t in command.split()[2:] if not t.startswith("-"))
        assert added == {"narrativetrace", "narrativetrace-clarity"}
        for name in added:
            assert f"`{name}`" in _README

    def test_says_the_skills_fetch_nothing_else(self) -> None:
        assert "fetch nothing else" in _README


class TestWhatTheSkillsSend:
    def test_states_precisely_what_the_feedback_skill_does_and_that_nothing_is_sent(self) -> None:
        for statement in (
            "narrativetrace-feedback",
            "pre-filled",
            f"{MARKETPLACE.repository}/issues/new",
            "nothing is sent",
            "never opens",
        ):
            assert statement in _README, statement

    def test_names_the_two_files_the_verb_itself_writes(self) -> None:
        assert f"`{DRAFT_FILE}`" in _README
        assert f"`{BODY_FILE}`" in _README

    def test_says_the_skill_never_runs_gh_or_the_command_the_verb_prints(self) -> None:
        assert "never runs `gh`" in _README
        assert "never runs the command" in _README

    def test_says_nothing_leaves_the_machine_from_the_plugin_itself(self) -> None:
        assert "Nothing leaves your machine from this plugin" in _README
        assert "no hooks" in _README


class TestLicenseAndLinks:
    def test_carries_the_license_homepage_and_repository_from_the_listing(self) -> None:
        assert MARKETPLACE.license in _README
        assert MARKETPLACE.homepage in _README
        assert MARKETPLACE.repository in _README

    def test_names_the_install_commands_from_the_listing(self) -> None:
        assert "/plugin marketplace add narrativetrace/narrativetrace-python" in _README
        assert f"/plugin install {MARKETPLACE.name}@{MARKETPLACE.name}" in _README


def _apache_section_7() -> str:
    """Section 7 of this repository's own LICENSE-APACHE, each line quoted with ``> ``."""
    text = (_repo_root() / "LICENSE-APACHE").read_text(encoding="utf-8")
    start = text.index("7. Disclaimer of Warranty.")
    section = text[start : text.index("\n\n", start)]
    return "\n".join("> " + line.strip() for line in section.splitlines())


class TestNoWarrantyNotice:
    def test_states_the_plain_no_warranty_line_in_the_license_section(self) -> None:
        license_section = _README[_README.index("## License and links") :]
        assert (
            "NarrativeTrace is provided as is: no warranty, and no guarantee that it fits your "
            "purpose. Use it at your own risk." in license_section
        )

    def test_quotes_the_apache_disclaimer_exactly_as_license_apache_has_it(self) -> None:
        assert _apache_section_7() in _README

    def test_links_the_apache_license_file_and_names_the_limitation_of_liability_section(
        self,
    ) -> None:
        assert f"{MARKETPLACE.repository}/blob/main/LICENSE-APACHE" in _README
        assert "Section 8" in _README
        assert "Limitation of Liability" in _README

    def test_says_the_runtime_the_skills_install_is_under_the_business_source_license(
        self,
    ) -> None:
        assert (
            "The NarrativeTrace runtime that these skills install is licensed under the "
            "Business Source License 1.1; see "
            f"[LICENSE]({MARKETPLACE.repository}/blob/main/LICENSE)." in _README
        )

    def test_limits_the_section_eight_pointer_to_the_apache_licensed_parts(self) -> None:
        assert "limits liability further (Apache-licensed parts only)." in _README


class TestStability:
    def test_carries_no_version_number_so_a_release_leaves_it_byte_identical(self) -> None:
        assert re.search(r"\d+\.\d+\.\d+", _README) is None

    def test_renders_byte_identically_every_time(self) -> None:
        assert render_claude_plugin_readme(MARKETPLACE, SKILLS) == _README

    def test_the_committed_file_equals_a_fresh_render(self) -> None:
        committed = (_repo_root() / ".claude" / "README.md").read_text(encoding="utf-8")
        assert committed == _README
