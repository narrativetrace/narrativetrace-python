# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""PyPI presence/absence polling for `poe verify-publication` — pure decision logic plus a thin
default network client, split the same way `verify-publication-registry.ts` and .NET's
`PublicationVerificationSupport.ClassifyHttpStatus`/`Worst` are: the classification and the
backoff loop take an injected `fetch_status`/`sleep`/`now`, so the whole thing is unit-testable
without a real clock or a real registry, and `scripts.verify_publication`'s own tests exercise it
that way.

Two independent checks share the same registry, for opposite reasons:

- **Presence** (a package that SHOULD be on PyPI at this release's version) — classified in three
  non-PRESENT shades, not one flat "missing": `LAGGING` (the project exists on PyPI, just not yet
  this exact version — ordinary sync lag, worth a retry), `NOT_YET_PUBLISHED` (the project itself
  has never been created on PyPI at all — PyPI rate-limits NEW PROJECT creation, not new versions
  of an existing one, so part of a release can legitimately stay in this state for a while while
  the rest of it is already live), and `MISSING` (anything else — a 5xx, no response at all — not
  explained by ordinary propagation and worth attention). Collapsing the first two into one "not
  found" verdict would misreport a real partial release as a broken one: it must read as "some
  packages aren't out yet", never as "the release is broken".
- **Absence** (`narrativetrace-security-tests`, which must NEVER reach PyPI) — a single project-
  level lookup, no version, no polling: if the project exists under this name AT ALL, any version,
  that is already the violation — the exact defect class that let a benchmark harness project
  publish once in the .NET port.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from time import monotonic
from time import sleep as time_sleep
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

DEFAULT_REGISTRY_BASE = "https://pypi.org/pypi"
DEFAULT_FETCH_TIMEOUT_SECONDS = 15.0

Presence = Literal["PRESENT", "LAGGING", "NOT_YET_PUBLISHED", "MISSING"]
AbsenceVerdict = Literal["ABSENT", "PRESENT", "UNKNOWN"]

FetchStatus = Callable[[str], int]
Sleep = Callable[[float], None]
Clock = Callable[[], float]


@dataclass(frozen=True)
class RegistryTarget:
    name: str
    version: str


def project_url(registry_base: str, name: str) -> str:
    """The project-level metadata URL — every release of `name`, no specific version."""
    return f"{registry_base}/{name}/json"


def version_url(registry_base: str, name: str, version: str) -> str:
    """The exact-version metadata URL PyPI's legacy JSON API serves."""
    return f"{registry_base}/{name}/{version}/json"


def default_fetch_status(url: str) -> int:
    """GETs `url` and returns its HTTP status; `0` for a request that never got a response
    (DNS/connect/timeout failure) — the same "no answer at all" sentinel the java script's `curl`
    and the ts tool's `catch { return 0 }` both use, so it classifies as MISSING below, never as a
    silent PRESENT/ABSENT."""
    try:
        with urlopen(  # nosec B310 - registry_base is DEFAULT_REGISTRY_BASE (https, fixed) unless
            # a caller deliberately overrides it (e.g. a rehearsal against TestPyPI), never
            # untrusted input.
            url,
            timeout=DEFAULT_FETCH_TIMEOUT_SECONDS,
        ) as response:
            return int(response.status)
    except HTTPError as exc:
        return exc.code
    except URLError:
        return 0


def classify_presence(version_status: int, project_status: int | None) -> Presence:
    """`version_status`/`project_status` are the HTTP statuses of `version_url`/`project_url` for
    the same package. `project_status` is only consulted when `version_status` is 404 — callers
    may pass `None` otherwise (see `check_presence_one`, which fetches it lazily) — but a 404
    version status with no `project_status` is a caller bug, not a value to guess at."""
    if version_status == 200:
        return "PRESENT"
    if version_status != 404:
        return "MISSING"
    if project_status is None:
        raise ValueError("project_status is required to classify a 404 version_status")
    return "NOT_YET_PUBLISHED" if project_status == 404 else "LAGGING"


def classify_absence(project_status: int) -> AbsenceVerdict:
    """`project_status` is the HTTP status of `project_url` for a package that must never exist."""
    if project_status == 404:
        return "ABSENT"
    if project_status == 200:
        return "PRESENT"
    return "UNKNOWN"


def check_presence_one(
    target: RegistryTarget, fetch_status: FetchStatus, registry_base: str = DEFAULT_REGISTRY_BASE
) -> Presence:
    version_status = fetch_status(version_url(registry_base, target.name, target.version))
    if version_status != 404:
        return classify_presence(version_status, project_status=None)
    project_status = fetch_status(project_url(registry_base, target.name))
    return classify_presence(version_status, project_status)


def check_absence_one(
    name: str, fetch_status: FetchStatus, registry_base: str = DEFAULT_REGISTRY_BASE
) -> AbsenceVerdict:
    return classify_absence(fetch_status(project_url(registry_base, name)))


@dataclass(frozen=True)
class PollOptions:
    registry_base: str = DEFAULT_REGISTRY_BASE
    timeout_seconds: float = 1800.0
    initial_backoff_seconds: float = 15.0
    max_interval_seconds: float = 60.0
    fetch_status: FetchStatus = field(default=default_fetch_status)
    sleep: Sleep = field(default=time_sleep)
    now: Clock = field(default=monotonic)
    on_pending: Callable[[list[RegistryTarget]], None] | None = None


def poll_presence(
    targets: Iterable[RegistryTarget], options: PollOptions | None = None
) -> dict[str, Presence]:
    """Polls every target until each reads `PRESENT` or the overall deadline elapses, backing off
    between rounds (doubling, capped at `max_interval_seconds`) — one round rechecks every
    not-yet-PRESENT target together, sharing one deadline, never a separate timeout per package
    (mirrors `pollPresence` in `verify-publication-registry.ts`)."""
    opts = options or PollOptions()
    all_targets = list(targets)
    deadline = opts.now() + opts.timeout_seconds
    wait = opts.initial_backoff_seconds
    verdicts = {
        t.name: check_presence_one(t, opts.fetch_status, opts.registry_base) for t in all_targets
    }
    while True:
        pending = [t for t in all_targets if verdicts[t.name] != "PRESENT"]
        if not pending or opts.now() >= deadline:
            return verdicts
        if opts.on_pending is not None:
            opts.on_pending(pending)
        opts.sleep(wait)
        wait = min(wait * 2, opts.max_interval_seconds)
        for target in pending:
            verdicts[target.name] = check_presence_one(
                target, opts.fetch_status, opts.registry_base
            )
