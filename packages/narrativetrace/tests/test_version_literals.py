# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The version-literal lint (`scripts/version_literals.py`).

`check` is wired into `poe check` through `scripts/snippet_check.py` and `sync` into
`poe snippet-sync`, the same split the docs-as-tests gate already draws between the reader and
the only writer — so these tests drive the two functions directly against synthetic `tmp_path`
trees, exactly as `test_snippet_check.py` does for the blocks they sit beside.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts.translation_check import REPO_ROOT, git_blob_hash
from scripts.version_literals import check, governed_files, read_version, sync


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestMarkers:
    def test_a_since_marker_on_a_documentation_page_is_reported(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "documentation/guide.md", "# Guide\n\nThe run has a name *(since 1.2.3)*.\n"
        )

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("documentation/guide.md:3:")
        assert "*(since" in problem

    def test_a_marker_hard_wrapped_after_since_is_still_caught(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/guide.md", "# Guide\n\nIt does *(since\n1.2.3)* this.\n")

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("documentation/guide.md:3:")

    def test_a_marker_hard_wrapped_after_the_version_comma_is_still_caught(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path,
            "documentation/guide.md",
            "# Guide\n\nIt does *(since 1.2.3,\nunreleased)* this.\n",
        )

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("documentation/guide.md:3:")

    def test_a_marker_in_a_heading_is_caught_the_same_as_one_in_the_body(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path, "documentation/guide.md", "# Guide\n\n## The run has a name *(since 1.2.3)*\n"
        )

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("documentation/guide.md:3:")

    def test_a_page_with_no_version_talk_reports_nothing(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/guide.md", "# Guide\n\nThe run has a name.\n")

        assert check(tmp_path, "1.2.3") == []


class TestBanner:
    def test_an_in_sync_docs_vs_published_banner_is_reported(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "documentation/guide.md",
            "# Guide\n\n*(Docs and published both at 1.2.3.)*\n",
        )

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("documentation/guide.md:3:")
        assert "docs-vs-published banner" in problem

    def test_a_divergent_docs_vs_published_banner_is_reported(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "documentation/guide.md",
            "# Guide\n\n*(These docs describe 1.2.3; published is 1.2.2.)*\n",
        )

        (problem,) = check(tmp_path, "1.2.3")

        assert "docs-vs-published banner" in problem

    def test_the_published_version_cache_comment_is_reported(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "documentation/guide.md",
            "# Guide\n\nSomething. <!-- registry checked 12m ago -->\n",
        )

        (problem,) = check(tmp_path, "1.2.3")

        assert "published-version cache" in problem


class TestCoordinates:
    @pytest.mark.parametrize(
        "coordinate",
        [
            "uv add narrativetrace==9.9.9",
            "pip install narrativetrace[structlog]==9.9.9",
            'dependencies = ["narrativetrace>=9.9.9"]',
            "uv run --with narrativetrace-pytest==9.9.9 pytest",
            'requires = ["narrativetrace-clarity~=9.9.9"]',
        ],
    )
    def test_a_coordinate_pinned_elsewhere_than_the_version_source_is_reported(
        self, tmp_path: Path, coordinate: str
    ) -> None:
        _write(tmp_path, "documentation/guide.md", f"# Guide\n\n`{coordinate}`\n")

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("documentation/guide.md:3:")
        assert "9.9.9" in problem

    @pytest.mark.parametrize(
        "coordinate",
        [
            "uv add narrativetrace==1.2.3",
            "pip install narrativetrace[structlog]==1.2.3",
            'dependencies = ["narrativetrace>=1.2.3"]',
            "uv run --with narrativetrace-pytest==1.2.3 pytest",
            'requires = ["narrativetrace-clarity~=1.2.3"]',
        ],
    )
    def test_a_coordinate_at_the_version_source_passes(
        self, tmp_path: Path, coordinate: str
    ) -> None:
        _write(tmp_path, "documentation/guide.md", f"# Guide\n\n`{coordinate}`\n")

        assert check(tmp_path, "1.2.3") == []

    def test_an_unpinned_coordinate_is_not_a_version_literal_at_all(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/guide.md", "# Guide\n\n`uv add narrativetrace`\n")

        assert check(tmp_path, "1.2.3") == []

    def test_a_third_party_coordinate_is_not_this_lint_s_business(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "documentation/guide.md",
            "# Guide\n\n`uv add structlog==25.1.0` and `pytest>=8.0.0`.\n",
        )

        assert check(tmp_path, "1.2.3") == []

    def test_a_third_party_version_literal_in_prose_passes(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "documentation/guide.md",
            "# Guide\n\nlogback 1.5.15 fixed it in 1.5.38; Python 3.12.1 is the floor.\n",
        )

        assert check(tmp_path, "1.2.3") == []

    def test_the_near_miss_distribution_name_is_somebody_else_s_package(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "documentation/guide.md", "# Guide\n\n`uv add narrativetracex==9.9.9`\n")

        assert check(tmp_path, "1.2.3") == []


_MIRROR_HEADER = (
    "<!-- source: README.md blob 0123456789ab | translated: 2026-09-25 | reviewed: - -->"
)


class TestScope:
    def test_the_root_readme_is_governed(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.md", "# Title\n\nIt does *(since 1.2.3)* this.\n")

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("README.md:3:")

    def test_a_root_readme_mirror_is_governed(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.md", "# Title\n")
        _write(
            tmp_path, "LEAME.md", f"{_MIRROR_HEADER}\n# Título\n\n`uv add narrativetrace==9.9.9`\n"
        )

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("LEAME.md:4:")

    def test_a_root_page_that_is_neither_the_readme_nor_its_mirror_is_not_governed(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "CHANGELOG.md", "# Releases\n\nIt does *(since 1.2.3)* this.\n")

        assert check(tmp_path, "1.2.3") == []

    def test_llms_txt_is_governed_even_though_it_is_not_markdown(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "documentation/llms.txt", "# Index\n\n*(Docs and published both at 1.2.3.)*\n"
        )

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("documentation/llms.txt:3:")

    def test_a_translated_guide_is_governed_too(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/es/guia.md", "# Guía\n\nLo hace *(since 1.2.3)*.\n")

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("documentation/es/guia.md:3:")

    def test_a_shipped_package_readme_is_governed(self, tmp_path: Path) -> None:
        _write(
            tmp_path, "packages/narrativetrace-pytest/README.md", "# Plugin\n\n*(since 1.2.3)*\n"
        )

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("packages/narrativetrace-pytest/README.md:3:")

    def test_a_package_source_file_is_not_a_public_document(self, tmp_path: Path) -> None:
        _write(tmp_path, "packages/narrativetrace/src/thing.py", '"""*(since 1.2.3)*"""\n')

        assert check(tmp_path, "1.2.3") == []

    def test_a_repository_with_no_documentation_directory_reports_nothing(
        self, tmp_path: Path
    ) -> None:
        assert check(tmp_path, "1.2.3") == []

    def test_a_file_without_a_trailing_newline_is_read_to_its_last_line(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "documentation/guide.md", "# Guide\n\nIt does *(since 1.2.3)* this.")

        (problem,) = check(tmp_path, "1.2.3")

        assert problem.startswith("documentation/guide.md:3:")


class TestSync:
    def test_a_stale_coordinate_is_rewritten_to_the_version_source(self, tmp_path: Path) -> None:
        page = _write(
            tmp_path, "documentation/guide.md", "# Guide\n\n`uv add narrativetrace==9.9.9`\n"
        )

        (change,) = sync(tmp_path, "1.2.3")

        assert page.read_text(encoding="utf-8") == "# Guide\n\n`uv add narrativetrace==1.2.3`\n"
        assert change.startswith("documentation/guide.md:")

    @pytest.mark.parametrize(
        ("before", "after"),
        [
            ("uv add narrativetrace==9.9.9", "uv add narrativetrace==1.2.3"),
            (
                "pip install narrativetrace[structlog]==9.9.9",
                "pip install narrativetrace[structlog]==1.2.3",
            ),
            ('"narrativetrace>=9.9.9"', '"narrativetrace>=1.2.3"'),
            ("--with narrativetrace-pytest==9.9.9", "--with narrativetrace-pytest==1.2.3"),
            ('"narrativetrace-clarity~=9.9.9"', '"narrativetrace-clarity~=1.2.3"'),
        ],
    )
    def test_every_coordinate_form_the_docs_use_is_rewritten(
        self, tmp_path: Path, before: str, after: str
    ) -> None:
        page = _write(tmp_path, "documentation/guide.md", f"# Guide\n\n`{before}`\n")

        sync(tmp_path, "1.2.3")

        assert page.read_text(encoding="utf-8") == f"# Guide\n\n`{after}`\n"

    def test_a_third_party_coordinate_is_left_exactly_as_it_is(self, tmp_path: Path) -> None:
        text = "# Guide\n\n`uv add structlog==25.1.0` and `narrativetracex==9.9.9`.\n"
        page = _write(tmp_path, "documentation/guide.md", text)

        assert sync(tmp_path, "1.2.3") == []
        assert page.read_text(encoding="utf-8") == text

    def test_a_translated_mirror_carries_the_same_language_neutral_coordinate(
        self, tmp_path: Path
    ) -> None:
        mirror = _write(
            tmp_path,
            "documentation/es/guia.md",
            "# Guía\n\n`uv add narrativetrace==9.9.9`\n",
        )

        sync(tmp_path, "1.2.3")

        assert "narrativetrace==1.2.3" in mirror.read_text(encoding="utf-8")

    def test_syncing_twice_changes_nothing_the_second_time(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/guide.md", "# Guide\n\n`uv add narrativetrace==9.9.9`\n")

        assert sync(tmp_path, "1.2.3") != []
        assert sync(tmp_path, "1.2.3") == []

    def test_a_synced_repository_passes_its_own_check(self, tmp_path: Path) -> None:
        _write(tmp_path, "documentation/guide.md", "# Guide\n\n`uv add narrativetrace==9.9.9`\n")

        sync(tmp_path, "4.5.6")

        assert check(tmp_path, "4.5.6") == []

    def test_a_file_without_a_trailing_newline_keeps_not_having_one(self, tmp_path: Path) -> None:
        page = _write(tmp_path, "documentation/guide.md", "# Guide\n\n`narrativetrace==9.9.9`")

        sync(tmp_path, "1.2.3")

        assert page.read_text(encoding="utf-8") == "# Guide\n\n`narrativetrace==1.2.3`"

    def test_the_mirror_of_a_rewritten_english_page_is_restamped(self, tmp_path: Path) -> None:
        source = _write(tmp_path, "README.md", "# Title\n\n`uv add narrativetrace==9.9.9`\n")
        mirror = _write(tmp_path, "LEAME.md", f"{_MIRROR_HEADER}\n# Título\n")

        sync(tmp_path, "1.2.3")

        fresh = git_blob_hash(source.read_bytes())[:12]
        assert mirror.read_text(encoding="utf-8").startswith(
            f"<!-- source: README.md blob {fresh} |"
        )

    def test_the_mirror_of_an_untouched_english_page_keeps_its_stamp(self, tmp_path: Path) -> None:
        _write(tmp_path, "README.md", "# Title\n")
        mirror = _write(tmp_path, "LEAME.md", f"{_MIRROR_HEADER}\n# Título\n")

        sync(tmp_path, "1.2.3")

        assert mirror.read_text(encoding="utf-8").startswith(_MIRROR_HEADER)


class TestVersionSource:
    def test_the_version_source_is_the_root_pyproject_s_own_version(self, tmp_path: Path) -> None:
        _write(tmp_path, "pyproject.toml", '[project]\nname = "x"\nversion = "1.2.3"\n')

        assert read_version(tmp_path) == "1.2.3"

    def test_a_pyproject_without_a_version_is_an_authoring_bug_not_a_degrade(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "pyproject.toml", '[project]\nname = "x"\n')

        with pytest.raises(ValueError, match=r"\Apyproject.toml: no top-level 'version"):
            read_version(tmp_path)

    def test_a_dependency_s_own_version_pin_is_not_mistaken_for_the_source(
        self, tmp_path: Path
    ) -> None:
        _write(
            tmp_path,
            "pyproject.toml",
            '[project]\nname = "x"\nversion = "1.2.3"\n\n[tool.other]\nversion = "9.9.9"\n',
        )

        assert read_version(tmp_path) == "1.2.3"


class TestRealRepository:
    """The gate against this repository's own tracked pages, the same shape
    `test_snippet_check.py::TestRealRepository` already runs beside it: the rule is only worth
    having if it is true of the tree that ships."""

    def test_no_public_document_talks_about_a_narrativetrace_version(self) -> None:
        assert check(REPO_ROOT, read_version(REPO_ROOT)) == []

    def test_the_version_source_is_the_one_the_publish_script_reads(self) -> None:
        """`read_version`'s docstring promises parity with `scripts/publish-public.sh`'s own
        `detect_version`, which stamps the version into the published LICENSE. The two are written
        in different languages, so the only way to hold them together is to run the shell one --
        lifted out of the script itself, never retyped here -- and compare.

        The script is stripped from the public snapshot (`.publishignore`), and the publish
        script's own `--verify` runs this suite against that snapshot: there the parity has no
        second half to compare, so the test skips rather than fails -- the private tree, where
        both halves live, is the one that holds them together."""
        script_path = REPO_ROOT / "scripts" / "publish-public.sh"
        if not script_path.is_file():
            pytest.skip("scripts/publish-public.sh is stripped from the public snapshot")
        script = script_path.read_text(encoding="utf-8")
        body = script.split("detect_version() {", 1)[1].split("}", 1)[0].strip()

        detected = subprocess.run(  # nosec B603, B607 - `body` is this repository's own tracked
            # shell function, read from the script under test; nothing here is external input.
            ["sh", "-c", body],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        assert read_version(REPO_ROOT) == detected

    def test_asking_the_real_repository_leaves_every_governed_page_byte_identical(
        self, tmp_path: Path
    ) -> None:
        before = {path: path.read_bytes() for path in governed_files(REPO_ROOT)}

        check(REPO_ROOT, read_version(REPO_ROOT))

        assert {path: path.read_bytes() for path in governed_files(REPO_ROOT)} == before
