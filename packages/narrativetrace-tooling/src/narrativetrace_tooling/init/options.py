# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What a person asked the installer to do.

INTENT: every flag that changes a plan, in one value the planner takes as input — so a plan is
reproducible from a snapshot, a carrier and this, and from nothing else.

**@llmNote** The defaults write nothing they were not asked to: an existing file is left alone
without :attr:`InitOptions.write_existing`, and a skill directory somebody else owns is left alone
without :attr:`InitOptions.force`. ``InitOptions()`` IS the default set; one changed flag is
``dataclasses.replace(options, force=True)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import Final


@unique
class Scope(Enum):
    """Which half of the install a run covers."""

    SKILLS = "skills"
    """The skill directories only."""

    AGENTS_MD = "agents-md"
    """The managed section and the import line only."""

    BOTH = "both"
    """Both — the default."""

    @property
    def includes_skills(self) -> bool:
        """Whether skill directories are part of this scope."""
        return self is not Scope.AGENTS_MD

    @property
    def includes_agents_md(self) -> bool:
        """Whether the managed section is part of this scope."""
        return self is not Scope.SKILLS


@unique
class Vendor(Enum):
    """Whether the vendor flavour is installed beside the open-standard one."""

    AUTO = "auto"
    """Install it where the project looks like that vendor's."""

    ON = "on"
    """Install it, detected or not."""

    OFF = "off"
    """Never install it."""


@dataclass(frozen=True, slots=True)
class InitOptions:
    """Every flag that changes a plan.

    :param dry_run: compute and show the plan, write nothing, and exit 0 even on a refusal
    :param write_existing: permission to touch a context file that exists and carries no markers
    :param force: permission to overwrite a skill directory that is not ours
    :param scope: which half of the install to plan
    :param vendor_claude: whether the vendor flavour is installed as well
    """

    dry_run: bool = False
    write_existing: bool = False
    force: bool = False
    scope: Scope = Scope.BOTH
    vendor_claude: Vendor = Vendor.AUTO

    def __post_init__(self) -> None:
        if not isinstance(self.scope, Scope):
            raise TypeError(f"an install needs a scope, never {type(self.scope).__name__}")
        if not isinstance(self.vendor_claude, Vendor):
            raise TypeError(
                f"an install needs a vendor rule, never {type(self.vendor_claude).__name__}"
            )


PERMISSIVE: Final = InitOptions(write_existing=True, force=True)
"""Every permission a person can give: what the round-trip properties and an "install everything"
run each ask for."""
