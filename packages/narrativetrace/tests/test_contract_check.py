# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""`scripts/contract_check.py`: version resolution (`resolve_published_version`) and the
`--with` argument list it builds for the nightly `uv run --project contract-probe` invocation.
The real subprocess/network path is exercised by hand (documentation/contract-gate.md) and by the
proof in the docs-vs-published-gate design note's own record -- these tests cover the pure,
offline decision logic around it.
"""

from __future__ import annotations

import pytest
from scripts import contract_check
from scripts.contract_check import (
    UsageError,
    _publishable_packages,
    _with_arguments,
    resolve_published_version,
)


def test_resolve_published_version_prefers_explicit() -> None:
    version, source = resolve_published_version("9.9.9")
    assert version == "9.9.9"
    assert source == "explicit version argument"


def test_resolve_published_version_falls_back_through_tag_then_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contract_check, "_git_tags", lambda: [])
    monkeypatch.setattr(contract_check, "fetch_latest_version", lambda name: "1.2.3")
    version, source = resolve_published_version(None)
    assert version == "1.2.3"
    assert "PyPI JSON latest" in source


def test_resolve_published_version_prefers_tag_over_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contract_check, "_git_tags", lambda: ["v2.0.0", "v1.0.0"])

    def _must_not_be_called(name: str) -> str | None:
        pytest.fail("must not be called")

    monkeypatch.setattr(contract_check, "fetch_latest_version", _must_not_be_called)
    version, source = resolve_published_version(None)
    assert version == "2.0.0"
    assert "v* tag" in source


def test_resolve_published_version_raises_when_nothing_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contract_check, "_git_tags", lambda: [])
    monkeypatch.setattr(contract_check, "fetch_latest_version", lambda name: None)
    with pytest.raises(UsageError):
        resolve_published_version(None)


def test_publishable_packages_excludes_the_never_publish_package() -> None:
    names = {p.name for p in _publishable_packages()}
    assert "narrativetrace" in names
    assert "narrativetrace-security-tests" not in names


def test_with_arguments_pins_every_publishable_package_at_the_given_version() -> None:
    args = _with_arguments("1.2.3")
    assert args.count("--with") == len(_publishable_packages())
    assert "narrativetrace==1.2.3" in args
    assert "narrativetrace-security-tests==1.2.3" not in args
