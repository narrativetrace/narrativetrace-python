# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The OpenAI plugin directory's ``plugin.json`` (shared by ChatGPT and Codex): the versionless
committed text and the packaged text a release ZIP carries, both from the one typed
:class:`~narrativetrace_skills.openai_listing.OpenAiListing`."""

from __future__ import annotations

import json

import pytest
from narrativetrace_skills.catalogue_index import OPENAI_DIRECTORY, SKILLS
from narrativetrace_skills.marketplace import MarketplaceListing, MarketplaceOwner
from narrativetrace_skills.openai_listing import OpenAiListing
from narrativetrace_skills.render.openai_plugin import (
    SCHEMA_URL,
    openai_package_entries,
    render_openai_plugin_json,
)


def _listing(**base_overrides: object) -> OpenAiListing:
    base_fields: dict[str, object] = {
        "name": "narrativetrace-x",
        "owner": MarketplaceOwner(name="NarrativeTrace", url="https://narrativetrace.ai"),
        "description": "The marketplace description.",
        "plugin_description": "The plugin description.",
        "plugin_source": "./.claude",
        "license": "Apache-2.0",
        "homepage": "https://narrativetrace.ai",
        "keywords": ("tracing", "agent-skills"),
    }
    base_fields.update(base_overrides)
    return OpenAiListing(
        base=MarketplaceListing(**base_fields),  # type: ignore[arg-type]
        display_name="NarrativeTrace for X",
        short_description="NarrativeTrace X skills",
        category="Developer Tools",
        capabilities=("Read", "Write"),
        default_prompts=("do the thing", "do the other thing"),
        brand_color="#4A4A4A",
        website_url="https://narrativetrace.ai",
    )


def _interface(rendered: str) -> dict[str, object]:
    return json.loads(rendered)["extensions"]["com.openai"]["interface"]  # type: ignore[no-any-return]


class TestTheCommittedRender:
    def test_is_well_formed_json_ending_in_a_newline(self) -> None:
        rendered = render_openai_plugin_json(_listing())
        assert rendered.endswith("}\n")
        json.loads(rendered)

    def test_maps_the_base_listing_onto_the_manifest_root(self) -> None:
        payload = json.loads(render_openai_plugin_json(_listing()))
        assert payload["$schema"] == SCHEMA_URL
        assert SCHEMA_URL == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        assert payload["name"] == "narrativetrace-x"
        assert payload["description"] == "The plugin description."
        assert payload["author"] == {"name": "NarrativeTrace"}
        assert payload["homepage"] == "https://narrativetrace.ai"
        assert payload["license"] == "Apache-2.0"
        assert payload["keywords"] == ["tracing", "agent-skills"]

    def test_the_manifest_root_carries_exactly_the_mapped_keys(self) -> None:
        payload = json.loads(render_openai_plugin_json(_listing()))
        assert list(payload) == [
            "$schema",
            "name",
            "description",
            "author",
            "homepage",
            "license",
            "keywords",
            "extensions",
        ]

    def test_the_interface_block_carries_exactly_the_listing_fields(self) -> None:
        interface = _interface(render_openai_plugin_json(_listing()))
        assert {key: value for key, value in interface.items() if key != "longDescription"} == {
            "displayName": "NarrativeTrace for X",
            "shortDescription": "NarrativeTrace X skills",
            "developerName": "NarrativeTrace",
            "category": "Developer Tools",
            "capabilities": ["Read", "Write"],
            "defaultPrompt": ["do the thing", "do the other thing"],
            "brandColor": "#4A4A4A",
            "websiteURL": "https://narrativetrace.ai",
            "logo": "./assets/logo.png",
            "composerIcon": "./assets/composer-icon.png",
        }

    def test_the_extension_sits_under_com_openai_interface_only(self) -> None:
        payload = json.loads(render_openai_plugin_json(_listing()))
        assert list(payload["extensions"]) == ["com.openai"]
        assert list(payload["extensions"]["com.openai"]) == ["interface"]

    def test_the_long_description_is_the_plugin_description_plus_the_environment_sentence(
        self,
    ) -> None:
        long_description = _interface(render_openai_plugin_json(_listing()))["longDescription"]
        assert long_description == (
            "The plugin description. It reads what one run actually did, and needs a Python "
            "interpreter, uv, and network access for the first dependency fetch."
        )

    def test_carries_no_version_hooks_apps_or_unruled_keys(self) -> None:
        rendered = render_openai_plugin_json(_listing())
        for absent in (
            '"version"',
            '"hooks"',
            '"apps"',
            '"onboardingSkill"',
            "requires_local_executor",
            '"privacyPolicyURL"',
            '"termsOfServiceURL"',
        ):
            assert absent not in rendered

    def test_renders_byte_identically_every_time(self) -> None:
        listing = _listing()
        assert render_openai_plugin_json(listing) == render_openai_plugin_json(listing)

    def test_escapes_every_character_json_cannot_carry_raw(self) -> None:
        hostile = _listing(
            owner=MarketplaceOwner(name='Narrative"Trace', url="https://narrativetrace.ai"),
            plugin_description='A "quoted" \\ name\twith\na newline and a \x01 control char.',
        )
        payload = json.loads(render_openai_plugin_json(hostile))
        assert payload["author"]["name"] == 'Narrative"Trace'
        assert payload["description"] == (
            'A "quoted" \\ name\twith\na newline and a \x01 control char.'
        )


class TestThePackagedRender:
    def test_inserts_the_version_after_the_name_and_changes_nothing_else(self) -> None:
        committed = json.loads(render_openai_plugin_json(_listing()))
        packaged = json.loads(render_openai_plugin_json(_listing(), "1.2.3"))
        assert list(packaged)[:3] == ["$schema", "name", "version"]
        assert packaged.pop("version") == "1.2.3"
        assert packaged == committed

    def test_the_two_renders_differ_by_exactly_the_version_line(self) -> None:
        committed = render_openai_plugin_json(_listing())
        packaged = render_openai_plugin_json(_listing(), "1.2.3")
        assert packaged.replace('  "version": "1.2.3",\n', "") == committed
        assert packaged != committed

    @pytest.mark.parametrize("version", ["", " ", "\t\n"])
    def test_a_blank_version_is_refused(self, version: str) -> None:
        with pytest.raises(ValueError, match=r"\Aversion must not be blank\Z"):
            render_openai_plugin_json(_listing(), version)

    def test_renders_byte_identically_every_time(self) -> None:
        listing = _listing()
        assert render_openai_plugin_json(listing, "1.2.3") == render_openai_plugin_json(
            listing, "1.2.3"
        )


class TestThePackageLayout:
    """The ZIP's file set, derived from the catalogue -- the list the pack step asserts the built
    archive against, never a glob."""

    def test_lists_the_manifest_every_skill_page_and_the_two_assets_sorted(self) -> None:
        entries = openai_package_entries(SKILLS)
        assert entries == sorted(
            [
                "plugin.json",
                "assets/logo.png",
                "assets/composer-icon.png",
                *(f"skills/{skill.canonical_name}/SKILL.md" for skill in SKILLS),
            ]
        )
        assert len(entries) == len(SKILLS) + 3

    def test_an_empty_skill_list_still_carries_the_manifest_and_the_assets(self) -> None:
        assert openai_package_entries(()) == [
            "assets/composer-icon.png",
            "assets/logo.png",
            "plugin.json",
        ]

    def test_the_asset_entries_are_the_manifests_own_paths_without_the_dot_slash(self) -> None:
        interface = json.loads(render_openai_plugin_json(OPENAI_DIRECTORY))["extensions"][
            "com.openai"
        ]["interface"]
        entries = openai_package_entries(())
        assert interface["logo"].removeprefix("./") in entries
        assert interface["composerIcon"].removeprefix("./") in entries


class TestNonAsciiText:
    def test_survives_a_round_trip_through_the_rendered_json(self) -> None:
        listing = _listing(plugin_description="Zürich — “quoted” 日本語 \U0001f600")
        payload = json.loads(render_openai_plugin_json(listing, "1.2.3"))
        assert payload["description"] == "Zürich — “quoted” 日本語 \U0001f600"
