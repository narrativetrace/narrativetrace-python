# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from __future__ import annotations

from snapshot_factory_types import MakeSnapshot

from narrativetrace_tooling.doctor.checks.skills_installed import _DOC_URL, check_skills_installed
from narrativetrace_tooling.init.catalogue import SkillFlavour
from narrativetrace_tooling.init.project_state import InstalledSkill, Presence

_CATALOGUE = ("narrativetrace-doctor", "add-narrative-tracing")
_VERSION = "1.2.3"
_CARRIER = f"narrativetrace-skills=={_VERSION}"
_OLDER = "narrativetrace-skills==0.0.1"


def _installed(name: str, coordinate: str = _CARRIER) -> InstalledSkill:
    return InstalledSkill(SkillFlavour.AGENTS, name, Presence.OURS, coordinate, "page")


def _theirs(name: str) -> InstalledSkill:
    return InstalledSkill(SkillFlavour.AGENTS, name, Presence.FOREIGN, "", "")


class TestPassingOutcomes:
    def test_passes_when_every_catalogue_skill_is_installed_and_current(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(
                _installed("narrativetrace-doctor"),
                _installed("add-narrative-tracing"),
            ),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.id == "config.skills-installed"
        assert finding.status == "pass"
        assert "2" in finding.message

    def test_passes_and_says_cannot_tell_when_the_project_version_is_unknown(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        """The empty-project path the install prompt starts from is not a defect."""
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(_installed("narrativetrace-doctor", _OLDER),),
            narrativetrace_version=None,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "pass"
        assert finding.message == (
            "this project's narrativetrace version could not be determined — cannot tell whether"
            " the agent skills are current"
        )

    def test_a_skill_directory_the_catalogue_never_named_is_ignored(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(
                _installed("narrativetrace-doctor"),
                _installed("add-narrative-tracing"),
                _theirs("deploy-to-staging"),
            ),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "pass"
        assert "deploy-to-staging" not in finding.message

    def test_a_stamp_naming_a_different_package_at_the_same_version_is_current(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        """Only the version half of a stamp is compared, never the whole coordinate — the two
        distributions this port ships can be pinned independently (D1)."""
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(
                _installed("narrativetrace-doctor", f"narrativetrace=={_VERSION}"),
                _installed("add-narrative-tracing", f"narrativetrace=={_VERSION}"),
            ),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "pass"


class TestNotInstalled:
    def test_fails_when_nothing_is_installed(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(catalogue_skill_names=_CATALOGUE, narrativetrace_version=_VERSION)
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert (
            finding.message
            == "the NarrativeTrace agent skills are not installed under .agents/skills/"
        )
        assert finding.fix == (
            "Run `uv run narrativetrace init --dry-run`, read the diff, then run it without the"
            " flag."
        )

    def test_where_nothing_is_installed_and_nothing_is_foreign_nobody_is_blamed(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(catalogue_skill_names=_CATALOGUE, narrativetrace_version=_VERSION)
        finding = check_skills_installed(snapshot)
        assert (
            finding.message
            == "the NarrativeTrace agent skills are not installed under .agents/skills/"
        )

    def test_two_foreign_directories_are_both_named_comma_separated(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(
                _theirs("narrativetrace-doctor"),
                _theirs("add-narrative-tracing"),
            ),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert "narrativetrace-doctor, add-narrative-tracing is there, not ours" in finding.message

    def test_a_page_that_is_there_without_our_line_names_the_registry_case_and_the_fix(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        """The obvious reading of "not ours" is "somebody else's work", which invites a ``--force``
        nobody needs: a page identical to this release's is ADOPTED. The fix says so in as many
        words, because this message is the one a person acts on."""
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(_theirs("narrativetrace-doctor"),),
            narrativetrace_version=_VERSION,
        )

        finding = check_skills_installed(snapshot)

        assert finding.fix == (
            "Run `uv run narrativetrace init --dry-run`, read the diff, then run it without the"
            " flag. Pages that are there without our line usually came from a registry (npx skills"
            " add, a plugin or workspace install). A page identical to this release's is adopted,"
            " and no --force is needed."
        )

    def test_the_registry_sentence_is_absent_when_no_page_is_there_at_all(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        """Nothing to explain: the project simply never ran the installer."""
        snapshot = make_snapshot(catalogue_skill_names=_CATALOGUE, narrativetrace_version=_VERSION)

        assert "registry" not in check_skills_installed(snapshot).fix

    def test_names_a_foreign_directory_at_a_skills_path(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(_theirs("narrativetrace-doctor"),),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert "narrativetrace-doctor" in finding.message
        assert "not ours" in finding.message

    def test_the_vendor_copy_alone_is_not_an_install(self, make_snapshot: MakeSnapshot) -> None:
        """``.agents/skills/`` is the layout every project gets; the vendor copy is written only
        where a project is detected as that vendor's, so a vendor-only install is no install."""
        vendor_only = InstalledSkill(
            SkillFlavour.CLAUDE, "narrativetrace-doctor", Presence.OURS, _CARRIER, "page"
        )
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(vendor_only,),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert "not installed" in finding.message

    def test_a_file_where_a_skill_directory_belongs_counts_as_missing(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        not_a_directory = InstalledSkill(
            SkillFlavour.AGENTS, "narrativetrace-doctor", Presence.NOT_A_DIRECTORY
        )
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(not_a_directory,),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert "narrativetrace-doctor" in finding.message
        assert "not ours" in finding.message


class TestStale:
    def test_fails_naming_both_the_stale_stamp_and_the_projects_version(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(
                _installed("narrativetrace-doctor", _OLDER),
                _installed("add-narrative-tracing", _OLDER),
            ),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert finding.message == (
            f"agent skills installed from {_OLDER}, project resolves narrativetrace=={_VERSION}"
        )
        assert finding.fix == (
            "Re-run `uv run narrativetrace init --dry-run` and apply it — the installed pages"
            " describe a different release of NarrativeTrace than this project uses."
        )

    def test_every_distinct_stale_stamp_is_named_once_comma_separated(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        other_stale = "narrativetrace-skills==0.0.2"
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(
                _installed("narrativetrace-doctor", _OLDER),
                _installed("add-narrative-tracing", other_stale),
            ),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert f"{_OLDER}, {other_stale}" in finding.message

    def test_a_stamp_with_an_extra_separator_is_compared_as_it_stands_and_reads_as_stale(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        """A hand-edited three-part stamp (two ``==``) — the near-miss the brief names as 'a
        three-part version only' — names no version anybody could line up against the project's
        clean one, so it is compared whole and reads as stale, same as a bare, separator-less
        stamp would."""
        three_part = "narrativetrace-skills==1.2.3==4"
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(
                _installed("narrativetrace-doctor", three_part),
                _installed("add-narrative-tracing", three_part),
            ),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert three_part in finding.message

    def test_a_bare_stamp_with_no_separator_at_all_is_compared_as_it_stands(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        bare = "hand-edited"
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(
                _installed("narrativetrace-doctor", bare),
                _installed("add-narrative-tracing", bare),
            ),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert bare in finding.message

    def test_the_version_half_is_taken_after_the_first_separator_not_the_last(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        """A coordinate with two ``==`` splits differently depending on which separator wins:
        taking the FIRST (this check's own rule) reads ``y==z`` as the version of
        ``x==y==z``, which then matches a project resolving exactly that string — proving the
        implementation does not silently take the last separator instead."""
        stamp = "x==y==z"
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(
                _installed("narrativetrace-doctor", stamp),
                _installed("add-narrative-tracing", stamp),
            ),
            narrativetrace_version="y==z",
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "pass"

    def test_stale_beats_missing_reporting_the_stamp(self, make_snapshot: MakeSnapshot) -> None:
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(_installed("narrativetrace-doctor", _OLDER),),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert _OLDER in finding.message


class TestPartial:
    def test_fails_naming_the_missing_skill_when_only_some_are_installed(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(_installed("narrativetrace-doctor"),),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert (
            finding.message
            == "the agent skills are installed, but add-narrative-tracing is missing"
        )
        assert finding.fix == (
            "Run `uv run narrativetrace init --dry-run` to add the missing page(s). A page"
            " identical to this release's is adopted as it stands; --force is only for a directory"
            " somebody else really owns."
        )

    def test_two_missing_skills_are_both_named_comma_separated(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        """One of the catalogue's three skills is installed (so the check reaches `_incomplete`,
        not `_not_installed`) and the other two are genuinely missing, exercising the comma-joined
        `missing()` list with more than one entry."""
        snapshot = make_snapshot(
            catalogue_skill_names=(*_CATALOGUE, "narrativetrace-pro-aggregate"),
            installed_skills=(_installed("narrativetrace-doctor"),),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert "add-narrative-tracing, narrativetrace-pro-aggregate is missing" in finding.message

    def test_a_foreign_directory_at_the_missing_skills_path_is_reported_not_counted(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshot = make_snapshot(
            catalogue_skill_names=_CATALOGUE,
            installed_skills=(
                _installed("narrativetrace-doctor"),
                _theirs("add-narrative-tracing"),
            ),
            narrativetrace_version=_VERSION,
        )
        finding = check_skills_installed(snapshot)
        assert finding.status == "fail"
        assert "add-narrative-tracing" in finding.message
        assert "not ours" in finding.message


class TestEveryOutcomeSharesShape:
    def test_every_outcome_carries_the_stable_id_and_the_published_doc_url(
        self, make_snapshot: MakeSnapshot
    ) -> None:
        snapshots = [
            make_snapshot(),
            make_snapshot(catalogue_skill_names=_CATALOGUE, narrativetrace_version=_VERSION),
            make_snapshot(
                catalogue_skill_names=_CATALOGUE,
                installed_skills=(_installed("narrativetrace-doctor", _OLDER),),
                narrativetrace_version=_VERSION,
            ),
            make_snapshot(
                catalogue_skill_names=_CATALOGUE,
                installed_skills=(_installed("narrativetrace-doctor"),),
                narrativetrace_version=_VERSION,
            ),
            make_snapshot(
                catalogue_skill_names=_CATALOGUE,
                installed_skills=(
                    _installed("narrativetrace-doctor"),
                    _installed("add-narrative-tracing"),
                ),
                narrativetrace_version=_VERSION,
            ),
        ]
        for snapshot in snapshots:
            finding = check_skills_installed(snapshot)
            assert finding.id == "config.skills-installed"
            assert finding.doc_url == _DOC_URL

    def test_no_skill_fixes_this_finding_class(self, make_snapshot: MakeSnapshot) -> None:
        """`config.skills-installed` is one of the two deliberate no-skill ids: naming a skill
        would point at the very page that is missing."""
        finding = check_skills_installed(make_snapshot())
        assert finding.skill is None
