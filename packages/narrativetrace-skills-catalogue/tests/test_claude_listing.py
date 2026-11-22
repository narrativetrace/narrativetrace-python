# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The Anthropic directory's listing fields, beside the vendor-neutral listing they extend."""

from __future__ import annotations

from narrativetrace_skills.catalogue_index import CLAUDE_DIRECTORY, MARKETPLACE, OPENAI_DIRECTORY


class TestClaudeDirectory:
    def test_draws_from_the_same_marketplace_listing_as_every_other_registry(self) -> None:
        assert CLAUDE_DIRECTORY.base is MARKETPLACE

    def test_uses_the_display_name_the_openai_listing_uses(self) -> None:
        assert CLAUDE_DIRECTORY.display_name == "NarrativeTrace for Python"
        assert CLAUDE_DIRECTORY.display_name == OPENAI_DIRECTORY.display_name

    def test_points_support_privacy_and_documentation_at_their_pages(self) -> None:
        assert (
            CLAUDE_DIRECTORY.support_url
            == "https://github.com/narrativetrace/narrativetrace-python/issues"
        )
        assert CLAUDE_DIRECTORY.privacy_policy_url == "https://narrativetrace.ai/privacy"
        assert CLAUDE_DIRECTORY.documentation_url == (
            "https://github.com/narrativetrace/narrativetrace-python/tree/main/documentation"
        )
