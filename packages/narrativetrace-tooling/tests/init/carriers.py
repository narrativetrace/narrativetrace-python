# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Carriers for tests: the REAL one this repository checks in, and a small hand-built one whose
skill list a test controls.

The real carrier is what every end-to-end case uses, because a fixture carrier proves only that the
fixture is consistent. The hand-built one exists so a planner case can say "two skills" and assert
on two actions instead of on the whole catalogue.

Mirrors the Java port's ``Carriers`` test helper.
"""

from __future__ import annotations

import json
from pathlib import Path

from narrativetrace_tooling.init.carrier import Carrier, open_carrier
from narrativetrace_tooling.init.catalogue import SkillFlavour

FAKE_COORDINATE = "narrativetrace-skills==1.2.3"
"""The coordinate :func:`fake` stamps with — its directory is named like an unpacked wheel."""

_FAKE_DIRECTORY = "narrativetrace_skills-1.2.3"


def repo_root() -> Path:
    """The workspace root, found by walking up rather than by counting directories: mutmut runs this
    suite from a ``mutants/`` copy one level deeper."""
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


def real_carrier_directory() -> Path:
    """This repository's own checked-in carrier payload — the tree the published wheel ships."""
    return repo_root() / "packages" / "narrativetrace-skills" / "skills"


def bundled_carrier_directory() -> Path:
    """The byte-identical copy the core distribution bundles as package data."""
    return repo_root() / "packages" / "narrativetrace" / "src" / "narrativetrace" / "_skills"


def real() -> Carrier:
    """The carrier this repository checks in, opened from its own directory."""
    return open_carrier(real_carrier_directory())


def fake(parent: Path, *names: str) -> Carrier:
    """An exploded carrier under ``parent``, carrying one page per name in both flavours."""
    root = parent / _FAKE_DIRECTORY / "skills"
    skills = []
    for name in names:
        for flavour in SkillFlavour:
            _write(root / page_path(name, flavour), body(name, flavour))
        skills.append(
            {
                "name": name,
                "description": f"What {name} does.",
                "agents": page_path(name, SkillFlavour.AGENTS),
                "claude": page_path(name, SkillFlavour.CLAUDE),
            }
        )
    _write(root / "catalogue.json", json.dumps({"runtime": "python", "skills": skills}))
    return open_carrier(parent / _FAKE_DIRECTORY)


def body(name: str, flavour: SkillFlavour) -> str:
    """The page text :func:`fake` carries for one skill and flavour."""
    return f"---\nname: {name}\nflavour: {flavour.value}\n---\n\nbody of {name}\n"


def page_path(name: str, flavour: SkillFlavour) -> str:
    """The carrier-relative path :func:`fake` writes one flavour's page to."""
    return f"{flavour.value}/{name}/SKILL.md"


def _write(file: Path, content: str) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding="utf-8")
