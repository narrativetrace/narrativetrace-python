# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The docs-vs-published banner in `documentation/llms.txt` (`scripts/llms_banner.py`, family
design note: `docs-vs-published-gate-2026-09-12.md`, part (a)).

`sync_banner`'s real PyPI lookup is exercised for real by `poe snippet-sync` (see that tool's own
report); these tests drive `render_banner`, `get_published_version`'s cache/TTL logic, and
`sync_banner`/`check_banner` against synthetic `tmp_path` trees with an injected fake fetcher and
clock — the same split `test_verify_publication_registry.py` and `test_snippet_check.py` use.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.llms_banner import (
    CACHE_RELATIVE,
    check_banner,
    compute_banner_line,
    get_published_version,
    read_repo_version,
    render_banner,
    sync_banner,
)

_LLMS_TXT = """# some-runtime

> A tagline.

## Section

body
"""


def _write_repo(root: Path, *, version: str = "0.1.1", llms_txt: str = _LLMS_TXT) -> Path:
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "some-runtime-workspace"\nversion = "{version}"\n', encoding="utf-8"
    )
    docs = root / "documentation"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "llms.txt").write_text(llms_txt, encoding="utf-8")
    return root


def _write_cache(
    root: Path, *, version: str, timestamp: float, package: str = "narrativetrace"
) -> None:
    cache_path = root / CACHE_RELATIVE
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"package": package, "version": version, "timestamp": timestamp}),
        encoding="utf-8",
    )


class TestReadRepoVersion:
    def test_reads_the_top_level_version(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, version="1.2.3")
        assert read_repo_version(tmp_path) == "1.2.3"


class TestRenderBanner:
    def test_equal_versions(self) -> None:
        assert render_banner("0.1.1", "0.1.1", None) == "*(Docs and published both at 0.1.1.)*"

    def test_differing_versions(self) -> None:
        assert (
            render_banner("0.1.2", "0.1.1", None)
            == "*(These docs describe 0.1.2; published is 0.1.1.)*"
        )

    def test_offline_never_guesses(self) -> None:
        assert (
            render_banner("0.1.2", None, None)
            == "*(These docs describe 0.1.2; published: unknown offline.)*"
        )

    def test_a_cached_hit_shows_its_own_age_never_silently_as_fresh(self) -> None:
        line = render_banner("0.1.1", "0.1.1", 125.0)
        assert line.startswith("*(Docs and published both at 0.1.1.)*")
        assert "<!-- registry checked" in line

    def test_a_fresh_live_lookup_carries_no_age_comment(self) -> None:
        assert render_banner("0.1.1", "0.1.1", 0.0) == "*(Docs and published both at 0.1.1.)*"


class TestGetPublishedVersion:
    def test_fresh_cache_is_used_without_calling_fetch(self, tmp_path: Path) -> None:
        _write_repo(tmp_path)
        _write_cache(tmp_path, version="0.1.1", timestamp=1_000.0)

        def fail_fetch(name: str) -> str | None:
            raise AssertionError("must not be called when the cache is fresh")

        version, age = get_published_version(tmp_path, now=1_100.0, fetch=fail_fetch)
        assert version == "0.1.1"
        assert age == 100.0

    def test_stale_past_ttl_cache_is_never_handed_back_as_current(self, tmp_path: Path) -> None:
        _write_repo(tmp_path)
        _write_cache(tmp_path, version="9.9.9", timestamp=1_000.0)

        version, age = get_published_version(
            tmp_path, now=1_000.0 + 3601.0, fetch=lambda name: None, ttl_seconds=3600.0
        )
        assert (version, age) == (None, None)

    def test_a_successful_live_fetch_is_cached_for_next_time(self, tmp_path: Path) -> None:
        _write_repo(tmp_path)
        version, age = get_published_version(tmp_path, now=1_000.0, fetch=lambda name: "0.1.1")
        assert (version, age) == ("0.1.1", 0.0)
        cached = json.loads((tmp_path / CACHE_RELATIVE).read_text(encoding="utf-8"))
        assert cached == {"package": "narrativetrace", "version": "0.1.1", "timestamp": 1_000.0}

    def test_offline_is_never_a_guess(self, tmp_path: Path) -> None:
        _write_repo(tmp_path)
        version, age = get_published_version(tmp_path, now=1_000.0, fetch=lambda name: None)
        assert (version, age) == (None, None)

    def test_check_banner_path_never_calls_fetch(self, tmp_path: Path) -> None:
        _write_repo(tmp_path)

        def fail_fetch(name: str) -> str | None:
            raise AssertionError("check_banner must never touch the network")

        version, age = get_published_version(
            tmp_path, now=1_000.0, fetch=fail_fetch, allow_network=False
        )
        assert (version, age) == (None, None)


class TestComputeBannerLine:
    def test_reflects_the_repo_version_and_a_fresh_cache(self, tmp_path: Path) -> None:
        _write_repo(tmp_path, version="0.1.2")
        _write_cache(tmp_path, version="0.1.1", timestamp=1.0)
        line = compute_banner_line(tmp_path, allow_network=False, now=50.0)
        assert line.startswith("*(These docs describe 0.1.2; published is 0.1.1.)*")


class TestSyncBanner:
    def test_inserts_a_banner_right_after_the_h1(self, tmp_path: Path) -> None:
        _write_repo(tmp_path)
        changed = sync_banner(tmp_path)
        assert changed is not None
        lines = (tmp_path / "documentation/llms.txt").read_text(encoding="utf-8").split("\n")
        assert lines[0] == "# some-runtime"
        assert lines[1] == ""
        assert lines[2].startswith("*(")

    def test_rewrites_an_existing_stale_banner_in_place(self, tmp_path: Path) -> None:
        stale = _LLMS_TXT.replace(
            "# some-runtime\n\n", "# some-runtime\n\n*(Docs and published both at 0.1.0.)*\n\n"
        )
        _write_repo(tmp_path, version="0.1.1", llms_txt=stale)
        _write_cache(tmp_path, version="0.1.1", timestamp=1.0)
        changed = sync_banner(tmp_path)
        assert changed is not None
        assert "0.1.0" not in changed
        text = (tmp_path / "documentation/llms.txt").read_text(encoding="utf-8")
        assert "Docs and published both at 0.1.1" in text

    def test_a_second_run_with_nothing_changed_is_a_no_op(self, tmp_path: Path) -> None:
        _write_repo(tmp_path)
        _write_cache(tmp_path, version="0.1.1", timestamp=1.0)
        sync_banner(tmp_path)
        assert sync_banner(tmp_path) is None

    def test_missing_llms_txt_is_a_no_op(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        assert sync_banner(tmp_path) is None


class TestCheckBanner:
    def test_missing_banner_fails(self, tmp_path: Path) -> None:
        _write_repo(tmp_path)
        failures = check_banner(tmp_path)
        assert len(failures) == 1
        assert "missing the docs-vs-published banner" in failures[0]

    def test_matching_repo_version_with_no_cache_passes(self, tmp_path: Path) -> None:
        _write_repo(tmp_path)
        sync_banner_result = sync_banner(tmp_path)
        assert sync_banner_result is not None
        assert check_banner(tmp_path) == []

    def test_stale_repo_version_token_fails_with_no_network_needed(self, tmp_path: Path) -> None:
        with_banner = _LLMS_TXT.replace(
            "# some-runtime\n\n", "# some-runtime\n\n*(Docs and published both at 0.1.0.)*\n\n"
        )
        _write_repo(tmp_path, version="0.1.1", llms_txt=with_banner)
        failures = check_banner(tmp_path)
        assert len(failures) == 1
        assert "0.1.0" in failures[0]
        assert "0.1.1" in failures[0]

    def test_offline_with_no_cache_is_not_a_failure(self, tmp_path: Path) -> None:
        # A banner whose repo-version token matches, but whose published half nobody can verify
        # right now (no cache on disk) must not fail the per-commit gate — see module docstring.
        with_banner = _LLMS_TXT.replace(
            "# some-runtime\n\n",
            "# some-runtime\n\n*(These docs describe 0.1.1; published: unknown offline.)*\n\n",
        )
        _write_repo(tmp_path, version="0.1.1", llms_txt=with_banner)
        assert check_banner(tmp_path) == []

    def test_a_fresh_cache_catches_a_stale_published_half_too(self, tmp_path: Path) -> None:
        with_banner = _LLMS_TXT.replace(
            "# some-runtime\n\n", "# some-runtime\n\n*(Docs and published both at 0.1.1.)*\n\n"
        )
        _write_repo(tmp_path, version="0.1.1", llms_txt=with_banner)
        _write_cache(tmp_path, version="0.1.0", timestamp=__import__("time").time())
        failures = check_banner(tmp_path)
        assert len(failures) == 1
        assert "stale" in failures[0]

    def test_missing_llms_txt_has_no_failures(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "x"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        assert check_banner(tmp_path) == []
