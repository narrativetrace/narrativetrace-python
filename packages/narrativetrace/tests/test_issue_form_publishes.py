# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The issue form must still be a valid issue form in the PUBLIC snapshot, which is not the file
this repository commits.

``scripts/publish-public.sh`` stamps a four-line ``#`` licence header onto every staged ``*.yml``,
and ``.github/ISSUE_TEMPLATE/narrativetrace-report.yml`` is a ``*.yml``. The form the pre-filled URL
points at is therefore the stamped one, and a form the host cannot parse opens as "we had trouble
loading your template" — with no failure anywhere on our side, because the URL is still well formed
and the parameters are still correct.

The STRUCTURAL half of the form's contract lives here rather than beside the URL builder because
``narrativetrace-tooling`` declares zero dependencies and may not have a YAML parser:
``tests/feedback/test_issue_form_fields.py`` reads the form as text and says exactly that.
``pyyaml`` is a workspace dev dependency, so this is the package that can answer it.

**@llmNote** The header lines are EXTRACTED from the real script, never retyped, for the same reason
``test_publish_public.py`` extracts its patterns: a hand-copied duplicate of what gates a publish is
a test that drifts from the thing it is about.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml


def _repo_root() -> Path:
    """The workspace root, found by walking up rather than by counting directories (mutmut runs
    this suite one level deeper, from its own ``mutants/`` copy)."""
    for candidate in Path(__file__).resolve().parents:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    raise RuntimeError(f"no uv workspace root above {__file__}")


REPO_ROOT = _repo_root()

FORM_PATH = REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "narrativetrace-report.yml"
"""THE declared input of this module: one named file, read as a whole."""

SCRIPT = REPO_ROOT / "scripts" / "publish-public.sh"
# The publish script is private machinery that `.publishignore` strips, so a `--verify` run of a
# real publish builds the staged snapshot where it legitimately does not exist. Skip there rather
# than failing collection, the same way `test_publish_public.py` does.
if not SCRIPT.is_file():
    pytest.skip(
        f"{SCRIPT} not present (private publish machinery, stripped from this snapshot)",
        allow_module_level=True,
    )

_SCRIPT_TEXT = SCRIPT.read_text(encoding="utf-8")


def _header_value(name: str) -> str:
    """One ``HEADER_*`` assignment's value, read out of the real script."""
    match = re.search(rf'^{name}="([^"]*)"$', _SCRIPT_TEXT, re.MULTILINE)
    assert match, f"{name} not found in {SCRIPT} — the stamping step has been reshaped"
    return match.group(1)


def _published_header() -> str:
    """The four ``#`` lines the publish step prepends to a staged ``*.yml``.

    ``HEADER_COPYRIGHT`` interpolates a shell variable for the year range, which no reader of this
    file can resolve — the YEAR is irrelevant to whether YAML still parses, so the line is kept and
    the interpolation left as the literal text it is.
    """
    lines = (
        _header_value("HEADER_SPDX"),
        _header_value("HEADER_TERMS_1"),
        _header_value("HEADER_TERMS_2"),
        _header_value("HEADER_COPYRIGHT"),
    )
    return "".join(f"# {line}\n" for line in lines)


def _parsed(text: str) -> dict[str, Any]:
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict), "an issue form is a YAML mapping"
    return loaded


def _field_ids(form: dict[str, Any]) -> list[str]:
    return [block["id"] for block in form["body"] if "id" in block]


class TestTheFormAsCommitted:
    def test_it_is_valid_yaml_with_the_keys_the_host_requires(self) -> None:
        form = _parsed(FORM_PATH.read_text(encoding="utf-8"))

        assert form["name"]
        assert form["description"]
        assert form["labels"] == ["from-agent"]
        assert isinstance(form["body"], list)

    def test_every_field_id_the_url_pre_fills_is_declared_exactly_once(self) -> None:
        """Structural, where the text-level check in the tooling package can only count lines: a
        duplicated id is a form the host rejects outright, and two boxes the URL cannot tell
        apart."""
        ids = _field_ids(_parsed(FORM_PATH.read_text(encoding="utf-8")))

        assert len(ids) == len(set(ids))
        assert set(ids) >= {
            "category",
            "runtime",
            "install",
            "step",
            "did",
            "happened",
            "expected",
            "language",
            "agent",
            "report",
            "reviewed",
        }

    def test_the_category_dropdown_offers_the_four_the_verb_accepts(self) -> None:
        form = _parsed(FORM_PATH.read_text(encoding="utf-8"))
        dropdown = next(block for block in form["body"] if block.get("id") == "category")

        assert dropdown["type"] == "dropdown"
        assert dropdown["attributes"]["options"] == ["prompt", "skill", "doctor", "library"]
        assert dropdown["validations"]["required"] is True

    def test_the_attestation_is_a_required_checkbox(self) -> None:
        form = _parsed(FORM_PATH.read_text(encoding="utf-8"))
        checkboxes = next(block for block in form["body"] if block.get("id") == "reviewed")

        assert checkboxes["type"] == "checkboxes"
        assert checkboxes["attributes"]["options"][0]["required"] is True

    def test_the_agent_field_is_free_text_rather_than_a_vendor_dropdown(self) -> None:
        """The set of agent products is open, a dropdown goes stale, and every vendor name in a
        shipped file is a publish-gate exception reviewed forever. Free text needs none."""
        form = _parsed(FORM_PATH.read_text(encoding="utf-8"))
        agent = next(block for block in form["body"] if block.get("id") == "agent")

        assert agent["type"] == "input"
        assert "options" not in agent["attributes"]


class TestTheFormAsPublished:
    def test_the_publish_step_really_does_stamp_a_yml(self) -> None:
        """The premise. If ``*.yml`` ever leaves the stamping step's file list this test becomes
        the one that says so, instead of quietly asserting nothing."""
        stamped = re.search(r"-o -name '\*\.yml' -o -name '\*\.yaml'", _SCRIPT_TEXT)

        assert stamped, "the stamping step no longer names *.yml — re-read it before trusting this"
        assert '*.py|*.sh|*.yml|*.yaml) c="#"' in _SCRIPT_TEXT

    def test_the_stamped_form_still_parses_with_every_field_intact(self) -> None:
        committed = FORM_PATH.read_text(encoding="utf-8")

        published = _parsed(_published_header() + committed)

        assert published == _parsed(committed), (
            "the licence header is a YAML comment and must change nothing about the form"
        )
        assert _field_ids(published) == _field_ids(_parsed(committed))

    def test_the_header_this_test_prepends_is_the_scripts_own(self) -> None:
        """The probe of the extraction: four lines, each a comment, carrying the licence the
        snapshot ships under. A regex that stopped matching would otherwise make the test above
        prepend nothing and pass."""
        header = _published_header()

        assert header.count("\n") == 4
        assert all(line.startswith("# ") for line in header.splitlines())
        assert "SPDX-License-Identifier: BUSL-1.1" in header

    def test_ordinary_yaml_above_the_form_would_change_it(self) -> None:
        """The probe of the assertion above: if prepending ANYTHING changed nothing, then "the
        licence header changed nothing" would also say nothing. A comment is invisible to the
        parser; a key is not."""
        committed = FORM_PATH.read_text(encoding="utf-8")

        perturbed = _parsed("a_key_the_form_does_not_have: anything\n" + committed)

        assert perturbed != _parsed(committed)
        assert "a_key_the_form_does_not_have" in perturbed

    def test_and_a_malformed_line_above_it_would_be_refused_outright(self) -> None:
        """The other half: the parser this test trusts really does complain. Otherwise "it still
        parses" would be a property of the parser rather than of the form."""
        with pytest.raises(yaml.YAMLError):
            _parsed("\tname: indented with a tab\n" + FORM_PATH.read_text(encoding="utf-8"))
