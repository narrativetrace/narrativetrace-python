# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""What ``narrativetrace feedback`` was asked to do, read off a command line and nothing else.

Every flag decision is a pure function, the same shape ``parse_installer_arguments`` has, so the
verb itself is a handful of lines over the tooling library. A bad flag is DATA, never an exception,
and the FIRST problem is the one reported — naming a later flag would name one nobody has read yet.
"""

from __future__ import annotations

import pytest

from narrativetrace.doctor.feedback_cli import (
    CHANNELS,
    FeedbackArguments,
    parse_feedback_arguments,
)

_REQUIRED = (
    "--category",
    "doctor",
    "--step",
    "trap.redaction-proof",
    "--did",
    "ran the doctor",
    "--happened",
    "it failed",
    "--expected",
    "it to pass",
)


def _parsed(*argv: str) -> FeedbackArguments:
    return parse_feedback_arguments(["draft", *_REQUIRED, *argv])


def _without(flag: str) -> list[str]:
    """The mandatory flags with one flag AND its value removed."""
    argv = list(_REQUIRED)
    index = argv.index(flag)
    del argv[index : index + 2]
    return argv


class TestTheChannel:
    def test_the_three_channels_are_the_ones_the_skill_offers_in_order(self) -> None:
        assert CHANNELS == ("draft", "url", "gh")

    @pytest.mark.parametrize("channel", CHANNELS)
    def test_each_channel_is_read_off_the_first_argument(self, channel: str) -> None:
        parsed = parse_feedback_arguments([channel, *_REQUIRED])

        assert parsed.channel == channel
        assert parsed.error is None

    def test_a_missing_channel_says_which_three_there_are(self) -> None:
        parsed = parse_feedback_arguments(list(_REQUIRED))

        assert parsed.error == "feedback needs a channel: draft, url, gh"

    def test_an_unknown_channel_is_named_back(self) -> None:
        parsed = parse_feedback_arguments(["send", *_REQUIRED])

        assert parsed.error == 'unknown feedback channel: "send"'


class TestTheMandatoryFields:
    @pytest.mark.parametrize("flag", ["--step", "--did", "--happened", "--expected"])
    def test_a_missing_field_names_the_flag_that_was_forgotten(self, flag: str) -> None:
        """Checked here rather than left to the library's constructor, so a person who forgets one
        is told which flag they forgot instead of reading a message about a blank field."""
        parsed = parse_feedback_arguments(["draft", *_without(flag)])

        assert parsed.error is not None
        assert parsed.error.startswith(f"{flag} is required")

    def test_a_missing_category_names_the_four_it_could_be(self) -> None:
        parsed = parse_feedback_arguments(["draft", *_without("--category")])

        assert parsed.error == "--category needs a value: prompt, skill, doctor or library"

    def test_an_unknown_category_is_refused_by_the_librarys_own_words(self) -> None:
        parsed = parse_feedback_arguments(["draft", "--category", "doctr", *_without("--category")])

        assert parsed.error is not None
        assert 'unknown category "doctr"' in parsed.error

    def test_the_first_unreadable_flag_is_the_one_reported(self) -> None:
        """Naming a later flag would name one nobody has read yet."""
        parsed = parse_feedback_arguments(["draft", "--nope", "x", "--also-nope", "y"])

        assert parsed.error == 'unknown option: "--nope"'

    def test_a_whole_line_is_read_before_it_is_validated(self) -> None:
        """So an unreadable FLAG is reported ahead of an unusable VALUE, whatever their order on
        the line: the pass records the first problem it meets, and the mandatory-field and category
        checks only run once the line has been read. Fixing what cannot be read first is also the
        order a person works in."""
        parsed = parse_feedback_arguments(["draft", "--category", "doctr", "--step", ""])

        assert parsed.error == "--step needs a value"


class TestTheOptionalFields:
    def test_the_language_defaults_to_english_and_can_be_any_tag(self) -> None:
        assert _parsed().language == "en"
        assert _parsed("--language", "pt-BR").language == "pt-BR"

    def test_the_agent_names_itself_or_stays_unknown(self) -> None:
        assert (_parsed().agent_product, _parsed().agent_model) == ("", "")

        named = _parsed("--agent-product", "example-cli", "--agent-model", "example-model")

        assert (named.agent_product, named.agent_model) == ("example-cli", "example-model")

    def test_a_named_trace_is_a_path_suffix(self) -> None:
        assert _parsed("--trace", "A/first.nt").trace == "A/first.nt"

    def test_json_is_off_until_it_is_asked_for(self) -> None:
        assert _parsed().as_json is False
        assert _parsed("--json").as_json is True


class TestHowAFlagMayBeWritten:
    def test_a_value_follows_the_flag_or_an_equals_sign(self) -> None:
        spaced = _parsed("--language", "es")
        joined = _parsed("--language=es")

        assert spaced.language == joined.language == "es"

    def test_a_value_may_itself_contain_an_equals_sign(self) -> None:
        """``--install`` is not a flag, but ``--step=a=b`` is a step somebody could type, and
        partitioning on the FIRST equals sign is what keeps it whole."""
        assert _parsed("--step=a=b").step == "a=b"

    def test_a_flag_with_no_value_after_it_says_so(self) -> None:
        parsed = parse_feedback_arguments(["draft", *_REQUIRED, "--language"])

        assert parsed.error == "--language needs a value"

    def test_an_unknown_option_is_named_back_verbatim(self) -> None:
        parsed = parse_feedback_arguments(["draft", *_REQUIRED, "--approval", "yes"])

        assert parsed.error == 'unknown option: "--approval"'

    def test_help_short_circuits_every_other_check(self) -> None:
        """Asking for the usage must work before the flags are right — that is when somebody asks
        for it."""
        parsed = parse_feedback_arguments(["--help"])

        assert parsed.help_wanted is True
        assert parsed.error is None

    def test_the_short_help_flag_works_too(self) -> None:
        assert parse_feedback_arguments(["-h"]).help_wanted is True

    def test_a_command_line_is_a_sequence_never_none(self) -> None:
        with pytest.raises(TypeError, match=r"never None"):
            parse_feedback_arguments(None)  # type: ignore[arg-type]
