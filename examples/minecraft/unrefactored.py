# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The unrefactored world: the same behavior hidden behind generic labels."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DataResult:
    a: int
    b: int
    tag: str


@dataclass(frozen=True, slots=True)
class Entity:
    kind: int
    a: int
    b: int
    c: int


class DataProcessor:
    def process(self, a: int, b: int) -> DataResult:
        return DataResult(a, b, "plains")


class StateManager:
    def update(self, type: int, count: int) -> bool:
        return True


class ThingFactory:
    def create(self, type: int) -> int:
        return type


class EntityHandler:
    def execute(self, kind: int, a: int, b: int, c: int) -> Entity:
        return Entity(kind, a, b, c)


class GameManager:
    def __init__(
        self,
        data_processor: DataProcessor,
        state_manager: StateManager,
        thing_factory: ThingFactory,
        entity_handler: EntityHandler,
    ) -> None:
        self._data_processor = data_processor
        self._state_manager = state_manager
        self._thing_factory = thing_factory
        self._entity_handler = entity_handler

    def handle(self, input: str) -> str:
        self._data_processor.process(0, 0)
        self._state_manager.update(1, 4)
        self._state_manager.update(2, 8)
        item = self._thing_factory.create(1)
        self._state_manager.update(item, 1)
        self._entity_handler.execute(1, 10, 64, 20)
        return f"{input} joined the world"
