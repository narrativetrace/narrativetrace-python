# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The translated view's own fixed vocabulary — never taught by a project's glossary.

``ScaffoldingBundle``. INTENT: "returns", "throws", "fork" and friends are chrome the
renderer itself emits around glossed identifiers, not domain vocabulary any project curates — a
committed ``glossary.json`` has no say over them, and they exist for exactly the locales this
runtime ships translated views for.

An unrecognized locale falls back to English deterministically — never the host process's own
locale, which would make the same render produce different bytes on different machines.
"""

from __future__ import annotations

from dataclasses import dataclass

_EN: dict[str, str] = {
    "returns": "returns",
    "throws": "throws",
    "incomplete": "incomplete",
    "fork": "fork",
    "join": "join",
    "tasks": "tasks",
    "background": "In the background:",
    "gapsHeading": "Glossary gaps",
}

_ES: dict[str, str] = {
    "returns": "devuelve",
    "throws": "lanza",
    "incomplete": "incompleto",
    "fork": "bifurcación",
    "join": "unión",
    "tasks": "tareas",
    "background": "En segundo plano:",
    "gapsHeading": "Vacíos del glosario",
}

_ZH_CN: dict[str, str] = {
    "returns": "返回",
    "throws": "抛出",
    "incomplete": "未完成",
    "fork": "分叉",
    "join": "汇合",
    "tasks": "任务",
    "background": "在后台:",
    "gapsHeading": "术语表缺口",
}

_BUNDLES: dict[str, dict[str, str]] = {"en": _EN, "es": _ES, "zh-CN": _ZH_CN}

SUPPORTED_LOCALES: tuple[str, ...] = tuple(_BUNDLES)
"""Locales this runtime ships scaffolding chrome for (English plus the shipped translations)."""


@dataclass(frozen=True, slots=True)
class ScaffoldingBundle:
    """One locale's fixed renderer vocabulary."""

    locale: str
    returns: str
    throws: str
    incomplete: str
    fork: str
    join: str
    tasks: str
    background: str
    gaps_heading: str

    @classmethod
    def for_locale(cls, locale: str) -> ScaffoldingBundle:
        """Looks up the bundle for ``locale``, falling back to English when unrecognized."""
        words = _BUNDLES.get(locale, _EN)
        resolved = locale if locale in _BUNDLES else "en"
        return cls(
            resolved,
            words["returns"],
            words["throws"],
            words["incomplete"],
            words["fork"],
            words["join"],
            words["tasks"],
            words["background"],
            words["gapsHeading"],
        )
