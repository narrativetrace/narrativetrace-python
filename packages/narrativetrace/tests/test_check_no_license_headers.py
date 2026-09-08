# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The license-header absence gate (`poe check`, `scripts/check_no_license_headers.py`).

`main()`'s git/filesystem glue is exercised for real by `poe check` itself running the script
against this repository; these tests cover `carries_a_header_block`'s pattern-matching in
isolation (including the exact false-positive `test_distribution_licensing.py` must not trip),
`find_offenders`'s all-or-nothing policy (a uniformly header-stamped tree -- what
the (private) publish pipeline's --verify build produces -- is a pass, not a finding; only a MIX is
an offender), and `_walk_python_files`'s scope (the fallback used outside a git checkout, e.g.
that same --verify build, which runs from a plain tar-extracted copy with no .git at all).
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_no_license_headers import (
    HEADER_SCAN_LINES,
    _walk_python_files,
    carries_a_header_block,
    find_offenders,
    tracked_python_files,
)

_HEADER = "# SPDX-License-Identifier: BUSL-1.1\n"
_PLAIN = '"""A module."""\n\ndef f() -> None:\n    pass\n'


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return Path(name)


class TestCarriesAHeaderBlock:
    def test_plain_module_has_no_header(self, tmp_path: Path) -> None:
        rel = _write(tmp_path, "plain.py", '"""A module."""\n\ndef f() -> None:\n    pass\n')
        assert carries_a_header_block(rel, tmp_path) is False

    def test_spdx_line_at_the_top_is_a_header(self, tmp_path: Path) -> None:
        rel = _write(
            tmp_path, "stamped.py", "# SPDX-License-Identifier: BUSL-1.1\n\ndef f() -> None:\n"
        )
        assert carries_a_header_block(rel, tmp_path) is True

    def test_copyright_line_at_the_top_is_a_header(self, tmp_path: Path) -> None:
        rel = _write(tmp_path, "stamped.py", "# Copyright 2026 Empower Agile\n\ndef f() -> None:\n")
        assert carries_a_header_block(rel, tmp_path) is True

    def test_business_source_license_phrase_is_a_header(self, tmp_path: Path) -> None:
        rel = _write(
            tmp_path,
            "stamped.py",
            "# Licensed under the Business Source License 1.1 (see LICENSE)\n",
        )
        assert carries_a_header_block(rel, tmp_path) is True

    def test_a_string_mention_past_the_scan_window_is_not_a_header(self, tmp_path: Path) -> None:
        padding = "\n".join(f"# line {n}" for n in range(HEADER_SCAN_LINES + 2))
        rel = _write(
            tmp_path, "mentions_it.py", f'{padding}\n\n"""Asserts license == "BUSL-1.1"."""\n'
        )
        assert carries_a_header_block(rel, tmp_path) is False

    def test_a_docstring_mentioning_the_license_near_the_top_is_not_a_header(
        self, tmp_path: Path
    ) -> None:
        # The real regression: test_distribution_licensing.py's own module docstring discusses
        # licensing without ever writing an SPDX/Apache/BSL header phrase.
        rel = _write(
            tmp_path,
            "licensing_test.py",
            '"""Wheels must carry the licence text: license = "BUSL-1.1" only stamps the '
            'expression.\n\nlicense-files = ["LICENSE"] and License-Expression: BUSL-1.1 are '
            'asserted below."""\n',
        )
        assert carries_a_header_block(rel, tmp_path) is False


def _make_fake_repo(tmp_path: Path, *, git: bool) -> Path:
    """A minimal repo shape: packages/<pkg>/src/one.py, scripts/two.py, root three.py. No
    ``.git`` unless ``git`` asks for one -- the marker `tracked_python_files` branches on."""
    (tmp_path / "packages" / "pkg" / "src").mkdir(parents=True)
    (tmp_path / "packages" / "pkg" / "src" / "one.py").write_text(_PLAIN, encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "two.py").write_text(_PLAIN, encoding="utf-8")
    (tmp_path / "three.py").write_text(_PLAIN, encoding="utf-8")
    if git:
        (tmp_path / ".git").mkdir()
    return tmp_path


class TestFindOffenders:
    """`--verify` runs `poe check` -- this gate included -- against a snapshot every tracked
    `.py` file was just stamped in: 100% coverage there is the intended post-stamp state, not
    a finding. Only a MIX (this gate's real purpose: a header pasted in by mistake) offends."""

    def test_no_file_stamped_is_not_an_offense(self, tmp_path: Path) -> None:
        repo = _make_fake_repo(tmp_path, git=False)
        assert find_offenders(repo) == []

    def test_every_file_stamped_is_not_an_offense(self, tmp_path: Path) -> None:
        repo = _make_fake_repo(tmp_path, git=False)
        for path in _walk_python_files(repo):
            (repo / path).write_text(_HEADER + _PLAIN, encoding="utf-8")
        assert find_offenders(repo) == []

    def test_one_stamped_file_among_unstamped_siblings_is_the_offense(self, tmp_path: Path) -> None:
        repo = _make_fake_repo(tmp_path, git=False)
        offender = repo / "scripts" / "two.py"
        offender.write_text(_HEADER + _PLAIN, encoding="utf-8")
        assert find_offenders(repo) == [Path("scripts/two.py")]

    def test_no_tracked_files_is_not_an_offense(self, tmp_path: Path) -> None:
        assert find_offenders(tmp_path) == []


class TestTrackedPythonFiles:
    """`git ls-files` can be unanswerable even when `.git` exists: ci.yml's container job runs
    against a workspace owned by a different uid, and git refuses it outright ("dubious
    ownership", exit 128) -- a containerized CI job's finding. Any git failure must
    route to the walk fallback, not crash the gate."""

    def test_a_git_dir_git_refuses_falls_back_to_the_walk(self, tmp_path: Path) -> None:
        # An empty `.git` directory is not a valid repository, so `git ls-files` genuinely
        # fails here -- same observable behavior as the container's ownership rejection.
        repo = _make_fake_repo(tmp_path, git=True)
        assert tracked_python_files(repo) == [
            Path("packages/pkg/src/one.py"),
            Path("scripts/two.py"),
            Path("three.py"),
        ]


class TestWalkPythonFiles:
    """The no-`.git` fallback (`tracked_python_files` delegates here) -- exercised directly
    against `--verify`'s own shape: a plain tar-extracted copy with no VCS metadata at all."""

    def test_finds_files_under_the_scoped_directories_and_the_repo_root(
        self, tmp_path: Path
    ) -> None:
        repo = _make_fake_repo(tmp_path, git=False)
        found = _walk_python_files(repo)
        assert found == [
            Path("packages/pkg/src/one.py"),
            Path("scripts/two.py"),
            Path("three.py"),
        ]

    def test_excludes_venv_build_and_mutants_directories(self, tmp_path: Path) -> None:
        repo = _make_fake_repo(tmp_path, git=False)
        for noise_dir in (".venv", "build", "packages/pkg/mutants", "__pycache__"):
            noisy = repo / noise_dir
            noisy.mkdir(parents=True)
            (noisy / "noise.py").write_text(_PLAIN, encoding="utf-8")
        found = _walk_python_files(repo)
        assert Path("packages/pkg/src/one.py") in found
        assert not any("noise.py" in str(path) for path in found)

    def test_ignores_directories_outside_its_scope(self, tmp_path: Path) -> None:
        repo = _make_fake_repo(tmp_path, git=False)
        outside = repo / "documentation"
        outside.mkdir()
        (outside / "outside.py").write_text(_PLAIN, encoding="utf-8")
        found = _walk_python_files(repo)
        assert not any("outside.py" in str(path) for path in found)
