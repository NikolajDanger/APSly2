from collections import Counter

from ..data.Items import (
  CLOCKWERK_ADDITIONAL,
  CLOCKWERK_CORE,
  CLOCKWERK_REPEATABLE,
  CLOCKWERK_SILLY,
  Trap,
  ordered_group,
)
from . import Sly2TestBase

EP8 = "Progressive Anatomy for Disaster"


class PoolTestBase(Sly2TestBase):
  def pool_names(self) -> Counter:
    return Counter(item.name for item in self.multiworld.itempool)

  def assert_pool_fills_locations(self) -> None:
    unfilled = len(self.multiworld.get_unfilled_locations(self.player))
    self.assertEqual(len(self.multiworld.itempool), unfilled)


class TestDefaultPool(PoolTestBase):
  options = {"starting_episode": "Jailbreak"}

  def test_pool_size(self) -> None:
    self.assert_pool_fills_locations()

  def test_starting_episode_precollected(self) -> None:
    precollected = [
      item.name for item in self.multiworld.precollected_items[self.player]
    ]
    self.assertEqual(precollected, ["Progressive Jailbreak"])
    self.assertEqual(self.pool_names()["Progressive Jailbreak"], 2)
    self.assertEqual(self.pool_names()["Progressive The Black Chateau"], 4)

  def test_default_episode_8(self) -> None:
    self.assertEqual(self.pool_names()[EP8], 3)
    self.assertEqual(
      sum(self.pool_names()[n] for n in CLOCKWERK_CORE),
      self.world.options.keys_in_pool.value
    )

  def test_optional_powerups_absent(self) -> None:
    names = self.pool_names()
    for name in ["TOM", "Mega Jump", "Time Rush"]:
      self.assertNotIn(name, names)
    self.assertIn("Paraglider", names)


class TestOptionalPowerups(PoolTestBase):
  options = {
    "include_tom": True,
    "include_mega_jump": True,
    "include_time_rush": True,
  }

  def test_present(self) -> None:
    names = self.pool_names()
    for name in ["TOM", "Mega Jump", "Time Rush"]:
      self.assertEqual(names[name], 1)


class TestEpisode8KeysOff(PoolTestBase):
  options = {"episode_8_keys": "Off"}

  def test_no_parts_four_episode_items(self) -> None:
    names = self.pool_names()
    self.assertEqual(names[EP8], 4)
    self.assertEqual(
      sum(n for name, n in names.items() if name.startswith("Clockwerk")), 0
    )
    self.assert_pool_fills_locations()


class TestEpisode8KeysLast(PoolTestBase):
  options = {"episode_8_keys": "Last_section"}

  def test_three_episode_items(self) -> None:
    self.assertEqual(self.pool_names()[EP8], 3)


class TestEpisode8KeysWhole(PoolTestBase):
  options = {"episode_8_keys": "Whole_episode"}

  def test_no_episode_items(self) -> None:
    self.assertEqual(self.pool_names()[EP8], 0)


class TestEpisode8KeysGradual(PoolTestBase):
  options = {"episode_8_keys": "Gradual_sections"}

  def test_no_episode_items(self) -> None:
    self.assertEqual(self.pool_names()[EP8], 0)


class TestClockwerkHuntOnly(PoolTestBase):
  options = {
    "episode_8_keys": "Off",
    "goal": "Clockwerk_Hunt",
    "keys_in_pool": 15,
    "required_keys_goal": 15,
  }

  def test_parts_from_core_and_additional(self) -> None:
    names = self.pool_names()
    parts = {n for n in names if n.startswith("Clockwerk")}
    self.assertEqual(sum(names[n] for n in parts), 15)
    self.assertTrue(parts <= set(CLOCKWERK_CORE + CLOCKWERK_ADDITIONAL))
    self.assertEqual(len(parts), 15)


class TestManyClockwerkParts(PoolTestBase):
  options = {
    "goal": "Clockwerk_Hunt",
    "episode_8_keys": "Off",
    "keys_in_pool": 120,
    "required_keys_goal": 20,
    "tasksanity": True,
    "include_pickpocketing": True,
    "bottle_item_bundle_size": 5,
    "bottle_location_bundle_size": 1,
  }

  def test_silly_and_repeatable_parts(self) -> None:
    names = self.pool_names()
    parts = {n for n in names if n.startswith("Clockwerk")}
    self.assertEqual(sum(names[n] for n in parts), 120)
    self.assertTrue(parts & set(CLOCKWERK_SILLY))
    repeatable = {name for name, _ in CLOCKWERK_REPEATABLE}
    for name, count in names.items():
      if name.startswith("Clockwerk") and count > 1:
        self.assertIn(name, repeatable)


class TestBottleBundles(PoolTestBase):
  options = {
    "bottle_item_bundle_size": 7,
    "bottle_location_bundle_size": 7,
  }

  def test_bundle_counts(self) -> None:
    names = self.pool_names()
    for ep in ordered_group("Episode"):
      ep = ep.removeprefix("Progressive ")
      self.assertEqual(names[f"7 bottles - {ep}"], 4)
      self.assertEqual(names[f"2 bottles - {ep}"], 1)
    self.assert_pool_fills_locations()


class TestSingleBottles(PoolTestBase):
  options = {
    "bottle_item_bundle_size": 1,
    "bottle_location_bundle_size": 1,
  }

  def test_thirty_per_episode(self) -> None:
    names = self.pool_names()
    for ep in ordered_group("Episode"):
      ep = ep.removeprefix("Progressive ")
      self.assertEqual(names[f"Bottle - {ep}"], 30)
    self.assert_pool_fills_locations()


class TestAllTraps(PoolTestBase):
  options = {"trap_chance": 100}

  def test_no_filler_left(self) -> None:
    names = self.pool_names()
    for filler in ordered_group("Filler"):
      self.assertNotIn(filler, names)
    self.assertTrue(any(trap.item_name in names for trap in Trap))


class TestTrapsWithoutWeights(PoolTestBase):
  options = {
    "trap_chance": 100,
    "trap_weights": {trap.key: 0 for trap in Trap},
  }

  def test_falls_back_to_filler(self) -> None:
    names = self.pool_names()
    for trap in Trap:
      self.assertNotIn(trap.item_name, names)
    self.assertIn("Coins", names)
    self.assert_pool_fills_locations()


class TestSingleTrapType(PoolTestBase):
  options = {
    "trap_chance": 100,
    "trap_weights": {Trap.ICE.key: 5},
  }

  def test_only_enabled_trap(self) -> None:
    names = self.pool_names()
    for trap in Trap:
      if trap is not Trap.ICE:
        self.assertNotIn(trap.item_name, names)
    self.assertIn(Trap.ICE.item_name, names)
