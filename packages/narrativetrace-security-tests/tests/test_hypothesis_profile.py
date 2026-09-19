# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Release rule 2 fix (2026-09-17 nightly finding F1b): `HYPOTHESIS_PROFILE` used to be read
nowhere in this repository, so the nightly's `HYPOTHESIS_PROFILE=fuzz` was a complete no-op --
indistinguishable from working. `conftest.py` in this directory now registers "fuzz" as a real
profile and loads whatever name the variable names, opt-in, when it is set. This file pins two
things: the profile the nightly names is real (not aspirational), and an unregistered name fails
loudly rather than being silently ignored -- the property that makes the variable load-bearing.
"""

from __future__ import annotations

import pytest
from hypothesis import settings
from hypothesis.errors import InvalidArgument


class TestFuzzProfileIsRegistered:
    def test_the_fuzz_profile_the_nightly_names_is_actually_registered(self) -> None:
        # get_profile looks the name up without switching the active profile -- this must not
        # leak into later tests in the same session, unlike load_profile.
        profile = settings.get_profile("fuzz")

        assert profile.deadline is None


class TestAnUnregisteredProfileNameFailsLoudly:
    def test_loading_an_unknown_profile_name_raises_instead_of_being_ignored(self) -> None:
        default_before = settings.default
        assert default_before is not None
        deadline_before = default_before.deadline

        with pytest.raises(InvalidArgument):
            settings.load_profile("hypothesis-profile-that-does-not-exist-2026-09-17")

        # A failed load must not have silently changed the settings every other test relies on.
        default_after = settings.default
        assert default_after is not None
        assert default_after.deadline == deadline_before
