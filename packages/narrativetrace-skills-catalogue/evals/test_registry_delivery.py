# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""How a Tier B case's skill pages got into the project -- by a registry, or by the harness. Most
cases declare no registry and the case is about the prompt; a case that DOES declare one is handed
its pages by the registry tool, because the state the registry leaves behind is what it measures.
"""

from __future__ import annotations

from pathlib import Path

import isolated_agent_config
import pytest
import registry_delivery as delivery
from narrativetrace_skills import MARKETPLACE

_REPO = Path("/repo")
_STAGED = Path("/scratch/staged")
_WORK = Path("/work")


def _case_with(directory: Path, manifest: str) -> Path:
    (directory / "case.json").write_text(manifest, encoding="utf-8")
    return directory


def _repo_root() -> Path:
    """The uv workspace root, found by walking up rather than by counting parents -- under
    ``mutmut`` this file runs from a copied tree one level deeper, where a fixed index points at
    ``packages/`` and every staged-surface assertion would fail for every mutant."""
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


class TestVocabulary:
    def test_knows_the_two_documented_registry_ids_and_nothing_else(self) -> None:
        assert delivery.is_registry("claude-marketplace") is True
        assert delivery.is_registry("npx-skills") is True
        assert delivery.is_registry("gemini-skills") is False
        assert delivery.is_registry("") is False

    def test_the_vocabulary_is_closed_because_a_case_file_is_data(self) -> None:
        """A command string in ``case.json`` would be a shell this harness does not have: each id
        owns the exact argv a documented registry line amounts to, so a case replays what a reader
        runs and can name nothing else."""
        assert delivery.REGISTRIES == ("claude-marketplace", "npx-skills")


class TestStagingCommands:
    def test_stages_heads_registry_surface_as_argv_lists_and_no_shell(self) -> None:
        assert delivery.staging_commands(_REPO, _STAGED) == (
            (
                "git",
                "-C",
                "/repo",
                "archive",
                "--format=tar",
                "-o",
                "/scratch/staged.tar",
                "HEAD",
                "--",
                ".claude-plugin",
                ".claude/skills",
                ".agents/skills",
            ),
            ("tar", "-xf", "/scratch/staged.tar", "-C", "/scratch/staged"),
        )

    def test_writes_the_archive_beside_the_staged_tree_and_never_inside_it(self) -> None:
        """The tar is an artefact of HOW the tree got here, and a registry tool scans everything it
        is pointed at -- a clone of the public repository carries no tarball at its root, and a
        staged tree that does is no longer the thing the case claims to measure."""
        for command in delivery.staging_commands(_REPO, _STAGED):
            assert not [
                argument
                for argument in command
                if argument.startswith(f"{_STAGED}/") and argument.endswith(".tar")
            ]

    def test_stages_out_of_head_and_never_out_of_the_working_tree(self) -> None:
        """A registry serves what was committed, so a trial against uncommitted edits would grade a
        tree no reader can get -- the same reason the publish script stages ``git archive HEAD``."""
        archive = delivery.staging_commands(_REPO, _STAGED)[0]

        assert "HEAD" in archive
        assert archive[:3] == ("git", "-C", "/repo")

    def test_every_staged_path_is_really_in_this_repository(self) -> None:
        """``git archive`` fails outright on a path that is not in the tree, and it would fail at
        TRIAL time -- in a run whose red row says nothing about the product. So the surface is
        checked against the repository on every build instead."""
        repo_root = _repo_root()

        for relative in delivery.REGISTRY_SURFACE:
            assert (repo_root / relative).exists(), f"{relative} is staged for every registry case"


class TestRegistryCommands:
    def test_the_marketplace_delivery_stages_then_adds_installs_and_proves_the_install(
        self,
    ) -> None:
        """The third command is the pre-step's own self-check: a plugin whose inventory cannot be
        read is not installed, and ``details`` exits non-zero for one that is not there, so a
        silently empty install can never pass for a delivered one."""
        plugin = MARKETPLACE.name
        install_id = f"{plugin}@{plugin}"

        commands = delivery.commands_for("claude-marketplace", _REPO, _STAGED)

        assert commands[:2] == delivery.staging_commands(_REPO, _STAGED)
        assert commands[2:] == (
            ("claude", "plugin", "marketplace", "add", "/scratch/staged"),
            ("claude", "plugin", "install", install_id),
            ("claude", "plugin", "details", install_id),
        )

    def test_the_npx_delivery_stages_then_runs_the_documented_add_line_unpinned(self) -> None:
        """Unpinned on purpose: the case exists to keep a PUBLISHED line honest, and a reader types
        no version. Pinning one would freeze the replay against a tool build no reader gets, which
        is the one failure the case is here to catch."""
        commands = delivery.commands_for("npx-skills", _REPO, _STAGED)

        assert commands[:2] == delivery.staging_commands(_REPO, _STAGED)
        assert commands[2:] == (("npx", "--yes", "skills", "add", "/scratch/staged", "-y"),)

    def test_no_delivery_ever_asks_for_a_project_scope(self) -> None:
        """User scope only (ruling Q4): a project-scope marketplace writes a settings file INTO the
        graded project, which is state the case never asked for and the installer would then be
        measured against."""
        for registry in delivery.REGISTRIES:
            for command in delivery.commands_for(registry, _REPO, _STAGED):
                assert "--scope" not in command
                assert "project" not in command

    def test_refuses_an_id_outside_the_vocabulary(self) -> None:
        with pytest.raises(ValueError, match="gemini-skills"):
            delivery.commands_for("gemini-skills", _REPO, _STAGED)  # type: ignore[arg-type]


class TestRegistryForCase:
    def test_reads_the_declared_registry_delivery(self, tmp_path: Path) -> None:
        case_dir = _case_with(tmp_path, '{ "fixture": "f", "registry": "npx-skills" }')

        assert delivery.registry_for_case(case_dir) == "npx-skills"

    def test_a_case_that_declares_no_registry_has_no_pre_step(self, tmp_path: Path) -> None:
        case_dir = _case_with(tmp_path, '{ "fixture": "f" }')

        assert delivery.registry_for_case(case_dir) is None

    def test_a_case_with_no_manifest_at_all_has_no_pre_step(self, tmp_path: Path) -> None:
        assert delivery.registry_for_case(tmp_path) is None

    def test_refuses_an_id_outside_the_vocabulary_rather_than_skipping_the_pre_step(
        self, tmp_path: Path
    ) -> None:
        """A typo must never read as "no registry": the pre-step is the whole arrangement a registry
        case measures, and a case that silently skipped it would pass as a plain prompt replay while
        its name and its ledger row still claimed a registry."""
        case_dir = _case_with(tmp_path, '{ "registry": "gemini-skills" }')

        with pytest.raises(ValueError, match=r"gemini-skills.*claude-marketplace, npx-skills"):
            delivery.registry_for_case(case_dir)

    def test_names_the_offending_manifest(self, tmp_path: Path) -> None:
        case_dir = _case_with(tmp_path, '{ "registry": "" }')

        with pytest.raises(ValueError, match=r"case\.json"):
            delivery.registry_for_case(case_dir)


class TestRegistryDelivery:
    def test_the_ordinary_case_delivers_nothing_runs_nothing_and_changes_no_environment(
        self,
    ) -> None:
        none = delivery.RegistryDelivery()

        assert none.delivers_the_skills is False
        assert none.commands(_REPO) == ()
        assert none.environment == {}

    def test_a_registry_case_runs_that_registrys_commands_against_its_own_staged_tree(self) -> None:
        through = delivery.RegistryDelivery("npx-skills", _WORK)

        assert through.delivers_the_skills is True
        assert through.staged_snapshot == _WORK / "staged"
        assert through.commands(_REPO) == delivery.commands_for(
            "npx-skills", _REPO, _WORK / "staged"
        )

    def test_a_registry_case_runs_every_command_against_the_isolated_configuration(self) -> None:
        through = delivery.RegistryDelivery("claude-marketplace", _WORK)

        assert through.environment == isolated_agent_config.env(_WORK)

    def test_refuses_half_a_delivery(self) -> None:
        """A step with no work directory would run a vendor tool against the ambient configuration
        -- the one outcome the isolation exists to prevent -- and a work directory with no step
        would isolate a trial that installs nothing. Neither half is optional."""
        with pytest.raises(ValueError, match="pre-step and the work directory"):
            delivery.RegistryDelivery("npx-skills", None)

        with pytest.raises(ValueError, match="pre-step and the work directory"):
            delivery.RegistryDelivery(None, _WORK)

    def test_a_delivery_that_delivers_nothing_has_no_staged_tree_to_name(self) -> None:
        with pytest.raises(RuntimeError, match="stages nothing"):
            _ = delivery.RegistryDelivery().staged_snapshot

    def test_refuses_a_registry_outside_the_vocabulary(self) -> None:
        with pytest.raises(ValueError, match="gemini-skills"):
            delivery.RegistryDelivery("gemini-skills", _WORK)  # type: ignore[arg-type]
