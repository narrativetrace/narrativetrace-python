# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Post-publish verification for the PyPI release — the python-native `poe verify-publication`
entry point (invoked as `python -m scripts.verify_publication`, not a shell script), run OUTSIDE
the pipeline that built the release.

Mirrors `narrative-trace-ts/tools/verify-publication.ts` and narrative-trace-dotnet's
`VerifyPublication` build target; java's `scripts/verify-publication.sh` is the original reference
all three, including this one, port from. Four checks:

1. Every publishable package — derived from the workspace itself
   (`verify_publication_packages.py`, never a hand-kept list) — is polled for presence on the real
   pypi.org, honestly distinguishing PRESENT / LAGGING (still propagating) / NOT_YET_PUBLISHED
   (the project has never been created — PyPI rate-limits NEW PROJECT creation, so part of a
   release can legitimately stay in this state while the rest is already live) / MISSING
   (something actually wrong). A partial release must read as "some packages aren't out yet",
   never as "the release is broken".
2. `narrativetrace-security-tests`, which must NEVER publish, is checked for absence — the exact
   check that caught a real stray publication in the .NET port.
3. Every PRESENT publishable package is checked against PyPI's Integrity API for a PEP 740
   attestation bound to the exact published bytes (`verify_publication_provenance.py`) —
   ATTESTED / NOT_ATTESTED / PARTIAL / UNKNOWN per package, a package with no provenance always a
   distinct, visible finding, never silently folded into a pass. This is the exact gap that let
   the 0.1.0 release report green while four of its eight packages shipped with a bootstrap API
   token before any Trusted Publisher existed for them, so no attestation and none possible after
   the fact. See `PROVENANCE_SCOPE_NOTE` for exactly what this does and does not prove.
4. A consumer smoke test installs from the real index into a throwaway, isolated environment and
   runs this repository's OWN documented quickstart (`verify_publication_smoke.py`).

Never a per-commit gate: it makes real network calls, and PyPI's own propagation, while normally
fast, is not instant. A manual publish-checklist step and the nightly canary's payload — see
`.github/workflows/verify-publication.yml`.
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404 - fixed argv below, used only to read `git tag` output
import sys
from pathlib import Path

from scripts.verify_publication_packages import (
    WorkspacePackage,
    derive_workspace_packages,
    latest_git_tag_version,
)
from scripts.verify_publication_provenance import (
    PROVENANCE_SCOPE_NOTE,
    FileProvenanceCheck,
    PackageProvenanceReport,
    ProvenanceFetchError,
    check_package_provenance,
    default_fetch_json,
    skipped_provenance_report,
)
from scripts.verify_publication_registry import (
    DEFAULT_REGISTRY_BASE,
    AbsenceVerdict,
    PollOptions,
    Presence,
    RegistryTarget,
    check_absence_one,
    default_fetch_status,
    poll_presence,
    project_url,
    version_url,
)
from scripts.verify_publication_smoke import (
    DEFAULT_INDEX_URL,
    SmokeResult,
    run_core_recipe_smoke_test,
    run_pytest_plugin_smoke_test,
    skipped_pytest_plugin_result,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_PACKAGE_NAME = "narrativetrace"
PYTEST_PLUGIN_PACKAGE_NAME = "narrativetrace-pytest"


class UsageError(ValueError):
    """A CLI argument problem — printed as a one-line error, exit code 2, never a traceback."""


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="verify_publication.py",
        description="Post-publish verification against the real PyPI index.",
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="Version to verify (default: the latest 'v*' git tag, else the core package's own "
        "pyproject.toml version).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the packages/URLs that would be checked; no network calls, no smoke test.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1800.0,
        help="Overall registry-poll deadline in seconds (default: 1800).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=60.0,
        help="Steady-state polling interval once backoff has ramped up, in seconds (default: 60).",
    )
    parser.add_argument(
        "--packages",
        default=None,
        help="Comma/space-separated subset of publishable package names to check (default: "
        "every publishable package the workspace declares).",
    )
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL, help=argparse.SUPPRESS)
    return parser


def _git_tags() -> list[str]:
    try:
        result = subprocess.run(  # nosec B603, B607 - fixed argv, read-only git query
            ["git", "tag", "--list", "v*", "--sort=-version:refname"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    return result.stdout.splitlines() if result.returncode == 0 else []


def resolve_version(all_packages: list[WorkspacePackage], explicit: str | None) -> str:
    """`explicit` wins; else the latest release tag; else the core package's own declared
    version — never silently defaulting to "whatever happens to build" (mirrors
    `resolveVersion` in `verify-publication.ts`)."""
    if explicit:
        return explicit
    tagged = latest_git_tag_version(_git_tags())
    if tagged:
        return tagged
    core = next((p for p in all_packages if p.name == CORE_PACKAGE_NAME), None)
    if core is None:
        raise UsageError(
            f"no version given, no release tag found, and {CORE_PACKAGE_NAME!r} is not a "
            "workspace member"
        )
    return core.version


def _parse_packages_arg(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [name for name in re.split(r"[,\s]+", raw.strip()) if name]


def select_publishable(
    all_packages: list[WorkspacePackage], requested: list[str] | None
) -> list[WorkspacePackage]:
    """Every publishable package, or the `requested` subset — every requested name is checked
    against the derived publishable set first, so a typo narrows to nothing silently checked
    rather than being dropped (mirrors `publish.yml`'s own subset-dispatch validation)."""
    publishable = [p for p in all_packages if p.publish]
    if requested is None:
        return publishable
    by_name = {p.name: p for p in publishable}
    unknown = [name for name in requested if name not in by_name]
    if unknown:
        raise UsageError(f"not a publishable package: {', '.join(unknown)}")
    return [by_name[name] for name in requested]


def _skip_reason(verdict: Presence | None, name: str, version: str) -> str:
    if verdict is None:
        return f"{name} is outside this run's --packages scope"
    return f"{name} is {verdict} at {version} — not yet available to smoke-test"


def _provenance_or_skip(
    presence: dict[str, Presence], package: WorkspacePackage, version: str
) -> PackageProvenanceReport:
    """Provenance is only meaningful once a package is actually on the index at this version —
    mirrors `_run_core_smoke_or_skip`/`_run_pytest_smoke_or_skip`'s own presence gating, for the
    same reason: querying the Integrity API for a version the presence poll has not confirmed
    PRESENT fails on an ordinary 404, a true statement but the wrong one. A registry-metadata
    fetch failure on an otherwise-PRESENT package (a transient 5xx, not the honest 'no
    provenance' 404 the check itself distinguishes) is reported as a distinct UNKNOWN finding
    rather than crashing the whole run."""
    verdict = presence.get(package.name)
    if verdict != "PRESENT":
        return skipped_provenance_report(
            package.name, version, _skip_reason(verdict, package.name, version)
        )
    try:
        return check_package_provenance(package.name, version, default_fetch_json)
    except ProvenanceFetchError as exc:
        failure = FileProvenanceCheck(
            filename="<registry metadata>", verdict="UNKNOWN", detail=str(exc)
        )
        return PackageProvenanceReport(name=package.name, version=version, files=(failure,))


def _run_core_smoke_or_skip(
    presence: dict[str, Presence], version: str, index_url: str
) -> SmokeResult:
    verdict = presence.get(CORE_PACKAGE_NAME)
    if verdict != "PRESENT":
        return SmokeResult(
            "core-recipe", "SKIPPED", _skip_reason(verdict, CORE_PACKAGE_NAME, version)
        )
    return run_core_recipe_smoke_test(version, index_url)


def _run_pytest_smoke_or_skip(
    presence: dict[str, Presence], version: str, index_url: str
) -> SmokeResult:
    verdict = presence.get(PYTEST_PLUGIN_PACKAGE_NAME)
    if verdict != "PRESENT":
        return skipped_pytest_plugin_result(
            _skip_reason(verdict, PYTEST_PLUGIN_PACKAGE_NAME, version)
        )
    return run_pytest_plugin_smoke_test(version, index_url)


def _print_dry_run(
    targets: list[RegistryTarget], must_not_publish: list[str], version: str, index_url: str
) -> None:
    print(
        f"Dry run — no network calls, no smoke test. Would check presence of {len(targets)} "
        f"package(s) at {version}:\n"
    )
    for target in targets:
        print(f"  {version_url(DEFAULT_REGISTRY_BASE, target.name, target.version)}")
    print("\nWould check ABSENCE (must never appear on the index, at any version) of:")
    for name in must_not_publish:
        print(f"  {project_url(DEFAULT_REGISTRY_BASE, name)}")
    print(
        f"\nSmoke test would install narrativetrace=={version} from {index_url} and run the "
        "README's core trace_object/MarkdownRenderer recipe; narrativetrace-pytest=="
        f"{version}'s first-10-minutes.md recipe runs only if the presence poll finds it PRESENT."
    )
    print(
        "\nWould also check every PRESENT package above against PyPI's Integrity API for a "
        f"bound PEP 740 attestation ({PROVENANCE_SCOPE_NOTE})"
    )


def _print_provenance_section(
    targets: list[RegistryTarget], provenance: dict[str, PackageProvenanceReport]
) -> None:
    print(f"\n{'PROVENANCE (PEP 740 attestation)':<45}STATUS")
    for target in targets:
        report = provenance[target.name]
        print(f"{f'{target.name}@{target.version}':<45}{report.status}")
        for check in report.files:
            print(f"  {check.filename:<43}{check.verdict} — {check.detail}")
    print(f"\nScope note: {PROVENANCE_SCOPE_NOTE}")


def _print_report(
    targets: list[RegistryTarget],
    presence: dict[str, Presence],
    must_not_publish: list[WorkspacePackage],
    absence: dict[str, AbsenceVerdict],
    provenance: dict[str, PackageProvenanceReport],
    smoke_results: tuple[SmokeResult, ...],
) -> None:
    print(f"\n{'PACKAGE':<45}STATUS")
    for target in targets:
        print(f"{f'{target.name}@{target.version}':<45}{presence[target.name]}")
    print(f"\n{'MUST NOT PUBLISH':<45}STATUS")
    for package in must_not_publish:
        print(f"{package.name:<45}{absence[package.name]}")
    _print_provenance_section(targets, provenance)
    print()
    for smoke in smoke_results:
        print(f"Smoke test [{smoke.tier}]: {smoke.verdict} — {smoke.detail}")


def _all_ok(
    presence: dict[str, Presence],
    absence: dict[str, AbsenceVerdict],
    provenance: dict[str, PackageProvenanceReport],
    smoke_results: tuple[SmokeResult, ...],
) -> bool:
    presence_ok = all(verdict in ("PRESENT", "NOT_YET_PUBLISHED") for verdict in presence.values())
    absence_ok = all(verdict == "ABSENT" for verdict in absence.values())
    provenance_ok = all(report.ok for report in provenance.values())
    smoke_ok = all(smoke.verdict != "FAILED" for smoke in smoke_results)
    return presence_ok and absence_ok and provenance_ok and smoke_ok


def run(args: argparse.Namespace) -> int:
    all_packages = derive_workspace_packages(REPO_ROOT)
    must_not_publish = [p for p in all_packages if not p.publish]
    selected = select_publishable(all_packages, _parse_packages_arg(args.packages))
    version = resolve_version(all_packages, args.version)
    targets = [RegistryTarget(p.name, version) for p in selected]

    if args.dry_run:
        _print_dry_run(targets, [p.name for p in must_not_publish], version, args.index_url)
        return 0

    print(
        f"Verifying {len(targets)} package(s) at {version} against the real PyPI index "
        f"({args.index_url})"
    )
    options = PollOptions(
        timeout_seconds=args.timeout,
        max_interval_seconds=args.interval,
        on_pending=lambda pending: print(
            f">> not yet present, retrying: {', '.join(t.name for t in pending)}", file=sys.stderr
        ),
    )
    presence = poll_presence(targets, options)
    absence = {
        p.name: check_absence_one(p.name, default_fetch_status, DEFAULT_REGISTRY_BASE)
        for p in must_not_publish
    }
    provenance = {p.name: _provenance_or_skip(presence, p, version) for p in selected}
    smoke_results = (
        _run_core_smoke_or_skip(presence, version, args.index_url),
        _run_pytest_smoke_or_skip(presence, version, args.index_url),
    )

    _print_report(targets, presence, must_not_publish, absence, provenance, smoke_results)
    return 0 if _all_ok(presence, absence, provenance, smoke_results) else 1


def main(argv: list[str]) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        return run(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
