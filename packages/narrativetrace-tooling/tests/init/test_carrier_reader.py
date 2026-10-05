# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The carrier is opened from the REAL checked-in payload and from the REAL built wheel — the two
things a consumer actually gets — and refused on hand-built broken ones. A fixture wheel would prove
only that the test can build a wheel; the refusals have no real counterpart, so those are built by
hand on purpose.

Named after the Java port's ``CarrierTest`` so the two lists diff. Java's local-Maven-repository
cases have no counterpart: the design ruled that Python's own caches are not stable enough to read,
so ``--from`` takes a path here and nothing resolves a coordinate.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
import zipfile
from collections.abc import Iterator
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import carriers
import pytest

from narrativetrace_tooling.init import carrier as carrier_module
from narrativetrace_tooling.init.carrier import (
    BUNDLED_ROOT,
    CARRIER_ROOT,
    CATALOGUE_FILE,
    CORE_DISTRIBUTION,
    SKILLS_DISTRIBUTION,
    Carrier,
    carrier_from_distribution,
    open_carrier,
    resolve_carrier,
)
from narrativetrace_tooling.init.catalogue import SkillEntry, SkillFlavour

REPO_ROOT = carriers.repo_root()


def _version() -> str:
    metadata: dict[str, Any] = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    return str(metadata["project"]["version"])


VERSION = _version()


@pytest.fixture
def real_carrier() -> Iterator[Carrier]:
    """The invariant is re-checked around every case that opens a real carrier: a test that reached
    past the frozen value and corrupted it should fail in the test that did it."""
    carrier = carriers.real()
    assert carrier_module._invariant(carrier), "the real carrier is incomplete before the test"
    yield carrier
    assert carrier_module._invariant(carrier), "the test left the real carrier incomplete"


class TestTheRealCarrier:
    def test_opens_the_checked_in_payload_and_stamps_it_with_what_the_directory_names(self) -> None:
        carrier = carriers.real()

        assert carrier.coordinate == "skills==unknown"
        assert len(carrier.skills) == 2

    def test_hands_out_each_flavour_body_exactly_as_the_carrier_carries_it(self) -> None:
        carrier = carriers.real()
        doctor = carrier.catalogue.skill("narrativetrace-doctor")

        assert doctor is not None
        for flavour in SkillFlavour:
            expected = (carriers.real_carrier_directory() / doctor.path_for(flavour)).read_text(
                encoding="utf-8"
            )
            assert carrier.body(doctor, flavour) == expected

    def test_opens_the_bundled_copy_and_reads_the_same_skills(self) -> None:
        bundled = open_carrier(carriers.bundled_carrier_directory())

        assert bundled.skills == carriers.real().skills

    def test_opens_a_distribution_root_as_well_as_the_carrier_root_itself(self) -> None:
        from_distribution_root = open_carrier(REPO_ROOT / "packages" / "narrativetrace-skills")
        from_carrier_root = open_carrier(carriers.real_carrier_directory())

        assert from_distribution_root.skills == from_carrier_root.skills

    def test_reads_the_version_out_of_an_unpacked_wheel_directorys_name(
        self, tmp_path: Path
    ) -> None:
        unpacked = tmp_path / "narrativetrace_skills-9.9.9"
        shutil.copytree(carriers.real_carrier_directory(), unpacked / CARRIER_ROOT)

        assert open_carrier(unpacked).coordinate == "narrativetrace-skills==9.9.9"

    def test_holds_its_invariant_once_open(self, real_carrier: Carrier) -> None:
        assert carrier_module._invariant(real_carrier) is True


@pytest.mark.distribution
class TestTheRealBuiltWheel:
    """What a consumer unpacks is a wheel, so one case opens the real archive. Marked
    ``distribution`` like every other test that shells out to ``uv build``."""

    def test_opens_the_built_carrier_wheel_and_stamps_it_with_its_own_coordinate(
        self, tmp_path: Path
    ) -> None:
        wheel = _build_carrier_wheel(tmp_path)

        carrier = open_carrier(wheel)

        assert carrier.coordinate == f"{SKILLS_DISTRIBUTION}=={VERSION}"
        assert len(carrier.skills) == 2

    def test_reads_every_page_out_of_the_wheel_byte_for_byte(self, tmp_path: Path) -> None:
        wheel = _build_carrier_wheel(tmp_path)

        carrier = open_carrier(wheel)

        for skill in carrier.skills:
            for flavour in SkillFlavour:
                with zipfile.ZipFile(wheel) as archive:
                    inside = archive.read(f"{CARRIER_ROOT}/{skill.path_for(flavour)}").decode()
                assert carrier.body(skill, flavour) == inside


class TestResolvingACarrierWithNoPathGiven:
    """The preference order: the skills distribution the PROJECT resolves, then the copy the core
    distribution bundles. Never a network call, in any branch."""

    def test_prefers_the_skills_distribution_the_project_resolves(self) -> None:
        resolved = resolve_carrier()

        assert resolved.coordinate == f"{SKILLS_DISTRIBUTION}=={VERSION}"
        assert len(resolved.skills) == 2

    def test_a_given_path_overrides_both(self, tmp_path: Path) -> None:
        carriers.fake(tmp_path, "only-this-one")

        resolved = resolve_carrier(tmp_path / "narrativetrace_skills-1.2.3")

        assert [skill.name for skill in resolved.skills] == ["only-this-one"]
        assert resolved.coordinate == carriers.FAKE_COORDINATE

    def test_reads_the_bundled_copy_out_of_the_core_distribution(self) -> None:
        bundled = carrier_from_distribution(CORE_DISTRIBUTION, BUNDLED_ROOT)

        assert bundled is not None
        assert bundled.coordinate == f"{CORE_DISTRIBUTION}=={VERSION}"
        assert bundled.skills == carriers.real().skills

    def test_reports_no_carrier_for_a_distribution_that_is_not_installed(self) -> None:
        assert carrier_from_distribution("narrativetrace-not-a-real-distribution", "x") is None

    def test_reports_no_carrier_for_an_installed_distribution_carrying_none(self) -> None:
        assert carrier_from_distribution("pytest", CARRIER_ROOT) is None

    def test_refuses_with_both_distributions_named_when_neither_carries_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(carrier_module, "carrier_from_distribution", lambda *_: None)

        with pytest.raises(ValueError, match=r"no skills carrier"):
            resolve_carrier()


class TestARefusedCarrier:
    def test_refuses_a_source_that_does_not_exist(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match=r"no carrier at .*nothing-here"):
            open_carrier(tmp_path / "nothing-here.whl")

    def test_refuses_a_directory_with_no_catalogue(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match=rf"carries no {CATALOGUE_FILE}"):
            open_carrier(tmp_path)

    def test_refuses_an_archive_with_no_catalogue(self, tmp_path: Path) -> None:
        wheel = tmp_path / "empty-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("empty-0.1.0.dist-info/METADATA", "Name: empty\n")

        with pytest.raises(ValueError, match=rf"carries no {CATALOGUE_FILE}"):
            open_carrier(wheel)

    def test_refuses_a_carrier_whose_catalogue_lists_a_missing_page_and_names_the_entry(
        self, tmp_path: Path
    ) -> None:
        exploded = _copy_real_carrier_into(tmp_path / "narrativetrace_skills-0.2.0")
        (exploded / CARRIER_ROOT / "claude" / "narrativetrace-doctor" / "SKILL.md").unlink()

        with pytest.raises(ValueError, match=r"narrativetrace-doctor at claude/"):
            open_carrier(exploded)

    def test_refuses_a_carrier_whose_catalogue_is_malformed_and_names_the_file(
        self, tmp_path: Path
    ) -> None:
        exploded = _copy_real_carrier_into(tmp_path / "narrativetrace_skills-0.2.0")
        (exploded / CARRIER_ROOT / CATALOGUE_FILE).write_text('{"runtime":', encoding="utf-8")

        with pytest.raises(ValueError, match=r"catalogue\.json is unusable: malformed JSON"):
            open_carrier(exploded)

    def test_refuses_a_carrier_page_that_is_not_utf8_and_names_the_file(
        self, tmp_path: Path
    ) -> None:
        exploded = _copy_real_carrier_into(tmp_path / "narrativetrace_skills-0.2.0")
        page = exploded / CARRIER_ROOT / "agents" / "narrativetrace-doctor" / "SKILL.md"
        page.write_bytes(b"\xff\xfe\xfd")

        with pytest.raises(ValueError, match=r"cannot read the carrier file .*SKILL\.md"):
            open_carrier(exploded)

    def test_refuses_a_corrupt_archive(self, tmp_path: Path) -> None:
        wheel = tmp_path / "narrativetrace_skills-0.2.0-py3-none-any.whl"
        wheel.write_text("this is not a zip archive", encoding="utf-8")

        with pytest.raises(ValueError, match=r"cannot read the carrier archive .*\.whl"):
            open_carrier(wheel)

    def test_refuses_to_hand_out_a_body_for_a_skill_the_carrier_does_not_list(self) -> None:
        carrier = carriers.real()
        stranger = SkillEntry("stranger", "d", "agents/x/SKILL.md", "claude/x/SKILL.md")

        with pytest.raises(ValueError, match=r"does not carry stranger"):
            carrier.body(stranger, SkillFlavour.AGENTS)

    def test_refuses_no_path_and_no_skill(self) -> None:
        with pytest.raises(ValueError, match=r"a carrier path must be given"):
            open_carrier(None)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match=r"a skill must be given"):
            carriers.real().body(None, SkillFlavour.AGENTS)  # type: ignore[arg-type]


class TestTheCoordinateACarrierStampsWith:
    """Rule 10: the coordinate is honest, and visibly stale where it cannot be known. It is written
    into every page the carrier installs and read back by the doctor, so a name that cannot produce
    one is refused before any page is written."""

    def test_falls_back_to_an_unknown_version_when_the_name_carries_none(
        self, tmp_path: Path
    ) -> None:
        exploded = _copy_real_carrier_into(tmp_path / "narrativetrace_skills")

        assert open_carrier(exploded).coordinate == "narrativetrace-skills==unknown"

    def test_reads_no_version_from_a_name_whose_trailing_dash_starts_nothing(
        self, tmp_path: Path
    ) -> None:
        exploded = _copy_real_carrier_into(tmp_path / "narrativetrace_skills-")

        assert open_carrier(exploded).coordinate == "narrativetrace-skills-==unknown"

    def test_normalises_an_underscored_distribution_name_the_way_a_wheel_does(
        self, tmp_path: Path
    ) -> None:
        exploded = _copy_real_carrier_into(tmp_path / "narrativetrace_skills-1.2.3")

        assert open_carrier(exploded).coordinate == "narrativetrace-skills==1.2.3"

    @pytest.mark.parametrize("name", ["a==b-1.2.3", "skills-1==2", "skills-1 2", "..-1.2.3"])
    def test_refuses_a_name_that_cannot_produce_a_coordinate(
        self, tmp_path: Path, name: str
    ) -> None:
        """The separator is ``==`` here, not Java's ``:`` — and whitespace matters just as much,
        because a stamp is one token a doctor later splits on that separator."""
        exploded = _copy_real_carrier_into(tmp_path / name)

        with pytest.raises(ValueError, match=r"does not name one"):
            open_carrier(exploded)

    def test_refuses_a_name_that_leaves_the_distribution_empty(self, tmp_path: Path) -> None:
        exploded = _copy_real_carrier_into(tmp_path / "-1.2.3")

        with pytest.raises(ValueError, match=r"does not name one"):
            open_carrier(exploded)


class TestReadingInsideAnArchive:
    """The zip half of the reader. Built by hand here rather than with ``uv build``: what these pin
    is a BROKEN archive, and a real build never produces one."""

    def test_refuses_an_archive_whose_catalogue_lists_a_page_it_does_not_carry(
        self, tmp_path: Path
    ) -> None:
        wheel = _wheel_missing_a_page(tmp_path, page_bytes=None)

        with pytest.raises(ValueError, match=r"narrativetrace-doctor at claude/"):
            open_carrier(wheel)

    def test_refuses_an_archive_page_that_is_not_utf8_and_names_the_entry(
        self, tmp_path: Path
    ) -> None:
        wheel = _wheel_missing_a_page(tmp_path, page_bytes=b"\xff\xfe\xfd")

        with pytest.raises(ValueError, match=r"cannot read the carrier file .*SKILL\.md"):
            open_carrier(wheel)

    def test_reads_a_wheel_name_with_no_version_part_as_an_unknown_version(
        self, tmp_path: Path
    ) -> None:
        """A file that is named like an archive but not like a wheel: no coordinate can be read out
        of it, so the version is the honest ``unknown`` rather than a guess."""
        wheel = tmp_path / "carrier.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            _write_carrier_entries(archive)

        assert open_carrier(wheel).coordinate == "carrier==unknown"


class TestWhenAFileWillNotBeRead:
    def test_names_the_file_when_reading_it_fails_for_a_reason_other_than_its_encoding(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A page that exists and cannot be read is not the same as one that is absent: absent
        means "the carrier does not carry it", and unreadable means "something is wrong here". The
        failure is injected because a permission this container cannot set is still one a
        consumer's filesystem can."""
        exploded = _copy_real_carrier_into(tmp_path / "narrativetrace_skills-0.2.0")
        readable = Path.read_bytes

        def refuse(self: Path) -> bytes:
            if self.name == "SKILL.md":
                raise OSError(13, "Permission denied")
            return readable(self)

        monkeypatch.setattr(Path, "read_bytes", refuse)

        with pytest.raises(ValueError, match=r"cannot read the carrier file .*SKILL\.md"):
            open_carrier(exploded)


class TestWhereAnInstalledDistributionKeepsItsPayload:
    """``_payload_candidates`` is where an editable install is found. Driven through real
    :class:`importlib.metadata.PathDistribution` values over synthetic ``.dist-info`` directories,
    because the branches are about what a distribution's own metadata says."""

    def test_an_ordinary_install_is_found_beside_the_importable_packages(
        self, tmp_path: Path
    ) -> None:
        distribution = _dist_info(tmp_path, direct_url=None)

        candidates = carrier_module._payload_candidates(distribution, CARRIER_ROOT)

        assert candidates == (tmp_path / CARRIER_ROOT,)

    def test_an_editable_install_is_followed_back_to_its_project_directory(
        self, tmp_path: Path
    ) -> None:
        project = tmp_path / "project"
        distribution = _dist_info(tmp_path, direct_url=f'{{"url": "{project.as_uri()}"}}')

        candidates = carrier_module._payload_candidates(distribution, CARRIER_ROOT)

        assert project / CARRIER_ROOT in candidates
        assert project / "src" / CARRIER_ROOT in candidates

    @pytest.mark.parametrize(
        "direct_url", ["not json at all", '{"url": 7}', '{"url": "https://example.test/x"}', "{}"]
    )
    def test_a_direct_url_that_names_no_local_project_is_simply_not_followed(
        self, tmp_path: Path, direct_url: str
    ) -> None:
        distribution = _dist_info(tmp_path, direct_url=direct_url)

        candidates = carrier_module._payload_candidates(distribution, CARRIER_ROOT)

        assert candidates == (tmp_path / CARRIER_ROOT,)

    def test_a_windows_style_drive_path_loses_the_leading_slash_a_file_url_adds(self) -> None:
        assert carrier_module._local_path("/C:/projects/x") == "C:/projects/x"
        assert carrier_module._local_path("/home/dev/x") == "/home/dev/x"


class TestAHandBuiltCarrier:
    def test_carries_one_page_per_name_in_both_flavours(self, tmp_path: Path) -> None:
        carrier = carriers.fake(tmp_path, "doctor", "clarity")

        assert [skill.name for skill in carrier.skills] == ["doctor", "clarity"]
        for skill in carrier.skills:
            for flavour in SkillFlavour:
                assert carrier.body(skill, flavour) == carriers.body(skill.name, flavour)

    def test_stamps_with_the_coordinate_its_directory_name_yields(self, tmp_path: Path) -> None:
        assert carriers.fake(tmp_path, "doctor").coordinate == carriers.FAKE_COORDINATE


def _dist_info(parent: Path, *, direct_url: str | None) -> importlib_metadata.PathDistribution:
    """A synthetic installed distribution: the least metadata ``importlib.metadata`` will accept."""
    info = parent / "synthetic-0.0.1.dist-info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: synthetic\nVersion: 0.0.1\n", encoding="utf-8"
    )
    if direct_url is not None:
        (info / "direct_url.json").write_text(direct_url, encoding="utf-8")
    return importlib_metadata.PathDistribution(info)


def _write_carrier_entries(archive: zipfile.ZipFile, *, skip: str = "") -> None:
    """Every entry the real checked-in carrier holds, optionally leaving one out."""
    root = carriers.real_carrier_directory()
    for file in sorted(root.rglob("*")):
        if file.is_file():
            relative = file.relative_to(root).as_posix()
            if relative != skip:
                archive.writestr(f"{CARRIER_ROOT}/{relative}", file.read_bytes())


def _wheel_missing_a_page(parent: Path, *, page_bytes: bytes | None) -> Path:
    """A wheel whose catalogue lists ``claude/narrativetrace-doctor/SKILL.md`` while the archive
    either lacks it or carries bytes that are not UTF-8."""
    missing = "claude/narrativetrace-doctor/SKILL.md"
    wheel = parent / f"narrativetrace_skills-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        _write_carrier_entries(archive, skip=missing)
        if page_bytes is not None:
            archive.writestr(f"{CARRIER_ROOT}/{missing}", page_bytes)
    return wheel


def _copy_real_carrier_into(target: Path) -> Path:
    shutil.copytree(carriers.real_carrier_directory(), target / CARRIER_ROOT)
    return target


def _build_carrier_wheel(out_dir: Path) -> Path:
    if shutil.which("uv") is None:
        pytest.skip("uv is not on PATH, so the built wheel cannot be inspected")
    build = subprocess.run(  # nosec B603, B607 # fixed argv, no shell, no untrusted input
        ["uv", "build", "--package", SKILLS_DISTRIBUTION, "--out-dir", str(out_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, f"uv build failed:\n{build.stdout}\n{build.stderr}"
    canonical = re.sub(r"[-_.]+", "_", SKILLS_DISTRIBUTION).lower()
    wheel = out_dir / f"{canonical}-{VERSION}-py3-none-any.whl"
    assert wheel.is_file(), f"{wheel.name} was not built"
    return wheel
