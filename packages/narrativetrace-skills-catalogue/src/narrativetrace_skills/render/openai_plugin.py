# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Renders ``plugin.json`` for the OpenAI plugin directory (shared by ChatGPT and Codex): the
versionless text that is committed BUILD OUTPUT (pinned by ``scripts/skills_render.py``'s drift
check) and the packaged text a release ZIP carries. Both go through one builder, so the two differ
only by the ``"version"`` key.

Field names and the manifest shape follow the vendor's plugin schema
(``https://agent-plugins.org/schemas/1.0.0/plugin.schema.json``) and its
``extensions.com.openai.interface`` listing fields. Every key this repository does not use is
left out: no ``hooks`` or ``apps`` (the plugin is skills-only), no ``onboardingSkill``, no
``requires_local_executor`` (the desktop-only declaration waits on a cloud trial) and no
``privacyPolicyURL``/``termsOfServiceURL`` (narrativetrace.ai carries neither page yet).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from narrativetrace_skills.openai_listing import OpenAiListing
from narrativetrace_skills.skill import Skill

SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"

LOGO_PATH = "./assets/logo.png"
COMPOSER_ICON_PATH = "./assets/composer-icon.png"

# Appended to the plugin description for the directory's longDescription: states the environment
# a skills-only plugin needs, and bounds the claim to what a run actually showed -- never more,
# the rule narrativetrace-verify and narrativetrace-explain hold their own reports to.
_ENVIRONMENT_SENTENCE = (
    "It reads what one run actually did, and needs a Python interpreter, uv, and network "
    "access for the first dependency fetch."
)


def render_openai_plugin_json(listing: OpenAiListing, version: str | None = None) -> str:
    """The committed, versionless text (``version`` omitted), or the packaged text with the release
    ``version`` inserted after ``name``. A blank ``version`` raises ``ValueError``."""
    if version is not None and not version.strip():
        raise ValueError("version must not be blank")
    base = listing.base
    payload: dict[str, Any] = {"$schema": SCHEMA_URL, "name": base.name}
    if version is not None:
        payload["version"] = version
    payload.update(
        {
            "description": base.plugin_description,
            "author": {"name": base.owner.name},
            "homepage": base.homepage,
            "license": base.license,
            "keywords": list(base.keywords),
            "extensions": {"com.openai": {"interface": _interface(listing)}},
        }
    )
    return f"{json.dumps(payload, indent=2)}\n"


def _interface(listing: OpenAiListing) -> dict[str, Any]:
    return {
        "displayName": listing.display_name,
        "shortDescription": listing.short_description,
        "longDescription": f"{listing.base.plugin_description} {_ENVIRONMENT_SENTENCE}",
        "developerName": listing.base.owner.name,
        "category": listing.category,
        "capabilities": list(listing.capabilities),
        "defaultPrompt": list(listing.default_prompts),
        "brandColor": listing.brand_color,
        "websiteURL": listing.website_url,
        "logo": LOGO_PATH,
        "composerIcon": COMPOSER_ICON_PATH,
    }


def openai_package_entries(skills: Iterable[Skill]) -> list[str]:
    """The release ZIP's file set, sorted: ``plugin.json``, one ``skills/<name>/SKILL.md`` per
    skill and the two listing assets. ``scripts/openai_plugin_pack.py`` asserts the built archive's
    entries EQUAL this list -- derived from the catalogue, never a glob -- so a skill added to the
    catalogue without a packaging change fails the gate instead of shipping an incomplete ZIP."""
    entries = [
        "plugin.json",
        LOGO_PATH.removeprefix("./"),
        COMPOSER_ICON_PATH.removeprefix("./"),
        *(f"skills/{skill.canonical_name}/SKILL.md" for skill in skills),
    ]
    return sorted(entries)
