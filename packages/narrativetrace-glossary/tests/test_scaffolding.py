# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The translated view's own fixed vocabulary."""

from __future__ import annotations

from narrativetrace_glossary.scaffolding import SUPPORTED_LOCALES, ScaffoldingBundle


def test_english_bundle() -> None:
    bundle = ScaffoldingBundle.for_locale("en")

    assert bundle.locale == "en"
    assert bundle.returns == "returns"
    assert bundle.gaps_heading == "Glossary gaps"


def test_spanish_bundle() -> None:
    bundle = ScaffoldingBundle.for_locale("es")

    assert bundle.locale == "es"
    assert bundle.returns == "devuelve"
    assert bundle.throws == "lanza"
    assert bundle.incomplete == "incompleto"
    assert bundle.gaps_heading == "Vacíos del glosario"


def test_simplified_chinese_bundle() -> None:
    bundle = ScaffoldingBundle.for_locale("zh-CN")

    assert bundle.locale == "zh-CN"
    assert bundle.returns == "返回"
    assert bundle.gaps_heading == "术语表缺口"


def test_unrecognized_locale_falls_back_to_english() -> None:
    bundle = ScaffoldingBundle.for_locale("fr")

    assert bundle.locale == "en"
    assert bundle.returns == "returns"


def test_supported_locales_lists_every_shipped_bundle() -> None:
    assert set(SUPPORTED_LOCALES) == {"en", "es", "zh-CN"}


def test_every_bundle_carries_every_field_non_blank() -> None:
    for locale in SUPPORTED_LOCALES:
        bundle = ScaffoldingBundle.for_locale(locale)
        for field_name in (
            "returns",
            "throws",
            "incomplete",
            "fork",
            "join",
            "tasks",
            "background",
            "gaps_heading",
        ):
            assert getattr(bundle, field_name).strip(), f"{locale}.{field_name} must not be blank"
