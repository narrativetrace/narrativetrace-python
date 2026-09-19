# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Self-check for the hostile corpus itself (mirrors Java's ``HostileCorpusTest``).

The corpus is a cross-runtime artifact copied byte-identically from the Java runtime; these tests
guard the copy, not the renderer -- a silently-truncated file or a duplicated id would otherwise
make every property test downstream pass for the wrong reason.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from hostile_corpus import (
    _CORPUS_DIR,
    graphs,
    injections,
    names,
    redactions,
    strings,
    templates,
    trace_shapes,
    traceparents,
    tracestates,
)

_FIXTURE_FILES = [
    "strings.json",
    "headers.json",
    "templates.json",
    "graphs.json",
    "injection.json",
    "names.json",
    "redaction.json",
    "trace-shapes.json",
]
_ALLOWED_NON_ASCII = "—"  # em-dash, allowed in prose (matches the Java corpus's own rule)


class TestMinimumCaseCounts:
    """A corpus that shrank silently is a corpus that stopped testing what it claims to."""

    def test_strings_has_more_than_seventy_cases(self) -> None:
        # Raised from 50 (mirrors Java's HostileCorpusTest, 2026-09-13): 71 -> 75 cases, the four
        # `diagram-alias-*` rows added for Mermaid's alias-mode participant derivation.
        assert len(strings()) > 70

    def test_injections_has_more_than_thirty_cases(self) -> None:
        assert len(injections()) > 30

    def test_traceparents_has_more_than_thirty_cases(self) -> None:
        assert len(traceparents()) > 30

    def test_tracestates_has_more_than_five_cases(self) -> None:
        assert len(tracestates()) > 5

    def test_templates_has_more_than_thirty_cases(self) -> None:
        assert len(templates()) > 30

    def test_graphs_has_more_than_forty_cases(self) -> None:
        assert len(graphs()) > 40

    def test_names_has_more_than_fifteen_cases(self) -> None:
        assert len(names()) > 15

    def test_redactions_has_more_than_sixty_cases(self) -> None:
        assert len(redactions()) > 60

    def test_trace_shapes_has_at_least_four_cases(self) -> None:
        assert len(trace_shapes()) >= 4


class TestIdsAreUniqueAndDescribed:
    @pytest.mark.parametrize(
        "cases",
        [
            strings(),
            injections(),
            traceparents(),
            tracestates(),
            templates(),
            graphs(),
            names(),
            redactions(),
            trace_shapes(),
        ],
    )
    def test_ids_are_unique(self, cases: tuple[object, ...]) -> None:
        ids = [c.id for c in cases]  # type: ignore[attr-defined]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize(
        "cases",
        [
            strings(),
            injections(),
            traceparents(),
            tracestates(),
            templates(),
            graphs(),
            names(),
            redactions(),
            trace_shapes(),
        ],
    )
    def test_descriptions_are_non_blank(self, cases: tuple[object, ...]) -> None:
        assert all(c.description.strip() for c in cases)  # type: ignore[attr-defined]


class TestAsciiOnDisk:
    """Every hostile character lives in the file as a ``\\uXXXX`` escape, never a raw byte, so a
    diff or an editor with the wrong encoding cannot silently mangle a case."""

    @pytest.mark.parametrize("filename", _FIXTURE_FILES)
    def test_fixture_file_is_ascii_except_the_allowed_em_dash(self, filename: str) -> None:
        text = (_CORPUS_DIR / filename).read_text(encoding="utf-8")
        offenders = {c for c in text if ord(c) > 126} - set(_ALLOWED_NON_ASCII)
        assert not offenders


class TestRepeatMaterialization:
    def test_long_1mib_is_exactly_one_mebibyte(self) -> None:
        case = next(c for c in strings() if c.id == "long-1mib")
        assert len(case.value) == 1024 * 1024

    def test_many_open_braces_is_exactly_ten_thousand_characters(self) -> None:
        case = next(c for c in templates() if c.id == "many-open-braces")
        assert case.template == "{" * 10_000

    def test_very_long_fields_keeps_its_prefix_and_repeats_the_extension(self) -> None:
        case = next(c for c in traceparents() if c.id == "very-long-fields")
        assert case.value.startswith("01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01")
        assert case.value.count("-x") == 100_000
        assert case.accepted


class TestSpecificHostileCodepointsArePresent:
    """`chr(codepoint)` throughout -- embedding the raw invisible/bidi characters themselves in
    this source file would be the "trojan source" hazard this suite exists to catch elsewhere
    (see strings.json's own `rtl-override`/`zero-width` cases)."""

    def test_nul_is_present(self) -> None:
        assert any(c.value == chr(0x0000) for c in strings())

    def test_rtl_override_is_present(self) -> None:
        assert any(chr(0x202E) in c.value for c in strings())

    def test_unpaired_high_and_low_surrogates_are_present(self) -> None:
        assert any(c.value == chr(0xD800) for c in strings())
        assert any(c.value == chr(0xDC00) for c in strings())

    def test_zero_width_space_is_present(self) -> None:
        assert any(chr(0x200B) in c.value for c in strings())

    def test_noncharacter_arabic_block_is_present(self) -> None:
        assert any(c.value == chr(0xFDD0) + chr(0xFDEF) for c in strings())

    def test_noncharacter_supplementary_is_present(self) -> None:
        # The JSON fixture spells these as UTF-16 surrogate-pair escapes (Java's `char` is a
        # UTF-16 code unit), but Python's JSON decoder combines a valid surrogate pair into one
        # real code point -- so the case surfaces here as the two astral noncharacters directly,
        # not as four surrogate halves.
        assert any(c.value == chr(0x1FFFE) + chr(0x1FFFF) for c in strings())


class TestHeaderFixtureHasBothOutcomes:
    def test_at_least_one_traceparent_is_accepted(self) -> None:
        assert any(c.accepted for c in traceparents())

    def test_at_least_one_traceparent_is_rejected(self) -> None:
        assert any(not c.accepted for c in traceparents())


class TestGraphShapesAllDeclareEitherLayersOrKind:
    def test_every_graph_case_is_a_layer_stack_or_a_named_kind(self) -> None:
        assert all(c.kind is not None or c.layers is not None for c in graphs())


class TestTraceShapesCoverBothKinds:
    def test_at_least_one_chain_and_one_cycle_case_exist(self) -> None:
        kinds = {c.kind for c in trace_shapes()}
        assert kinds == {"chain", "cycle"}


class TestRedactionCasesDeclareExactlyOneSubjectAndOneDirection:
    """A row that named neither a field, a value, nor a ``kind`` -- or that named more than one,
    or carried an unreadable ``expect`` -- would be replayed as a silently trivial assertion (or
    not replayed at all): the same failure mode as a fixture that stopped loading, one row at a
    time."""

    def test_every_case_carries_a_canary_or_a_value(self) -> None:
        assert all(c.secret.strip() for c in redactions())

    def test_every_case_declares_exactly_one_of_name_value_or_kind(self) -> None:
        for case in redactions():
            subjects = [case.name is not None, case.value is not None, case.kind is not None]
            assert sum(subjects) == 1, f"{case.id}: must declare exactly one of name/value/kind"

    def test_every_case_declares_which_way_it_goes(self) -> None:
        assert all(c.expect in ("redacted", "visible") for c in redactions())


class TestRedactionPositionIsWellFormed:
    """ADV-2026-09-14-1: ``position`` only ever means "as a map key", and only a value case may
    declare it -- a name case already renders as a dict, under its own field name, so a second
    map position on top of that would test nothing new. At least one row must use it, or the
    map-KEY value-shape axis is back to being asserted nowhere in the corpus."""

    def test_every_declared_position_is_map_key_on_a_value_case(self) -> None:
        for case in redactions():
            if case.position is None:
                continue
            assert case.position == "mapKey", f"{case.id} declares an unknown position"
            assert not case.is_name, f"{case.id}: only a value case may declare a map-key position"
            assert not case.is_kind, f"{case.id}: only a value case may declare a map-key position"

    def test_at_least_one_row_places_its_value_as_a_map_key(self) -> None:
        assert any(c.is_map_key for c in redactions())

    def test_a_map_key_row_renders_its_value_as_the_key_of_a_one_entry_dict(self) -> None:
        for case in redactions():
            if case.is_map_key:
                assert case.payload == {case.value: "visible-value"}, case.id


class TestNoRedactionCanaryIsItselfASecretShape:
    """A name or ``kind`` case whose canary is itself secret-shaped would pass the hidden
    assertion for the wrong reason -- the value axis would catch it whatever the name said."""

    def test_every_name_or_kind_case_canary_matches_the_canary_naming_convention(self) -> None:
        for case in redactions():
            if case.is_name or case.is_kind:
                assert case.canary is not None
                assert re.fullmatch(r"canary-[a-z0-9-]+", case.canary)


# --------------------------------------------------------------------------- #
# Byte-identity with the master copy (§6.7: the corpus master lives in the free #
# Java repository; every runtime copies it verbatim).                           #
# --------------------------------------------------------------------------- #
_MASTER_RELATIVE = Path("narrativetrace-security-tests/src/test/resources/hostile-corpus")


def _master_corpus_dir() -> Path | None:
    """Where the master corpus is mounted, or ``None`` when it is not reachable. `NT_MASTER_CORPUS`
    names the directory outright; otherwise `JAVA_REPO`, the dev container's `/workspace-java`
    mount (`scripts/dev-container.sh`) and the sibling checkout are tried in that order."""
    named = os.environ.get("NT_MASTER_CORPUS")
    if named:
        return Path(named) if Path(named).is_dir() else None
    roots = [os.environ.get("JAVA_REPO"), "/workspace-java", "../../../../narrative-trace-java"]
    for root in roots:
        if root is None:
            continue
        candidate = (
            Path(__file__).parent / root if root.startswith("..") else Path(root)
        ).resolve()
        if (candidate / _MASTER_RELATIVE).is_dir():
            return candidate / _MASTER_RELATIVE
    return None


def _require_master_corpus() -> Path:
    """The master corpus directory, or a LOUD skip -- release rule 2: a check that silently
    no-ops is a check nobody can prove ever ran."""
    master = _master_corpus_dir()
    if master is None:
        message = (
            "SKIPPED: master corpus not mounted — set NT_MASTER_CORPUS or JAVA_REPO, or run in "
            "the dev container where it is mounted read-only at /workspace-java"
        )
        print(message, file=sys.stderr)
        pytest.skip(message)
    return master


def _git_toplevel(path: Path) -> Path | None:
    """The git repository root containing ``path``, or ``None`` when ``path`` is not inside a git
    working copy at all (a plain directory mount, an extracted archive, ...)."""
    result = subprocess.run(  # nosec B603, B607 - fixed args, no shell, a local read-only query
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def _master_file_bytes(master_dir: Path, filename: str) -> tuple[bytes, str]:
    """Bytes of ``filename`` in the master corpus, and a description of what was actually
    compared -- design flaw fixed 2026-09-18: reading the master's WORKING-TREE file made this
    test go red the moment an in-progress master edit touched the same file, before anything was
    even committed there. Compares against the master's own COMMITTED ``HEAD`` instead
    (``git -C <master repo> show HEAD:<relative path>``), which is immune to a concurrent dirty
    edit; falls back to the working-tree file, loudly, only when the mount is not a git checkout
    at all (a plain directory mount with no ``.git``) -- the one case ``git show`` has nothing to
    read from."""
    file_path = master_dir / filename
    toplevel = _git_toplevel(master_dir)
    if toplevel is None:
        message = (
            f"master mount at {master_dir} is not a git checkout (no .git found) — comparing "
            "against its WORKING-TREE file, not a committed ref"
        )
        print(message, file=sys.stderr)
        return file_path.read_bytes(), "working tree (mount is not a git checkout)"
    try:
        relative = file_path.resolve().relative_to(toplevel.resolve())
    except ValueError:
        message = (
            f"{file_path} is not inside git toplevel {toplevel} — comparing its working tree file"
        )
        print(message, file=sys.stderr)
        return file_path.read_bytes(), "working tree (path escapes the git toplevel)"
    ref = f"HEAD:{relative.as_posix()}"
    result = subprocess.run(  # nosec B603, B607 - fixed args, no shell, a local read-only query
        ["git", "-C", str(toplevel), "show", ref],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = f"git show {ref} failed in {toplevel} — falling back to the working-tree file"
        print(message, file=sys.stderr)
        return file_path.read_bytes(), "working tree (git show failed)"
    description = f"{ref} in {toplevel}"
    print(f"comparing {filename} against the master's committed {description}", file=sys.stderr)
    return result.stdout, description


class TestByteIdentityWithTheMasterCorpus:
    """§6.7: a row is byte-identical across every runtime or it is not the same row. A port that
    quietly lacks a master row tests less than it claims to (this is how `graphs.json`'s four
    `curated-tostring-*`/`sensitive-map-key`/`throwing-summary` rows went missing until
    2026-09-17), and one that quietly adds a row tests something no other runtime does (owner
    ruling 2026-09-18: the master is the source of truth, no documented-extras exemption --
    `redaction.json`'s four `kind` rows, added here 2026-09-11 ahead of the master and removed the
    same day to restore byte-identity, were proposed to the master separately and ADOPTED there
    unchanged (ids, `kind` names and canaries all identical); copied back verbatim once the master
    carried them).

    Compares against the master's own committed ``HEAD`` (see :func:`_master_file_bytes`), never
    its working tree (design flaw fixed 2026-09-18): a mount read via the working tree turned this
    port red the moment an in-progress, uncommitted master edit touched the same file, which is
    not the byte-identity contract this class actually exists to enforce -- byte-identity is a
    contract between committed history, not between one runtime's committed state and another's
    mid-edit scratch. Falls back to the working-tree file, loudly, only when the mount is not a
    git checkout at all."""

    @pytest.mark.parametrize("filename", _FIXTURE_FILES)
    def test_the_fixture_file_is_byte_identical_to_the_master(self, filename: str) -> None:
        master = _require_master_corpus()
        master_bytes, compared_against = _master_file_bytes(master, filename)
        assert (_CORPUS_DIR / filename).read_bytes() == master_bytes, (
            f"{filename} has drifted from the master's {compared_against} — copy it from the "
            "master, never retype"
        )
