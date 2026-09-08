# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""The refactored world: domain-rich names, so the trace reads as the story it is."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Item(Enum):
    OAK_LOG = "oak_log"
    COBBLESTONE = "cobblestone"
    WOODEN_PICKAXE = "wooden_pickaxe"


class Recipe(Enum):
    WOODEN_PICKAXE = Item.WOODEN_PICKAXE

    @property
    def result(self) -> Item:
        return self.value


class CreatureType(Enum):
    ZOMBIE = "zombie"


@dataclass(frozen=True, slots=True)
class Chunk:
    x: int
    z: int
    biome: str


@dataclass(frozen=True, slots=True)
class Creature:
    type: CreatureType
    x: int
    y: int
    z: int


class WorldGenerator:
    def generate_chunk(self, x: int, z: int) -> Chunk:
        return Chunk(x, z, "plains")


class PlayerInventory:
    def add_item(self, item: Item, quantity: int) -> bool:
        return True


class CraftingTable:
    def craft(self, recipe: Recipe) -> Item:
        return recipe.result


class CreatureSpawner:
    def spawn_hostile(self, type: CreatureType, x: int, y: int, z: int) -> Creature:
        return Creature(type, x, y, z)


class WorldServer:
    def __init__(
        self,
        world_generator: WorldGenerator,
        inventory: PlayerInventory,
        crafting_table: CraftingTable,
        creature_spawner: CreatureSpawner,
    ) -> None:
        self._world_generator = world_generator
        self._inventory = inventory
        self._crafting_table = crafting_table
        self._creature_spawner = creature_spawner

    def player_joined(self, player_name: str) -> str:
        self._world_generator.generate_chunk(0, 0)
        self._inventory.add_item(Item.OAK_LOG, 4)
        self._inventory.add_item(Item.COBBLESTONE, 8)
        tool = self._crafting_table.craft(Recipe.WOODEN_PICKAXE)
        self._inventory.add_item(tool, 1)
        self._creature_spawner.spawn_hostile(CreatureType.ZOMBIE, 10, 64, 20)
        return f"{player_name} joined the world"
