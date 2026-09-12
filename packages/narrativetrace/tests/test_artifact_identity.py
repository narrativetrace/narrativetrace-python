# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Tests for :mod:`narrativetrace.output.artifact_identity` — the cross-platform per-invocation
naming scheme (mirrors Java's ``ArtifactIdentityTest``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from narrativetrace.output.artifact_identity import ArtifactIdentity
from narrativetrace.output.paths import diagram_file_for, structural_file, trace_artifact


class TestOrdinaryMethod:
    def test_an_ordinary_test_method_keeps_its_undecorated_slug(self) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "customerPlacesOrder")
        assert identity.file_slug() == "customer_places_order"

    def test_is_invocation_is_false_for_an_ordinary_method(self) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "customerPlacesOrder")
        assert identity.is_invocation is False


class TestInvocationNaming:
    def test_invocation_slug_pads_the_index_to_three_digits(self) -> None:
        identity = ArtifactIdentity.of_invocation(
            "CatalogTest", "equipmentCanBeFound", 2, "find TENT"
        )
        assert identity.file_slug() == "equipment_can_be_found-002-find_tent"

    def test_a_label_that_slugs_to_nothing_is_dropped_leaving_only_the_index(self) -> None:
        identity = ArtifactIdentity.of_invocation("CatalogTest", "equipmentCanBeFound", 2, "!!!")
        assert identity.file_slug() == "equipment_can_be_found-002"

    def test_an_empty_label_behaves_like_a_dropped_one(self) -> None:
        identity = ArtifactIdentity.of_invocation("CatalogTest", "equipmentCanBeFound", 2, "")
        assert identity.file_slug() == "equipment_can_be_found-002"

    def test_indices_beyond_three_digits_are_not_re_padded(self) -> None:
        identity = ArtifactIdentity.of_invocation("CatalogTest", "findsIt", 1234, "case")
        assert identity.file_slug() == "finds_it-1234-case"

    def test_display_names_differing_only_in_path_unsafe_characters_still_get_separate_files(
        self,
    ) -> None:
        a = ArtifactIdentity.of_invocation("CatalogTest", "finds", 1, "find/TENT")
        b = ArtifactIdentity.of_invocation("CatalogTest", "finds", 2, "find TENT")
        assert a.file_slug() != b.file_slug()

    def test_an_ordinary_method_can_never_collide_with_an_invocation_artifact(self) -> None:
        ordinary = ArtifactIdentity.of_method("CatalogTest", "finds")
        invocation = ArtifactIdentity.of_invocation("CatalogTest", "finds", 1, "")
        assert ordinary.file_slug() != invocation.file_slug()
        assert "-" not in ordinary.file_slug()


class TestValidation:
    def test_negative_invocation_index_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            ArtifactIdentity("CatalogTest", "finds", -1, "")

    def test_of_invocation_requires_a_one_based_index(self) -> None:
        with pytest.raises(ValueError, match="1-based"):
            ArtifactIdentity.of_invocation("CatalogTest", "finds", 0, "")


class TestStructuralScenario:
    def test_invocation_is_titled_by_method_and_index_never_the_display_name(self) -> None:
        identity = ArtifactIdentity.of_invocation(
            "CatalogTest", "equipmentCanBeFound", 2, "find TENT"
        )
        title = identity.structural_scenario("find TENT")
        assert title == "Equipment can be found #2"
        assert "TENT" not in title

    def test_an_ordinary_method_is_titled_by_its_display_name(self) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "customerPlacesOrder")
        assert identity.structural_scenario("Customer places a large order") == (
            "Customer places a large order"
        )

    def test_a_none_display_name_falls_back_to_the_humanized_bare_method_name(self) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "customerPlacesOrder")
        assert identity.structural_scenario(None) == "Customer places order"

    def test_a_display_name_equal_to_the_method_name_is_treated_as_absent(self) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "equipmentCanBeFound[KAYAK]")
        assert (
            identity.structural_scenario("equipmentCanBeFound[KAYAK]") == "Equipment can be found"
        )

    def test_a_genuine_display_name_containing_a_literal_bracket_is_not_mistaken_for_a_label(
        self,
    ) -> None:
        identity = ArtifactIdentity.of_method("CatalogTest", "findsIt")
        assert identity.structural_scenario("finds it [fast]") == "finds it [fast]"


class TestEveryArtifactOfOneInvocationSharesItsName:
    def test_trace_diagram_and_structural_paths_share_the_same_stem(self, tmp_path: Path) -> None:
        identity = ArtifactIdentity.of_invocation("CatalogTest", "finds", 2, "tent")
        slug = identity.file_slug()
        trace = trace_artifact(tmp_path, identity.test_class_name, slug, ".md")
        diagram = diagram_file_for(tmp_path, identity.test_class_name, slug)
        structural = structural_file(tmp_path, identity.test_class_name, slug)
        assert trace.stem == diagram.stem == structural.stem == slug
