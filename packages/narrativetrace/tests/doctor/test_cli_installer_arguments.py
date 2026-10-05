# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""``parse_installer_arguments`` — what ``init``/``uninstall`` were asked for, out of a command line
and nothing else.

Named after the Java port's ``InstallerArgumentsTest`` so the two case lists diff. Every case
here is pure: no project, no carrier, no process.
"""

from __future__ import annotations

import pytest

from narrativetrace.doctor.cli_bin import InstallerArguments, parse_installer_arguments
from narrativetrace_tooling.init import Scope, Vendor


class TestGuardsAndTheInvariant:
    def test_no_command_line_at_all_is_a_type_error(self) -> None:
        with pytest.raises(
            TypeError, match=r"\Aa command line is a sequence of arguments, never None\Z"
        ):
            parse_installer_arguments(None)  # type: ignore[arg-type]

    def test_a_problem_that_says_nothing_is_refused_at_construction(self) -> None:
        with pytest.raises(AssertionError, match=r"\Aa read command line must say what it read\Z"):
            InstallerArguments(error="")

    def test_a_carrier_that_names_nothing_is_refused_at_construction(self) -> None:
        with pytest.raises(AssertionError, match=r"\Aa read command line must say what it read\Z"):
            InstallerArguments(from_path="")

    def test_every_flag_this_cli_accepts_keeps_the_invariant(self) -> None:
        """The parser is the only caller that builds these, so "it cannot produce an empty message
        or an empty path" is the claim — asserted over the whole flag surface at once."""
        parsed = parse_installer_arguments(
            ["--dry-run", "--write-existing", "--force", "--json", "--only=skills", "--from", "x"]
        )

        assert parsed.error is None
        assert parsed.from_path == "x"


class TestDefaults:
    def test_no_arguments_is_the_default_install_whole(self) -> None:
        assert parse_installer_arguments([]) == InstallerArguments()

    def test_the_default_install_writes_nothing_it_was_not_asked_to(self) -> None:
        options = parse_installer_arguments([]).options

        assert options.dry_run is False
        assert options.write_existing is False
        assert options.force is False

    def test_the_default_install_covers_both_halves_and_detects_the_vendor(self) -> None:
        options = parse_installer_arguments([]).options

        assert options.scope is Scope.BOTH
        assert options.vendor_claude is Vendor.AUTO

    def test_the_launcher_is_asked_for_nothing_by_default(self) -> None:
        parsed = parse_installer_arguments([])

        assert parsed.from_path is None
        assert parsed.as_json is False
        assert parsed.help_wanted is False
        assert parsed.error is None


class TestSwitches:
    def test_dry_run_asks_for_a_preview(self) -> None:
        assert parse_installer_arguments(["--dry-run"]).options.dry_run is True

    def test_write_existing_grants_permission_to_touch_a_context_file(self) -> None:
        assert parse_installer_arguments(["--write-existing"]).options.write_existing is True

    def test_force_grants_permission_to_overwrite_somebody_elses_directory(self) -> None:
        assert parse_installer_arguments(["--force"]).options.force is True

    def test_json_asks_for_the_envelope(self) -> None:
        assert parse_installer_arguments(["--json"]).as_json is True

    def test_both_spellings_of_help_ask_for_the_usage(self) -> None:
        assert parse_installer_arguments(["--help"]).help_wanted is True
        assert parse_installer_arguments(["-h"]).help_wanted is True

    def test_every_switch_at_once_is_every_switch(self) -> None:
        parsed = parse_installer_arguments(["--dry-run", "--write-existing", "--force", "--json"])

        assert parsed.options.dry_run is True
        assert parsed.options.write_existing is True
        assert parsed.options.force is True
        assert parsed.as_json is True
        assert parsed.error is None

    def test_a_repeated_switch_is_not_an_error(self) -> None:
        parsed = parse_installer_arguments(["--force", "--force"])

        assert parsed.options.force is True
        assert parsed.error is None


class TestFlagsThatTakeAValue:
    def test_only_skills_narrows_the_scope_to_the_pages(self) -> None:
        assert parse_installer_arguments(["--only", "skills"]).options.scope is Scope.SKILLS

    def test_only_agents_md_narrows_the_scope_to_the_section(self) -> None:
        assert parse_installer_arguments(["--only", "agents-md"]).options.scope is Scope.AGENTS_MD

    def test_vendor_claude_asks_for_the_vendor_flavour_everywhere(self) -> None:
        assert parse_installer_arguments(["--vendor", "claude"]).options.vendor_claude is Vendor.ON

    def test_vendor_none_refuses_the_vendor_flavour_everywhere(self) -> None:
        assert parse_installer_arguments(["--vendor", "none"]).options.vendor_claude is Vendor.OFF

    def test_from_names_a_carrier(self) -> None:
        assert parse_installer_arguments(["--from", "some.whl"]).from_path == "some.whl"

    def test_the_equals_spelling_reads_the_same_as_the_spaced_one(self) -> None:
        assert parse_installer_arguments(["--from=some.whl"]).from_path == "some.whl"
        assert parse_installer_arguments(["--only=skills"]).options.scope is Scope.SKILLS
        assert parse_installer_arguments(["--vendor=none"]).options.vendor_claude is Vendor.OFF

    def test_a_value_carrying_an_equals_sign_survives_whole(self) -> None:
        """Only the FIRST `=` separates the flag from its value, so a path carrying one arrives
        intact rather than truncated at it."""
        parsed = parse_installer_arguments(["--from=carriers/a=b/c.whl"])

        assert parsed.from_path == "carriers/a=b/c.whl"

    def test_a_value_flag_consumes_its_value_rather_than_reading_it_as_a_flag(self) -> None:
        parsed = parse_installer_arguments(["--only", "skills", "--json"])

        assert parsed.options.scope is Scope.SKILLS
        assert parsed.as_json is True
        assert parsed.error is None

    def test_the_last_spelling_of_a_repeated_value_flag_wins(self) -> None:
        parsed = parse_installer_arguments(["--only", "skills", "--only", "agents-md"])

        assert parsed.options.scope is Scope.AGENTS_MD
        assert parsed.error is None


class TestWhatCannotBeRead:
    def test_an_unknown_option_is_reported_with_its_own_spelling(self) -> None:
        assert parse_installer_arguments(["--nope"]).error == 'unknown option: "--nope"'

    def test_a_bare_word_is_an_unknown_option_too(self) -> None:
        assert parse_installer_arguments(["skills"]).error == 'unknown option: "skills"'

    def test_an_unknown_option_keeps_its_inline_value_in_the_message(self) -> None:
        assert parse_installer_arguments(["--nope=1"]).error == 'unknown option: "--nope=1"'

    def test_only_refuses_a_value_that_is_neither_half(self) -> None:
        assert (
            parse_installer_arguments(["--only", "everything"]).error
            == '--only takes skills or agents-md, got "everything"'
        )

    def test_vendor_refuses_a_value_that_is_neither_vendor(self) -> None:
        assert (
            parse_installer_arguments(["--vendor", "cursor"]).error
            == '--vendor takes claude or none, got "cursor"'
        )

    def test_a_value_flag_at_the_end_of_the_line_has_no_value(self) -> None:
        assert parse_installer_arguments(["--from"]).error == "--from needs a value"

    def test_an_empty_inline_value_is_no_value(self) -> None:
        assert parse_installer_arguments(["--only="]).error == "--only needs a value"

    def test_a_flag_missing_its_value_does_not_swallow_the_next_argument(self) -> None:
        """The refusal costs the reader nothing else: a flag written with no value consumes only
        itself, so whatever follows is still read (and still reported if IT is wrong too)."""
        parsed = parse_installer_arguments(["--only=", "--force"])

        assert parsed.error == "--only needs a value"
        assert parsed.options.force is True

    def test_the_next_flag_is_read_as_the_value_it_was_written_as(self) -> None:
        """``--only --json`` asked for a scope and gave a flag: the value is what follows,
        verbatim, so the message names what was actually written rather than guessing."""
        assert (
            parse_installer_arguments(["--only", "--json"]).error
            == '--only takes skills or agents-md, got "--json"'
        )

    def test_from_takes_a_following_flag_as_its_value_and_says_nothing(self) -> None:
        """`--from` accepts any string, so unlike `--only`/`--vendor` it cannot refuse a value that
        was meant as the next flag: `init --from --json` asks for a carrier named `--json` and drops
        the JSON request, with no error. Pinned because the surprise belongs on the record — the
        refusal a person eventually sees ("no carrier at --json") names what was typed."""
        parsed = parse_installer_arguments(["--from", "--json"])

        assert parsed.from_path == "--json"
        assert parsed.as_json is False
        assert parsed.error is None

    def test_a_value_flags_value_is_case_sensitive(self) -> None:
        assert (
            parse_installer_arguments(["--vendor", "Claude"]).error
            == '--vendor takes claude or none, got "Claude"'
        )

    def test_the_first_problem_is_the_one_reported(self) -> None:
        parsed = parse_installer_arguments(["--nope", "--only", "everything"])

        assert parsed.error == 'unknown option: "--nope"'

    def test_a_bad_flag_does_not_lose_the_good_ones_beside_it(self) -> None:
        parsed = parse_installer_arguments(["--dry-run", "--nope", "--json"])

        assert parsed.options.dry_run is True
        assert parsed.as_json is True
        assert parsed.error == 'unknown option: "--nope"'

    def test_help_is_read_even_when_the_rest_cannot_be(self) -> None:
        """``--help`` wins over an error at the launcher, so a mistyped line can still ask how the
        verb works instead of being told twice that it was mistyped."""
        parsed = parse_installer_arguments(["--nope", "--help"])

        assert parsed.help_wanted is True
        assert parsed.error == 'unknown option: "--nope"'
