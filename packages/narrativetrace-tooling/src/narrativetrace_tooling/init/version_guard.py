# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Warns when the carrier an install resolved is not the release this project runs, and never
refuses.

INTENT: a consumer can end up with a skills carrier at one version and the NarrativeTrace release
the project actually resolves at another: a stale ``narrativetrace-skills`` pin, an install that
predates the carrier, a carrier chosen by hand with a path. The pages would then describe a release
the project does not run, and nothing else would say so.

**@llmNote** A warning, never a refusal. Refusing would block the empty-project path the install
prompt serves — where there is no project version at all — and the doctor's own staleness finding
catches the result either way. With no resolvable project version this is SILENT: "cannot tell" is
not a warning.

**@sideEffects** Reads installed-distribution metadata. Never writes, never resolves anything over a
network.
"""

from __future__ import annotations

from importlib import metadata as importlib_metadata

from narrativetrace_tooling.init.carrier import CORE_DISTRIBUTION, Carrier


def project_family_version() -> str | None:
    """The NarrativeTrace release this project resolves, or ``None`` when it resolves none.

    ``None`` is the empty-project answer, and the reason this guard is silent there: a directory
    with no NarrativeTrace installed is exactly the case the install prompt starts from.
    """
    try:
        return importlib_metadata.version(CORE_DISTRIBUTION)
    except importlib_metadata.PackageNotFoundError:
        return None


def version_warning(carrier: Carrier, project_version: str | None) -> str | None:
    """One line naming both versions and the command that aligns them, or ``None`` when there is
    nothing to say.

    :param carrier: the carrier the install resolved
    :param project_version: what :func:`project_family_version` answered
    """
    if carrier is None:
        raise TypeError("a carrier is needed to compare versions")
    if project_version is None:
        return None
    carried = _version_of(carrier.coordinate)
    if carried == project_version:
        return None
    return (
        f"warning: the skills carrier is {carrier.coordinate}, but this project resolves"
        f" {CORE_DISTRIBUTION}=={project_version} — the installed pages will describe a different"
        f" release. Run `uv add '{_SKILLS}=={project_version}'` to line them up, or pass"
        " --from to choose a carrier deliberately."
    )


_SKILLS = "narrativetrace-skills"


def _version_of(coordinate: str) -> str:
    """The version half of a ``<distribution>==<version>`` coordinate."""
    _, separator, version = coordinate.partition("==")
    return version if separator else ""
