# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Regression coverage for `scripts/publish-public.sh`'s trace-gate NAME filter and binary scan.

The trace gate greps the staged snapshot for AI-development markers (`TRACE_PATTERN`) two ways:
staged file CONTENT and staged file NAMES. The content check has always been filtered through
`.publishallow`; the NAME check was not (fixed 2026-09-13, mirroring the TypeScript port's own
`90f7860` fix) -- a cleanly-worded file at an AI-tooling path (e.g. `.claude/skills/**`, a rendered
`render/claude.py`) could never clear the gate by review, only by renaming or deletion.

This extracts the real `TRACE_PATTERN` and `name_hits=` lines out of the actual script (never a
hand-copied duplicate, so the test cannot drift from what actually gates a publish) and runs that
exact snippet against a synthetic staged tree, proving the NAME check is now filtered the same way
the CONTENT check already is -- and still catches an unreviewed hit.

`TestBinaryAssetScan` covers a second, later fix (2026-09-13, family finding): the CONTENT check
above runs `grep -I`, which silently SKIPS binary files rather than reporting them -- a gated word
or this maintainer's identity embedded in an image's tEXt/iTXt chunk, a PDF's XMP dictionary, or a
font's name table shipped undetected (the sibling .NET port's NuGet package icon carried exactly
this: a C2PA provenance block naming the AI vendor, in every published package, unseen by a
`grep -I`-based gate for the package's whole public life). The fix re-scans every file `grep -I`
treats as binary with `grep -a` (force text) for the same `TRACE_PATTERN` / `SECRETS_PATTERN`,
filtered through the same `.publishallow`. This test builds real PNGs byte-for-byte with `zlib` and
`struct` (no Pillow) -- one with a gated word in an `iTXt` chunk, one clean -- and runs the actual
extracted script snippets against them.
"""

from __future__ import annotations

import re
import struct
import subprocess
import zlib
from pathlib import Path

import pytest


def _repo_root() -> Path:
    """The workspace root, found by walking up rather than by counting directories.

    mutmut runs this suite from a `packages/narrativetrace/mutants/` copy, one level deeper than
    the source tree, so a fixed `parents[N]` would resolve wrong there and fail collection for the
    whole mutation run.
    """
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


REPO_ROOT = _repo_root()
SCRIPT = REPO_ROOT / "scripts" / "publish-public.sh"
# `scripts/publish-public.sh` is itself private machinery (.publishignore strips it): the
# `--verify` step of a real publish run builds and tests the STAGED (published) snapshot standalone,
# where this file legitimately does not exist. Skip the whole module there rather than failing
# collection -- there is nothing to regression-test against a script that was never shipped.
if not SCRIPT.is_file():
    pytest.skip(
        f"{SCRIPT} not present (private publish machinery, stripped from this snapshot)",
        allow_module_level=True,
    )
SCRIPT_TEXT = SCRIPT.read_text(encoding="utf-8")


def _extract(pattern: str) -> str:
    match = re.search(pattern, SCRIPT_TEXT, re.DOTALL | re.MULTILINE)
    assert match, f"pattern not found in {SCRIPT}: {pattern!r}"
    return match.group(0)


TRACE_PATTERN_LINE = _extract(r"^TRACE_PATTERN='[^']*'$")
SECRETS_PATTERN_LINE = _extract(r'^SECRETS_PATTERN="[^\n]*"$')
# The two-line `name_hits=` assignment: from its opening `$(cd "$STAGE"` through the first
# `|| true)"` that closes it (the fallback-empty-string idiom every gate in this script shares).
NAME_HITS_SNIPPET = _extract(r'name_hits="\$\(cd "\$STAGE".*?\|\| true\)"')
# The binary-asset discovery block: computes $binary_staged_files by set difference (every staged
# file minus the ones `grep -I` is willing to treat as text) and defines `scan_binary_assets_for()`,
# which the trace and secrets gates both call. From its opening `all_staged_files=` assignment
# through the function's closing `}`.
BINARY_SCAN_SNIPPET = _extract(r'all_staged_files="\$\(cd "\$STAGE".*?\n\}')
# The trace gate's binary re-scan: `binary_trace_hits=` through its `.publishallow` filter.
BINARY_TRACE_HITS_SNIPPET = _extract(
    r'binary_trace_hits="\$\(scan_binary_assets_for.*?\|\| true\)"'
)
# The secrets gate's binary re-scan: same shape, `$SECRETS_PATTERN` instead.
BINARY_SECRET_HITS_SNIPPET = _extract(
    r'binary_secret_hits="\$\(scan_binary_assets_for.*?\|\| true\)"'
)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))


def _minimal_png(itxt_text: str | None = None) -> bytes:
    """A real, valid 1x1 grayscale PNG, built byte-for-byte -- no Pillow.

    With `itxt_text` given, carries it in an `iTXt` metadata chunk (the same chunk type a real
    image editor or a provenance stamp -- e.g. C2PA -- would use), the way the family finding's
    NuGet package icon carried its embedded vendor-naming block.
    """
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)  # 1x1, 8-bit, grayscale
    chunks = [_png_chunk(b"IHDR", ihdr)]
    raw_scanline = bytes([0, 0])  # filter-type byte + one gray pixel
    chunks.append(_png_chunk(b"IDAT", zlib.compress(raw_scanline)))
    if itxt_text is not None:
        keyword = b"Comment"
        itxt_data = (
            keyword + b"\x00" + bytes([0, 0]) + b"\x00" + b"\x00" + itxt_text.encode("utf-8")
        )
        chunks.append(_png_chunk(b"iTXt", itxt_data))
    chunks.append(_png_chunk(b"IEND", b""))
    return signature + b"".join(chunks)


def _run_name_hits(tmp_path: Path, allow_contents: str) -> str:
    """Run the real script's `name_hits=` computation against a synthetic staged tree."""
    stage = tmp_path / "stage"
    (stage / ".claude" / "skills").mkdir(parents=True)
    (stage / ".claude" / "skills" / "add.md").write_text("hi", encoding="utf-8")
    (stage / "plain.md").write_text("hi", encoding="utf-8")

    allow = tmp_path / ".publishallow"
    allow.write_text(allow_contents, encoding="utf-8")

    script = "\n".join(
        [
            "set -euo pipefail",
            f'STAGE="{stage}"',
            f'allow="{allow}"',
            TRACE_PATTERN_LINE,
            NAME_HITS_SNIPPET,
            'printf "%s" "$name_hits"',
        ]
    )
    result = subprocess.run(  # nosec B603, B607 # fixed argv (bash -c + this test's own script
        # string built above from repo-local literals and the real script's extracted snippet),
        # no shell metacharacter expansion beyond bash -c itself, no untrusted input
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    return result.stdout


class TestNameHitsAllowlistFiltering:
    def test_an_unreviewed_ai_tool_named_path_is_still_caught(self, tmp_path: Path) -> None:
        hits = _run_name_hits(tmp_path, allow_contents="")

        assert "./.claude" in hits

    def test_a_reviewed_publishallow_entry_clears_the_same_path(self, tmp_path: Path) -> None:
        hits = _run_name_hits(tmp_path, allow_contents=r"^\./\.claude(/.*)?$" + "\n")

        assert "./.claude" not in hits

    def test_an_unrelated_plain_file_never_hits_regardless_of_the_allowlist(
        self, tmp_path: Path
    ) -> None:
        hits = _run_name_hits(tmp_path, allow_contents="")

        assert "plain.md" not in hits

    def test_the_allowlist_does_not_blanket_clear_every_name_hit(self, tmp_path: Path) -> None:
        # A reviewed entry for one path must not silently launder an unrelated hit -- the fixture
        # tree carries only the one AI-tool-named path, so this is really the same assertion as
        # the "still caught" test above with an unrelated allow entry present, proving the filter
        # is a real regex match, not `[ -s "$allow" ]` alone short-circuiting the whole gate.
        hits = _run_name_hits(tmp_path, allow_contents=r"^\./nonexistent$" + "\n")

        assert "./.claude" in hits


def _run_binary_hits(tmp_path: Path, hits_snippet: str, allow_contents: str = "") -> str:
    """Run the real script's binary-asset discovery + one gate's `binary_*_hits=` computation.

    Stages a planted PNG (`planted.png`, `iTXt` chunk carrying "claude") next to a clean PNG
    (`clean.png`) and an ordinary text file (`plain.md`, contains "claude" too, to prove the
    binary path is genuinely additive to the existing text-content gate rather than a replacement
    for it -- the text gate would already catch `plain.md` on its own, so this fixture puts the
    same word in both a text file and a binary one and only asserts on the binary side).
    """
    stage = tmp_path / "stage"
    stage.mkdir(parents=True)
    (stage / "planted.png").write_bytes(_minimal_png(itxt_text="rendered by claude"))
    (stage / "clean.png").write_bytes(_minimal_png(itxt_text=None))
    (stage / "plain.md").write_text("claude", encoding="utf-8")

    allow = tmp_path / ".publishallow"
    allow.write_text(allow_contents, encoding="utf-8")

    var_name = hits_snippet.split("=", 1)[0]
    script = "\n".join(
        [
            "set -euo pipefail",
            f'STAGE="{stage}"',
            f'allow="{allow}"',
            TRACE_PATTERN_LINE,
            SECRETS_PATTERN_LINE,
            BINARY_SCAN_SNIPPET,
            hits_snippet,
            f'printf "%s" "${var_name}"',
        ]
    )
    result = subprocess.run(  # nosec B603, B607 # fixed argv (bash -c + this test's own script
        # string built above from repo-local literals and the real script's extracted snippets),
        # no shell metacharacter expansion beyond bash -c itself, no untrusted input
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    return result.stdout


class TestBinaryAssetScan:
    def test_a_gated_word_in_a_png_itxt_chunk_is_caught(self, tmp_path: Path) -> None:
        hits = _run_binary_hits(tmp_path, BINARY_TRACE_HITS_SNIPPET)

        assert "planted.png" in hits

    def test_a_clean_png_passes(self, tmp_path: Path) -> None:
        hits = _run_binary_hits(tmp_path, BINARY_TRACE_HITS_SNIPPET)

        assert "clean.png" not in hits

    def test_the_text_file_is_left_to_the_existing_content_gate_not_this_one(
        self, tmp_path: Path
    ) -> None:
        # plain.md is real TEXT (grep -I treats it as such), so it is outside $binary_staged_files
        # entirely -- this proves the binary scan is additive, not a wholesale replacement that
        # would double-report (or worse, mis-report) an ordinary text hit.
        hits = _run_binary_hits(tmp_path, BINARY_TRACE_HITS_SNIPPET)

        assert "plain.md" not in hits

    def test_a_reviewed_publishallow_entry_clears_the_planted_png(self, tmp_path: Path) -> None:
        hits = _run_binary_hits(
            tmp_path, BINARY_TRACE_HITS_SNIPPET, allow_contents=r"^\./planted\.png$" + "\n"
        )

        assert "planted.png" not in hits

    def test_the_allowlist_does_not_blanket_clear_every_binary_hit(self, tmp_path: Path) -> None:
        hits = _run_binary_hits(
            tmp_path, BINARY_TRACE_HITS_SNIPPET, allow_contents=r"^\./nonexistent$" + "\n"
        )

        assert "planted.png" in hits

    def test_the_secrets_gate_binary_scan_catches_the_same_planted_identity_marker(
        self, tmp_path: Path
    ) -> None:
        # Reuses the same fixture but swaps in "claude" for an identity marker the
        # SECRETS_PATTERN actually gates on, proving the secrets gate's own binary re-scan
        # (independent code path from the trace gate's) is wired up too.
        stage = tmp_path / "stage"
        stage.mkdir(parents=True)
        (stage / "planted.png").write_bytes(_minimal_png(itxt_text="built by danijel"))
        (stage / "clean.png").write_bytes(_minimal_png(itxt_text=None))
        allow = tmp_path / ".publishallow"
        allow.write_text("", encoding="utf-8")

        script = "\n".join(
            [
                "set -euo pipefail",
                f'STAGE="{stage}"',
                f'allow="{allow}"',
                TRACE_PATTERN_LINE,
                SECRETS_PATTERN_LINE,
                BINARY_SCAN_SNIPPET,
                BINARY_SECRET_HITS_SNIPPET,
                'printf "%s" "$binary_secret_hits"',
            ]
        )
        result = subprocess.run(  # nosec B603, B607 # fixed argv, no shell metacharacter
            # expansion beyond bash -c itself, no untrusted input
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=True,
            cwd=tmp_path,
        )

        assert "planted.png" in result.stdout
        assert "clean.png" not in result.stdout
