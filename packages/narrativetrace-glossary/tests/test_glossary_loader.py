# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Runtime discovery of the committed glossary for translation."""

from __future__ import annotations

from pathlib import Path

import pytest
from narrativetrace_glossary.glossary_loader import load_glossary

from narrativetrace.config import ConfigResolver

_VALID = """{
  "schemaVersion": 1,
  "contexts": {"billing": {"packages": ["acme.billing"]}},
  "terms": []
}"""


def test_no_explicit_config_and_no_default_file_returns_none(tmp_path: Path) -> None:
    resolver = ConfigResolver(start_dir=tmp_path)

    assert load_glossary(resolver, default_dir=tmp_path) is None


def test_no_explicit_config_but_a_glossary_json_in_the_default_dir_loads_it(tmp_path: Path) -> None:
    (tmp_path / "glossary.json").write_text(_VALID, encoding="utf-8")
    resolver = ConfigResolver(start_dir=tmp_path)

    glossary = load_glossary(resolver, default_dir=tmp_path)

    assert glossary is not None
    assert "billing" in glossary.contexts


def test_explicit_env_var_pointing_at_a_real_glossary_loads_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    glossary_dir = tmp_path / "repo"
    glossary_dir.mkdir()
    (glossary_dir / "glossary.json").write_text(_VALID, encoding="utf-8")
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(glossary_dir))
    resolver = ConfigResolver(start_dir=tmp_path)

    glossary = load_glossary(resolver)

    assert glossary is not None


def test_explicit_env_var_pointing_at_a_directory_with_no_glossary_json_fails_fast(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setenv("NARRATIVETRACE_GLOSSARY_DIR", str(empty_dir))
    resolver = ConfigResolver(start_dir=tmp_path)

    with pytest.raises(ValueError, match=r"has no glossary\.json"):
        load_glossary(resolver)


def test_a_malformed_committed_glossary_raises_even_without_explicit_config(tmp_path: Path) -> None:
    (tmp_path / "glossary.json").write_text("{ not json", encoding="utf-8")
    resolver = ConfigResolver(start_dir=tmp_path)

    with pytest.raises(ValueError, match="malformed glossary JSON"):
        load_glossary(resolver, default_dir=tmp_path)


def test_default_resolver_is_constructed_when_none_is_given(tmp_path: Path) -> None:
    assert load_glossary(default_dir=tmp_path) is None
