# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""PyPI presence/absence polling for `poe verify-publication` (`scripts/verify_publication_
registry.py`).

`default_fetch_status`'s real network call is exercised for real by `poe verify-publication`
against the live pypi.org index (see the tool's own report); these tests drive the classification
and backoff-loop logic against an injected fake clock/fetcher, matching the same reasoning
`verify-publication-registry.ts`'s own test suite documents.
"""

from __future__ import annotations

import pytest
from scripts.verify_publication_registry import (
    PollOptions,
    RegistryTarget,
    check_absence_one,
    check_presence_one,
    classify_absence,
    classify_presence,
    poll_presence,
    project_url,
    version_url,
)


class TestUrls:
    def test_project_url_has_no_version_segment(self) -> None:
        assert (
            project_url("https://pypi.org/pypi", "narrativetrace")
            == "https://pypi.org/pypi/narrativetrace/json"
        )

    def test_version_url_includes_the_exact_version(self) -> None:
        assert (
            version_url("https://pypi.org/pypi", "narrativetrace", "0.1.0")
            == "https://pypi.org/pypi/narrativetrace/0.1.0/json"
        )


class TestClassifyPresence:
    def test_200_is_present(self) -> None:
        assert classify_presence(200, project_status=None) == "PRESENT"

    def test_404_with_the_project_itself_absent_is_not_yet_published(self) -> None:
        assert classify_presence(404, project_status=404) == "NOT_YET_PUBLISHED"

    def test_404_with_the_project_existing_is_lagging(self) -> None:
        assert classify_presence(404, project_status=200) == "LAGGING"

    def test_a_server_error_is_missing_regardless_of_project_status(self) -> None:
        assert classify_presence(500, project_status=None) == "MISSING"

    def test_no_response_at_all_is_missing(self) -> None:
        assert classify_presence(0, project_status=None) == "MISSING"

    def test_a_404_with_no_project_status_supplied_raises(self) -> None:
        with pytest.raises(ValueError, match="project_status is required"):
            classify_presence(404, project_status=None)


class TestClassifyAbsence:
    def test_404_is_absent(self) -> None:
        assert classify_absence(404) == "ABSENT"

    def test_200_is_present_a_violation(self) -> None:
        assert classify_absence(200) == "PRESENT"

    def test_a_server_error_is_unknown_never_silently_absent(self) -> None:
        assert classify_absence(500) == "UNKNOWN"


class TestCheckPresenceOne:
    def test_fetches_the_project_url_only_when_the_version_url_404s(self) -> None:
        calls: list[str] = []

        def fetch_status(url: str) -> int:
            calls.append(url)
            return 200 if url.endswith("/json") and "/0.1.0/" not in url else 404

        target = RegistryTarget("narrativetrace", "0.1.0")
        verdict = check_presence_one(target, fetch_status, "https://pypi.org/pypi")

        assert verdict == "LAGGING"
        assert calls == [
            "https://pypi.org/pypi/narrativetrace/0.1.0/json",
            "https://pypi.org/pypi/narrativetrace/json",
        ]

    def test_does_not_fetch_the_project_url_when_the_version_is_present(self) -> None:
        calls: list[str] = []

        def fetch_status(url: str) -> int:
            calls.append(url)
            return 200

        target = RegistryTarget("narrativetrace", "0.1.0")
        verdict = check_presence_one(target, fetch_status, "https://pypi.org/pypi")

        assert verdict == "PRESENT"
        assert len(calls) == 1


class TestCheckAbsenceOne:
    def test_absent_project_reads_absent(self) -> None:
        verdict = check_absence_one(
            "narrativetrace-security-tests", lambda _url: 404, "https://pypi.org/pypi"
        )

        assert verdict == "ABSENT"


class _FakeClock:
    """A controllable stand-in for `time.monotonic` — deadlines are a test input, never real
    wall-clock time (this repository's own convention, applied here the same way
    `verify-publication-registry.ts`'s injectable `now` is)."""

    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds

    def advance(self, seconds: float) -> None:
        self.seconds += seconds


class TestPollPresence:
    def test_returns_immediately_when_every_target_is_already_present(self) -> None:
        sleeps: list[float] = []
        options = PollOptions(fetch_status=lambda _url: 200, sleep=sleeps.append, now=_FakeClock())

        verdicts = poll_presence([RegistryTarget("narrativetrace", "0.1.0")], options)

        assert verdicts == {"narrativetrace": "PRESENT"}
        assert sleeps == []

    def test_stops_once_the_deadline_elapses_even_if_still_pending(self) -> None:
        clock = _FakeClock()

        def fetch_status(_url: str) -> int:
            clock.advance(100)  # every check "costs" time, past the short deadline below
            return 404

        options = PollOptions(
            fetch_status=fetch_status, sleep=lambda _s: None, now=clock, timeout_seconds=10.0
        )

        verdicts = poll_presence([RegistryTarget("narrativetrace-otel", "0.1.0")], options)

        assert verdicts["narrativetrace-otel"] == "NOT_YET_PUBLISHED"

    def test_calls_on_pending_with_the_targets_still_not_present(self) -> None:
        clock = _FakeClock()
        statuses = iter([404, 404, 200])  # present only on the second recheck
        pending_seen: list[list[str]] = []
        options = PollOptions(
            fetch_status=lambda _url: next(statuses, 404),
            sleep=lambda _s: None,
            now=clock,
            timeout_seconds=1000.0,
            initial_backoff_seconds=1.0,
            on_pending=lambda pending: pending_seen.append([t.name for t in pending]),
        )
        # The first two fetch_status calls (version_url, then project_url once it 404s) both read
        # 404, so the initial check reads NOT_YET_PUBLISHED and one retry round is needed before
        # the third call (the recheck's version_url) reads 200.

        verdicts = poll_presence([RegistryTarget("narrativetrace", "0.1.0")], options)

        assert pending_seen  # at least one round reported the target as still pending
        assert verdicts["narrativetrace"] == "PRESENT"

    def test_backoff_doubles_and_is_capped_at_max_interval(self) -> None:
        clock = _FakeClock()
        waits: list[float] = []

        def sleep_and_advance(seconds: float) -> None:
            waits.append(seconds)
            clock.advance(seconds)  # a real sleep would consume this much wall-clock time too

        options = PollOptions(
            fetch_status=lambda _url: 404,
            sleep=sleep_and_advance,
            now=clock,
            timeout_seconds=3.0,
            initial_backoff_seconds=1.0,
            max_interval_seconds=2.0,
        )

        poll_presence([RegistryTarget("narrativetrace-otel", "0.1.0")], options)

        assert waits[0] == 1.0
        assert all(w <= 2.0 for w in waits)
