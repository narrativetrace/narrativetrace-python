# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""A registry case installs a marketplace and a plugin, which are USER-level state. The one place
they may land is a throwaway configuration directory the trial owns -- never the configuration the
person running the trial works in.
"""

from __future__ import annotations

import stat
from pathlib import Path

import isolated_agent_config as config
import pytest


class TestEnvironment:
    def test_points_every_vendor_tool_at_the_trials_own_directories(self, tmp_path: Path) -> None:
        env = config.env(tmp_path)

        assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "config")
        assert env["npm_config_cache"] == str(tmp_path / "npm-cache")

    def test_leaves_home_alone(self, tmp_path: Path) -> None:
        """``HOME`` is where the uv cache and the resolved toolchains live: a trial that moved it
        would re-download every dependency before the agent did anything."""
        assert "HOME" not in config.env(tmp_path)

    def test_opts_the_registry_tool_out_of_telemetry(self, tmp_path: Path) -> None:
        assert config.env(tmp_path)["DO_NOT_TRACK"] == "1"

    def test_the_agent_only_environment_is_the_configuration_directory(
        self, tmp_path: Path
    ) -> None:
        """Every trial gets this much -- the one entry that keeps a trial from inheriting the
        configuration, and therefore the skills, of the person running it."""
        assert config.agent_config_env(tmp_path) == {
            "CLAUDE_CONFIG_DIR": str(config.config_dir(tmp_path))
        }


class TestSeedLogin:
    def test_seeds_the_subscription_login_and_nothing_else_of_the_real_configuration(
        self, tmp_path: Path
    ) -> None:
        real = tmp_path / "real"
        real.mkdir()
        (real / ".credentials.json").write_text('{"token":"t"}', encoding="utf-8")
        (real / "history.jsonl").write_text("somebody's shell history", encoding="utf-8")
        (real / "projects").mkdir()
        work = tmp_path / "work"

        assert config.seed_login(real, work) is True

        isolated = config.config_dir(work)
        assert (isolated / ".credentials.json").read_text(encoding="utf-8") == '{"token":"t"}'
        assert not (isolated / "history.jsonl").exists()
        assert not (isolated / "projects").exists()
        assert (real / ".credentials.json").read_text(encoding="utf-8") == '{"token":"t"}'

    def test_is_a_no_op_when_the_real_configuration_carries_no_login_file(
        self, tmp_path: Path
    ) -> None:
        """A configuration with no login is the ordinary state of a machine that authenticates some
        other way. Seeding is then a no-op, not a failure: whether the agent can start is the
        agent's own answer, and a crash here would blame the harness for it."""
        real = tmp_path / "real"
        real.mkdir()
        work = tmp_path / "work"

        assert config.seed_login(real, work) is False

        assert config.config_dir(work).is_dir()
        assert not (config.config_dir(work) / ".credentials.json").exists()

    def test_creates_the_package_cache_the_registry_tool_writes_to(self, tmp_path: Path) -> None:
        real = tmp_path / "real"
        real.mkdir()
        work = tmp_path / "work"

        config.seed_login(real, work)

        assert config.npm_cache_dir(work).is_dir()

    def test_writes_the_copied_login_owner_only(self, tmp_path: Path) -> None:
        """The copy is a credential: nobody but its owner may read it."""
        real = tmp_path / "real"
        real.mkdir()
        (real / ".credentials.json").write_text('{"token":"t"}', encoding="utf-8")
        work = tmp_path / "work"

        config.seed_login(real, work)

        copy = config.config_dir(work) / ".credentials.json"
        assert stat.S_IMODE(copy.stat().st_mode) == 0o600

    def test_replaces_a_login_left_by_an_earlier_seeding(self, tmp_path: Path) -> None:
        real = tmp_path / "real"
        real.mkdir()
        (real / ".credentials.json").write_text("first", encoding="utf-8")
        work = tmp_path / "work"
        config.seed_login(real, work)
        (real / ".credentials.json").write_text("second", encoding="utf-8")

        config.seed_login(real, work)

        copy = config.config_dir(work) / ".credentials.json"
        assert copy.read_text(encoding="utf-8") == "second"


class TestGuardClauses:
    """Both halves of the isolation are load-bearing, so neither may be silently absent: a missing
    work directory would put the trial's installs in the ambient configuration, and a missing real
    configuration would leave a logged-out agent."""

    @pytest.mark.parametrize(
        "call",
        [
            lambda: config.config_dir(None),  # type: ignore[arg-type]
            lambda: config.npm_cache_dir(None),  # type: ignore[arg-type]
            lambda: config.agent_config_env(None),  # type: ignore[arg-type]
            lambda: config.env(None),  # type: ignore[arg-type]
        ],
    )
    def test_refuses_a_missing_work_directory(self, call: object) -> None:
        with pytest.raises(TypeError, match="work directory"):
            call()  # type: ignore[operator]

    def test_refuses_a_missing_real_configuration(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError, match="real configuration"):
            config.seed_login(None, tmp_path)  # type: ignore[arg-type]


class TestRealConfigDir:
    def test_the_override_wins_when_one_is_set(self) -> None:
        assert config.resolve_real_config_dir("/elsewhere/cfg", "/home/someone") == Path(
            "/elsewhere/cfg"
        )

    def test_falls_back_to_the_conventional_directory_under_home(self) -> None:
        assert config.resolve_real_config_dir(None, "/home/someone") == Path(
            "/home/someone/.claude"
        )

    def test_a_blank_override_is_no_override(self) -> None:
        assert config.resolve_real_config_dir("  ", "/home/someone") == Path(
            "/home/someone/.claude"
        )

    def test_refuses_to_guess_when_home_is_not_set(self) -> None:
        """``HOME`` is asked and nothing else is: every CLI this harness drives reads that variable,
        and this container's uid has no passwd entry, so ``Path.home()`` returns the literal ``~``
        -- a relative path with no login under it, which turns into a logged-out agent two steps
        later. Java's own first registry trial was lost to the JVM's ``user.home`` being ``?``
        there, so an absent HOME says so here instead of guessing."""
        with pytest.raises(RuntimeError, match=r"HOME"):
            config.resolve_real_config_dir(None, None)

        with pytest.raises(RuntimeError, match=r"HOME"):
            config.resolve_real_config_dir(None, "")

    def test_reads_the_ambient_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
        monkeypatch.setenv("HOME", "/home/dev")

        assert config.real_config_dir() == Path("/home/dev/.claude")

        monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/elsewhere/cfg")
        assert config.real_config_dir() == Path("/elsewhere/cfg")
