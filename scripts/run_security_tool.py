# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Resolve-or-fetch-then-run wrapper for security binaries with no PyPI package.

gitleaks and OSV-Scanner are Go static binaries with no wheel to `uv sync`. This script looks
for the named tool on `PATH` first; failing that, it downloads a pinned release asset into
`.tools/bin/` (gitignored, cached across runs), verifies it against the asset's published
SHA-256 before ever executing it, and execs the tool with the remaining CLI arguments forwarded
verbatim.

Network-dependent, so only `poe secrets-scan` and `poe osv-scan` call this — both are on-demand
or scheduled-CI entry points, never the pre-commit gate or `poe check` (see
documentation/security-tooling.md). A tool that cannot be resolved (offline, unsupported
platform, download/checksum failure) is never a silent green (mirrors a 2026-09-08 audit's
finding in the Java spec repo and its `ScannerGateSupport` fix — the exact failure class that
bit the .NET first release, where a secrets scanner had gracefully skipped for the project's
entire life): locally the caller still gets exit 0 (a WARN on stderr, so a machine without the
tools keeps a working `check`), but in CI (`CI` set) or under
`NARRATIVETRACE_SECURITY_REQUIRED=true`, a missing binary now fails the run. Every outcome is
recorded under `build/reports/security-scans/<tool>.status` as `ran-clean` or `skipped: <reason>`
(no file at all reads back as `never-ran`), so "ran clean" and "never ran" stay distinguishable
after the fact, by humans and by jobs alike.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".tools" / "bin"
DOWNLOAD_TIMEOUT_SECONDS = 30
SECURITY_SCAN_STATUS_DIR = REPO_ROOT / "build" / "reports" / "security-scans"


@dataclass(frozen=True)
class MissingBinaryDecision:
    """What the caller must do when a tool's binary is absent: fail, or warn with `message`."""

    fail: bool
    message: str


def security_scanners_required() -> bool:
    """Whether this context demands a scan actually ran: CI, or the explicit opt-in flag."""
    return os.environ.get("NARRATIVETRACE_SECURITY_REQUIRED") == "true" or bool(
        os.environ.get("CI")
    )


def decide_missing_binary(tool: str, required: bool) -> MissingBinaryDecision:
    """The decision for a missing `tool` binary, given whether scanners are `required` here."""
    if required:
        return MissingBinaryDecision(
            fail=True,
            message=(
                f"{tool} could not be resolved and security scanners are required in this "
                "context (CI, or NARRATIVETRACE_SECURITY_REQUIRED=true)."
            ),
        )
    return MissingBinaryDecision(
        fail=False,
        message=(
            f"{tool} not found on PATH and could not be fetched — scan SKIPPED. A skipped scan "
            "is NOT a clean scan: nothing was checked."
        ),
    )


def record_skipped(reports_dir: Path, tool: str, reason: str) -> None:
    """Records that `tool`'s scan was skipped for `reason`; readable back via `scan_status`."""
    _write_status(reports_dir, tool, f"skipped: {reason}")


def record_ran_clean(reports_dir: Path, tool: str) -> None:
    """Records that `tool` actually ran and reported nothing; readable back via `scan_status`."""
    _write_status(reports_dir, tool, "ran-clean")


def scan_status(reports_dir: Path, tool: str) -> str:
    """`tool`'s most recent recorded outcome: `ran-clean`, `skipped: ...`, or `never-ran` when
    no scan has recorded a status at all — three states, so silence cannot masquerade as
    coverage."""
    status_file = reports_dir / f"{tool}.status"
    return status_file.read_text(encoding="utf-8").strip() if status_file.is_file() else "never-ran"


def _write_status(reports_dir: Path, tool: str, status: str) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / f"{tool}.status").write_text(status + "\n", encoding="utf-8")


@dataclass(frozen=True)
class Asset:
    url: str
    sha256: str
    archive_member: str | None = None  # set when url is a tar.gz containing this member


# Pinned versions, platform matrix taken from each tool's own published release checksums.
# Bump deliberately: replace url + sha256 together from the new release's checksum file.
TOOLS: dict[str, dict[tuple[str, str], Asset]] = {
    "gitleaks": {
        ("Linux", "x86_64"): Asset(
            "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/"
            "gitleaks_8.30.1_linux_x64.tar.gz",
            "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
            "gitleaks",
        ),
        ("Linux", "aarch64"): Asset(
            "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/"
            "gitleaks_8.30.1_linux_arm64.tar.gz",
            "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080",
            "gitleaks",
        ),
        ("Darwin", "arm64"): Asset(
            "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/"
            "gitleaks_8.30.1_darwin_arm64.tar.gz",
            "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5",
            "gitleaks",
        ),
        ("Darwin", "x86_64"): Asset(
            "https://github.com/gitleaks/gitleaks/releases/download/v8.30.1/"
            "gitleaks_8.30.1_darwin_x64.tar.gz",
            "dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709",
            "gitleaks",
        ),
    },
    "osv-scanner": {
        ("Linux", "x86_64"): Asset(
            "https://github.com/google/osv-scanner/releases/download/v2.5.1/"
            "osv-scanner_linux_amd64",
            "f9f25499a2c8cc367b3af45df2ea7eeca7fbccceab9c35079968f4b3652194be",
        ),
        ("Linux", "aarch64"): Asset(
            "https://github.com/google/osv-scanner/releases/download/v2.5.1/"
            "osv-scanner_linux_arm64",
            "3d0f5aa5a6baa8eb32bcef247388e149ef6030a6634ccae6fa0d62681fb27a6d",
        ),
        ("Darwin", "arm64"): Asset(
            "https://github.com/google/osv-scanner/releases/download/v2.5.1/"
            "osv-scanner_darwin_arm64",
            "75c44d6332f892a1e56286f4105a98ed751ae28d215ca0a8b65cc00d84103054",
        ),
        ("Darwin", "x86_64"): Asset(
            "https://github.com/google/osv-scanner/releases/download/v2.5.1/"
            "osv-scanner_darwin_amd64",
            "9f89beb6c3d784893cb1cae0a3d56c529bfe91075418c2f9440c45b79654198b",
        ),
    },
}


def _fetch_verified(tool: str, asset: Asset) -> bytes:
    """Downloads `asset.url` and returns its bytes, raising if they don't match `asset.sha256`."""
    if not asset.url.startswith("https://"):
        raise ValueError(f"refusing non-https URL for {tool}: {asset.url}")
    with urllib.request.urlopen(  # nosec B310 # nosemgrep - https checked above, url from TOOLS
        asset.url, timeout=DOWNLOAD_TIMEOUT_SECONDS
    ) as response:
        raw: bytes = response.read()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != asset.sha256:
        raise ValueError(f"checksum mismatch for {tool}: expected {asset.sha256}, got {digest}")
    return raw


def _extract_member(tool: str, archive_member: str, raw: bytes, dest: Path) -> None:
    """Writes the single `archive_member` file out of the tar.gz bytes `raw` to `dest`."""
    tmp_archive = CACHE_DIR / f"{tool}.tar.gz"
    tmp_archive.write_bytes(raw)
    try:
        with tarfile.open(tmp_archive) as tar:
            member = tar.extractfile(archive_member)
            if member is None:
                raise ValueError(f"{archive_member!r} not found in {tool} archive")
            dest.write_bytes(member.read())
    finally:
        tmp_archive.unlink()


def _download(tool: str, asset: Asset) -> Path:
    """Fetches `asset`, verifies its checksum, and returns the executable path in CACHE_DIR."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    raw = _fetch_verified(tool, asset)

    dest = CACHE_DIR / tool
    if asset.archive_member:
        _extract_member(tool, asset.archive_member, raw, dest)
    else:
        dest.write_bytes(raw)

    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return dest


def resolve(tool: str) -> Path | None:
    """Finds `tool` on PATH, in the local cache, or fetches it; None if none of that works."""
    on_path = shutil.which(tool)
    if on_path:
        return Path(on_path)

    cached = CACHE_DIR / tool
    if cached.is_file():
        return cached

    asset = TOOLS.get(tool, {}).get((platform.system(), platform.machine()))
    if asset is None:
        print(
            f"warning: no {tool} release known for {platform.system()}/{platform.machine()} "
            "— skipping (install it manually, or add a platform entry to "
            "scripts/run_security_tool.py)",
            file=sys.stderr,
        )
        return None

    try:
        return _download(tool, asset)
    except (OSError, ValueError) as exc:
        print(f"warning: could not fetch {tool} ({exc}) — skipping", file=sys.stderr)
        return None


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: run_security_tool.py <tool> [args...]", file=sys.stderr)
        return 2
    tool, *tool_args = argv
    binary = resolve(tool)
    if binary is None:
        decision = decide_missing_binary(tool, security_scanners_required())
        record_skipped(SECURITY_SCAN_STATUS_DIR, tool, "binary not resolved")
        print(f"warning: {decision.message}", file=sys.stderr)
        return 1 if decision.fail else 0
    result = subprocess.run(  # nosec B603 # binary is resolve()'s own path, never untrusted input
        [str(binary), *tool_args], check=False
    )
    if result.returncode == 0:
        record_ran_clean(SECURITY_SCAN_STATUS_DIR, tool)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
