# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""INTENT: a throwaway vendor-tool configuration a trial owns, in BOTH directions.

Outward: a marketplace and a plugin are USER-level state -- the only scope the documentation
describes (Phase 4 ruling Q4) -- so a registry trial's installs land in the trial's own directory
and never in the configuration of the person running it.

Inward, and just as load-bearing: no trial inherits that person's configuration either. A trial
driven against the operator's own configuration is driven against the operator's own skills, and
the skill under test becomes one line among dozens -- a red row that would reproduce nowhere else.
"A preset narrower than its prompt measures the sandbox" has a mirror image, and this is it.

Two things stay deliberately OUTSIDE the isolation:

- ``HOME`` is untouched. It is where the uv cache and the resolved interpreters live, and a trial
  that moved it would spend its first minutes re-downloading a toolchain instead of measuring a
  skill.
- The subscription LOGIN is copied in, because a fresh configuration is a logged-out one: the agent
  CLI answers "Not logged in" and the trial measures the harness. Nothing else of the real
  configuration is read, and nothing at all is written back to it.

**@llmNote** The login file is a secret. It is copied owner-only into a directory the runner
deletes when the trial ends, and it is the only file this module ever reads out of the real
configuration -- never the history, the sessions or the projects beside it.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

CONFIG_DIR_VARIABLE = "CLAUDE_CONFIG_DIR"
"""The vendor CLI's own configuration-directory override."""

_HOME_VARIABLE = "HOME"

_LOGIN_FILE = ".credentials.json"
"""The subscription login: the one file a fresh configuration cannot do without."""

_OWNER_ONLY = 0o600


def config_dir(work_dir: Path) -> Path:
    """The isolated configuration directory inside a trial's work directory."""
    _require_work_dir(work_dir)
    return work_dir / "config"


def npm_cache_dir(work_dir: Path) -> Path:
    """Where the package runner caches its downloads -- the ambient one may not be writable."""
    _require_work_dir(work_dir)
    return work_dir / "npm-cache"


def agent_config_env(work_dir: Path) -> dict[str, str]:
    """The isolated configuration, for EVERY trial -- the one entry that keeps a trial from
    inheriting the configuration of the person running it."""
    return {CONFIG_DIR_VARIABLE: str(config_dir(work_dir))}


def env(work_dir: Path) -> dict[str, str]:
    """The above, plus what only a REGISTRY trial needs: a writable package cache and a best-effort
    telemetry opt-out for the registry tool that has one."""
    return {
        **agent_config_env(work_dir),
        "npm_config_cache": str(npm_cache_dir(work_dir)),
        "DO_NOT_TRACK": "1",
    }


def seed_login(real_config: Path, work_dir: Path) -> bool:
    """Creates the isolated configuration and the package cache, and copies the subscription login
    in when ``real_config`` has one.

    :returns: whether a login was found and copied. A caller SAYS which it was: a trial with no
        login does not fail here, it fails three steps later when the agent answers "Not logged
        in", and that is a long way from the cause.
    :sideEffects: creates :func:`config_dir` and :func:`npm_cache_dir`; writes one owner-only copy
        of the login file there. Reads exactly one file of ``real_config`` and writes none.
    """
    if real_config is None:
        raise TypeError("seed_login needs the real configuration directory to read the login from")
    isolated = config_dir(work_dir)
    isolated.mkdir(parents=True, exist_ok=True)
    npm_cache_dir(work_dir).mkdir(parents=True, exist_ok=True)
    login = real_config / _LOGIN_FILE
    if not login.is_file():
        return False
    copy = isolated / _LOGIN_FILE
    shutil.copyfile(login, copy)
    copy.chmod(_OWNER_ONLY)
    assert copy.is_file(), "a seeded login must be on disk"
    return True


def real_config_dir() -> Path:
    """The configuration directory the ambient environment points the vendor CLI at."""
    return resolve_real_config_dir(
        os.environ.get(CONFIG_DIR_VARIABLE), os.environ.get(_HOME_VARIABLE)
    )


def resolve_real_config_dir(config_dir_variable: str | None, home_variable: str | None) -> Path:
    """The override when one is set; otherwise the conventional directory under the home the TOOLS
    use.

    **@llmNote** ``HOME`` is the only home asked for, deliberately: every CLI this harness drives
    reads that variable, and this container's uid has no passwd entry, so :meth:`Path.home` returns
    the literal ``~`` -- a relative path with no login beneath it, which becomes a logged-out agent
    two steps later. Java lost its first registry trial to exactly that (its JVM reported
    ``user.home=?``), so an absent ``HOME`` says so here rather than guessing.
    """
    if config_dir_variable is not None and config_dir_variable.strip():
        return Path(config_dir_variable)
    if home_variable is None or not home_variable.strip():
        raise RuntimeError(
            f"neither {CONFIG_DIR_VARIABLE} nor {_HOME_VARIABLE} is set, so there is no vendor "
            f"configuration to seed the subscription login from -- set {_HOME_VARIABLE} (this "
            "harness never falls back to a platform home: an unresolvable one reads as a "
            "logged-out agent several steps later)"
        )
    return Path(home_variable) / ".claude"


def _require_work_dir(work_dir: Path) -> None:
    if work_dir is None:
        raise TypeError("an isolated configuration needs the work directory it lives in")
