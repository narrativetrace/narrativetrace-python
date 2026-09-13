# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Nightly docs-vs-published contract gate (docs-vs-published-gate-2026-09-12.md §2, ruling 4):
resolves the published version the same way `scripts/verify_publication_registry.py`'s own lookup
works (the newest reachable `v*` tag, else PyPI's own JSON "latest" for `narrativetrace`),
installs it into a FRESH temporary environment -- never this checkout's own `.venv`, never the
workspace's editable install standing in for the real answer -- and runs `contract-probe/`'s
runner against it. This is the "fresh-temp-dir install helper" the design note asks for, mirroring
Java's `scripts/contract-check.sh`; never per commit -- it makes real registry calls (see
`documentation/security-tooling.md`'s per-commit/nightly split, which this gate follows for the
same reason).

Usage::

    python -m scripts.contract_check [<version>] [--dry-run]

`<version>` is optional, exactly like `scripts/verify_publication.py`: omit it (as the nightly
schedule does) and the LAST PUBLISHED version is checked. Pass it explicitly to check exactly that
version instead (a manual rehearsal, or a specific past release).
"""

from __future__ import annotations

import argparse
import os
import subprocess  # nosec B404 - fixed argv at every call site below, read-only or a pinned `uv run`
import sys
import tempfile
from pathlib import Path

from scripts.llms_banner import fetch_latest_version
from scripts.verify_publication_packages import (
    WorkspacePackage,
    derive_workspace_packages,
    latest_git_tag_version,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PROBE_DIR = REPO_ROOT / "contract-probe"
CORE_PACKAGE_NAME = "narrativetrace"


class UsageError(ValueError):
    """A CLI argument or resolution problem -- printed as a one-line error, exit code 2, never a
    traceback."""


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


def resolve_published_version(explicit: str | None) -> tuple[str, str]:
    """`explicit` wins; else the newest reachable `v*` git tag; else PyPI's own JSON "latest" for
    `narrativetrace` -- never this checkout's own `pyproject.toml` version, which moves on to the
    next unreleased number the instant a release is cut (mirrors `verify-publication.sh`'s own
    `resolve_version`)."""
    if explicit:
        return explicit, "explicit version argument"
    tagged = latest_git_tag_version(_git_tags())
    if tagged:
        return tagged, f"newest v* tag reachable from HEAD (v{tagged})"
    latest = fetch_latest_version(CORE_PACKAGE_NAME)
    if latest:
        return latest, f"PyPI JSON latest for {CORE_PACKAGE_NAME} (no v* tag found)"
    raise UsageError(
        f"no <version> given, no v* tag reachable from HEAD, and PyPI's JSON API is unreachable "
        f"for {CORE_PACKAGE_NAME!r}. Pass <version> explicitly."
    )


def _publishable_packages() -> list[WorkspacePackage]:
    return [p for p in derive_workspace_packages(REPO_ROOT) if p.publish]


def _with_arguments(version: str) -> list[str]:
    """One `--with <name>==<version>` per publishable workspace package, resolved from the
    workspace's own manifests (never a hand-kept list) -- these, plus `contract-probe`'s own
    declared `pyyaml` dependency, are the only packages the probe's environment ever contains."""
    args: list[str] = []
    for package in _publishable_packages():
        args += ["--with", f"{package.name}=={version}"]
    return args


def _probe_command(version: str, out_path: Path) -> list[str]:
    return [
        "uv",
        "run",
        "--project",
        str(CONTRACT_PROBE_DIR),
        *_with_arguments(version),
        "python",
        "-m",
        "contract_probe.runner",
        f"--version={version}",
        f"--contract={REPO_ROOT / 'documentation' / 'contract.yaml'}",
        f"--out={out_path}",
    ]


def _print_dry_run(version: str, source: str, out_path: Path) -> None:
    print(f"Dry run -- would check version {version} ({source}), no network, no install.")
    print("Would run:")
    print("  " + " ".join(_probe_command(version, out_path)))


def _fresh_environment(cache_dir: Path) -> dict[str, str]:
    """Copies the current environment (`PATH`, `HOME`, ... -- uv and its own toolchain discovery
    need them) and overrides only `UV_CACHE_DIR`, so this run can never reuse a wheel or
    resolution already warmed by this checkout's own development work -- the one thing that must
    be fresh. `VIRTUAL_ENV` is dropped: a caller that itself ran under `uv run` (this repository's
    own workspace venv) would otherwise leak a path that does not match `contract-probe`'s own
    project venv, which uv only warns about and ignores -- dropping it avoids the spurious
    warning entirely."""
    env = {**os.environ, "UV_CACHE_DIR": str(cache_dir)}
    env.pop("VIRTUAL_ENV", None)
    return env


def run_contract_probe(version: str, out_path: Path, *, cache_dir: Path) -> int:
    """Installs every publishable package at `version` into a FRESH environment (an isolated uv
    cache directory -- never this checkout's own `~/.cache/uv`, never a locally-built wheel of the
    same version standing in for the real registry answer) and runs `contract-probe`'s runner
    against it. Returns the runner's own exit code (0 only if every applicable entry holds)."""
    print(
        f">> installing every publishable package at {version} into a fresh uv cache and "
        "running contract-probe",
        file=sys.stderr,
    )
    result = subprocess.run(  # nosec B603 - fixed program name ("uv"), argv built entirely above
        _probe_command(version, out_path),
        cwd=REPO_ROOT,
        env=_fresh_environment(cache_dir),
        check=False,
    )
    return result.returncode


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contract_check.py",
        description="Nightly docs-vs-published contract gate against the real PyPI index.",
    )
    parser.add_argument(
        "version",
        nargs="?",
        default=None,
        help="Version to check (default: the newest v* tag, else PyPI's own latest).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved version and the command that would run; no network, no install.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        version, source = resolve_published_version(args.version)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.version is None:
        print(f">> no <version> given -- checking the last published version: {version} ({source})")

    with tempfile.TemporaryDirectory(prefix="contract-check-") as workdir:
        work_path = Path(workdir)
        out_path = work_path / "contract-result.json"
        if args.dry_run:
            _print_dry_run(version, source, out_path)
            return 0
        cache_dir = work_path / "uv-cache"
        status = run_contract_probe(version, out_path, cache_dir=cache_dir)
        if out_path.is_file():
            print(f">> result JSON: {out_path.name}", file=sys.stderr)
            print(out_path.read_text(encoding="utf-8"))
        return status


if __name__ == "__main__":
    sys.exit(main())
