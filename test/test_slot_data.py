import json
import os
from collections import Counter

from test.general import gen_steps, setup_solo_multiworld
from worlds.AutoWorld import call_all

from .. import Sly2World
from ..data.Constants import LOOT, LOOT_PRICES, TREASURE_PRICES
from ..data.Items import item_dict
from ..Sly2Options import Sly2Options
from . import Sly2TestBase

PASSTHROUGH_OPTIONS = [
  "starting_episode",
  "permissive_yaml",
  "goal",
  "pick_and_mix",
  "keys_in_pool",
  "episode_8_keys",
  "required_keys_episode_8",
  "required_keys_goal",
  "include_tom",
  "include_mega_jump",
  "include_time_rush",
  "coins_minimum",
  "coins_maximum",
  "thiefnet_minimum",
  "thiefnet_maximum",
  "include_vaults",
  "include_pickpocketing",
  "tasksanity",
  "small_guard_loot_chance",
  "large_guard_loot_chance",
  "loot_table_distribution",
  "randomize_loot",
  "dynamic_loot_tables",
  "loot_values",
  "loot_value_minimum",
  "loot_value_maximum",
  "treasure_values",
  "treasure_value_minimum",
  "treasure_value_maximum",
  "bottle_item_bundle_size",
  "bottle_location_bundle_size",
  "bottlesanity",
  "scout_thiefnet",
  "trap_chance",
  "trap_weights",
  "trap_duration",
  "ring_link",
  "thiefnet_icon_theme",
  "thiefnet_text_color",
]

GENERATED_KEYS = [
  "thiefnet_costs",
  "loot_table",
  "loot_prices",
  "treasure_prices",
  "world_version",
]


class TestSlotData(Sly2TestBase):
  options = {"thiefnet_minimum": 100, "thiefnet_maximum": 500}

  def test_keys(self) -> None:
    slot_data = self.world.fill_slot_data()
    for key in PASSTHROUGH_OPTIONS + GENERATED_KEYS + ["death_link"]:
      self.assertIn(key, slot_data)
    for key in self.world.get_options_as_dict():
      self.assertIn(key, Sly2Options.type_hints)

  def test_world_version(self) -> None:
    path = os.path.join(
      os.path.dirname(os.path.dirname(__file__)), "archipelago.json"
    )
    with open(path) as f:
      manifest = json.load(f)
    version = self.world.fill_slot_data()["world_version"]
    self.assertEqual(
      ".".join(str(n) for n in version), manifest["world_version"]
    )

  def test_thiefnet_costs(self) -> None:
    costs = self.world.fill_slot_data()["thiefnet_costs"]
    self.assertEqual(len(costs), 24)
    self.assertEqual(costs, sorted(costs))
    for cost in costs:
      self.assertTrue(100 <= cost <= 500)

  def test_vanilla_loot_and_prices(self) -> None:
    slot_data = self.world.fill_slot_data()
    self.assertEqual(slot_data["loot_table"], LOOT)
    self.assertEqual(slot_data["loot_prices"], LOOT_PRICES)
    self.assertEqual(slot_data["treasure_prices"], TREASURE_PRICES)


class TestRandomizedLoot(Sly2TestBase):
  options = {
    "randomize_loot": True,
    "loot_values": "Shuffled",
    "treasure_values": "Randomized",
    "treasure_value_minimum": 5,
    "treasure_value_maximum": 7,
  }

  def test_loot_table_partitions_locations(self) -> None:
    table = self.world.fill_slot_data()["loot_table"]
    self.assertEqual(set(table), set(LOOT))
    placed = [loc for locs in table.values() for loc in locs]
    expected = [loc for locs in LOOT.values() for loc in locs]
    self.assertEqual(Counter(placed), Counter(expected))
    for loot, locs in table.items():
      self.assertTrue(locs, loot)

  def test_prices(self) -> None:
    slot_data = self.world.fill_slot_data()
    self.assertEqual(
      Counter(slot_data["loot_prices"].values()),
      Counter(LOOT_PRICES.values())
    )
    self.assertEqual(list(slot_data["loot_prices"]), list(LOOT_PRICES))
    self.assertEqual(
      list(slot_data["treasure_prices"]), list(TREASURE_PRICES)
    )
    for price in slot_data["treasure_prices"].values():
      self.assertTrue(5 <= price <= 7)


class TestTrackerPassthrough(Sly2TestBase):
  options = {
    "goal": "Clockwerk_Hunt",
    "keys_in_pool": 14,
    "required_keys_goal": 9,
    "episode_8_keys": "Gradual_sections",
    "required_keys_episode_8": 12,
    "bottle_item_bundle_size": 6,
    "bottle_location_bundle_size": 6,
    "include_pickpocketing": True,
    "randomize_loot": True,
    "tasksanity": True,
    "starting_episode": "A_Tangled_Web",
  }

  def test_regenerates_from_slot_data(self) -> None:
    slot_data = self.world.fill_slot_data()
    multiworld = setup_solo_multiworld(Sly2World, steps=())
    setattr(multiworld, "generation_is_fake", True)
    setattr(multiworld, "re_gen_passthrough", {Sly2World.game: slot_data})
    for step in gen_steps:
      call_all(multiworld, step)
    tracker = multiworld.worlds[1]

    for name in PASSTHROUGH_OPTIONS:
      self.assertEqual(
        getattr(tracker.options, name).value,
        getattr(self.world.options, name).value,
        name
      )
    self.assertEqual(tracker.loot_table, self.world.loot_table)
    self.assertEqual(tracker.thiefnet_costs, self.world.thiefnet_costs)
    self.assertEqual(
      tracker.tracker_world["map_page_locations"],
      self.world.tracker_world["map_page_locations"],
    )
    self.assertEqual(
      {loc.name for loc in multiworld.get_locations(1)},
      {loc.name for loc in self.multiworld.get_locations(self.player)}
    )
    self.assertEqual(
      Counter(item_dict[item.name].category for item in multiworld.itempool),
      Counter(
        item_dict[item.name].category for item in self.multiworld.itempool
      )
    )


OPERATION_SLUGS = [
  "thunder_beak",
  "wet_tiger",
  "high_road",
  "canada_games",
  "carmelitas_gunner",
]


class TestTrackerMapDimitriGoal(Sly2TestBase):
  options = {"goal": "Dimitri", "tasksanity": True}

  def test_only_goal_operation_uses_goal_variant(self) -> None:
    pages = self.world.tracker_world["map_page_locations"]
    self.assertIn("locations/operations/thunder_beak_goal.json", pages)
    self.assertNotIn("locations/operations/thunder_beak_normal.json", pages)
    for slug in OPERATION_SLUGS[1:]:
      self.assertIn(f"locations/operations/{slug}_normal.json", pages)
      self.assertNotIn(f"locations/operations/{slug}_goal.json", pages)


class TestTrackerMapClockLaGoal(Sly2TestBase):
  options = {"goal": "ClockLa"}

  def test_only_anatomy_operation_uses_goal_variant(self) -> None:
    pages = self.world.tracker_world["map_page_locations"]
    self.assertIn("locations/operations/carmelitas_gunner_goal.json", pages)
    for slug in OPERATION_SLUGS[:-1]:
      self.assertIn(f"locations/operations/{slug}_normal.json", pages)
      self.assertNotIn(f"locations/operations/{slug}_goal.json", pages)


class TestTrackerMapNonBossGoal(Sly2TestBase):
  options = {"goal": "All_Bosses"}

  def test_all_operations_use_normal_variant(self) -> None:
    pages = self.world.tracker_world["map_page_locations"]
    for slug in OPERATION_SLUGS:
      self.assertIn(f"locations/operations/{slug}_normal.json", pages)
      self.assertNotIn(f"locations/operations/{slug}_goal.json", pages)
