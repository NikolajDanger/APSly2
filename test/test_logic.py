from BaseClasses import CollectionState

from ..data.Constants import EPISODES
from ..data.Locations import location_groups
from ..data.Names import (
  VICTORY,
  EpisodeName,
  ItemName,
  LocationCategory,
  bottle_item,
  episode_region,
  job_location,
  progressive_episode,
  thiefnet_location,
  treasure_location,
  vault_location,
)
from . import Sly2TestBase

PARAGLIDER_JOBS = [
  job_location(EpisodeName.A_TANGLED_WEB, "Operation: High Road"),
  job_location(EpisodeName.HE_WHO_TAMES_THE_IRON_HORSE, "Spice in the Sky"),
  job_location(
    EpisodeName.HE_WHO_TAMES_THE_IRON_HORSE, "Ride the Iron Horse"
  ),
  job_location(EpisodeName.MENACE_FROM_THE_NORTH_EH, "Thermal Ride"),
]

VICTORY_JOBS = [
  job_location(EpisodeName.THE_BLACK_CHATEAU, "Operation: Thunder Beak"),
  job_location(EpisodeName.THE_PREDATOR_AWAKENS, "Operation: Wet Tiger"),
  job_location(EpisodeName.A_TANGLED_WEB, "Operation: High Road"),
  job_location(
    EpisodeName.MENACE_FROM_THE_NORTH_EH, "Operation: Canada Games"
  ),
  job_location(
    EpisodeName.ANATOMY_FOR_DISASTER, "Carmelita's Gunner/Defeat Clock-la"
  ),
]


class TestGadgetGates(Sly2TestBase):
  options = {"include_mega_jump": True, "episode_8_keys": "Off"}

  def test_paraglider_jobs(self) -> None:
    self.assertAccessDependency(
      PARAGLIDER_JOBS, [[ItemName.PARAGLIDER]], only_check_listed=True
    )

  def test_crystal_vase(self) -> None:
    self.assertAccessDependency(
      [treasure_location(EpisodeName.A_TANGLED_WEB, "Crystal Vase")],
      [
        [ItemName.PARAGLIDER], [ItemName.MEGA_JUMP],
        [ItemName.HOVER_PACK], [ItemName.TURNBUCKLE_LAUNCH]
      ],
      only_check_listed=True
    )

  def test_iron_horse_late_chapters(self) -> None:
    self.collect_all_but(ItemName.PARAGLIDER)
    self.assertTrue(self.can_reach_region(episode_region(6, 2)))
    self.assertFalse(self.can_reach_region(episode_region(6, 3)))
    self.assertFalse(self.can_reach_region(episode_region(6, 4)))
    self.collect_by_name(ItemName.PARAGLIDER)
    self.assertTrue(self.can_reach_region(episode_region(6, 4)))

  def test_menace_final_chapter(self) -> None:
    for missing in [ItemName.PARAGLIDER, ItemName.ALARM_CLOCK]:
      self.multiworld.state = CollectionState(self.multiworld)
      self.collect_all_but(missing)
      self.assertTrue(self.can_reach_region(episode_region(7, 3)))
      self.assertFalse(self.can_reach_region(episode_region(7, 4)), missing)
      self.collect_by_name(missing)
      self.assertTrue(self.can_reach_region(episode_region(7, 4)))


class TestThiefNetGating(Sly2TestBase):
  options = {"starting_episode": "The_Black_Chateau"}

  def test_needs_episode_items(self) -> None:
    self.assertFalse(self.can_reach_location(thiefnet_location(1)))
    episodes = self.get_items_by_name(
      [progressive_episode(ep) for ep in EPISODES]
    )
    self.collect(episodes[0])
    self.assertTrue(self.can_reach_location(thiefnet_location(1)))
    self.assertFalse(self.can_reach_location(thiefnet_location(4)))
    self.collect(episodes[1:14])
    self.assertFalse(self.can_reach_location(thiefnet_location(24)))
    self.collect(episodes[14])
    self.assertTrue(self.can_reach_location(thiefnet_location(24)))


class TestBottleVaults(Sly2TestBase):
  options = {
    "bottle_item_bundle_size": 10,
    "bottle_location_bundle_size": 10,
    "include_vaults": True,
  }

  def test_vault_needs_bundles(self) -> None:
    for ep in EPISODES:
      self.multiworld.state = CollectionState(self.multiworld)
      bundles = self.get_items_by_name(bottle_item(10, ep))
      self.assertEqual(len(bundles), 3)
      self.collect_all_but(bottle_item(10, ep))
      self.assertFalse(self.can_reach_location(vault_location(ep)))
      self.collect(bundles[:2])
      self.assertFalse(self.can_reach_location(vault_location(ep)))
      self.collect(bundles[2])
      self.assertTrue(self.can_reach_location(vault_location(ep)))


class TestPickpocketing(Sly2TestBase):
  options = {"include_pickpocketing": True, "randomize_loot": True}

  def test_all_loot_locations_placed(self) -> None:
    placed = {loc.name for loc in self.multiworld.get_locations()}
    self.assertTrue(location_groups[LocationCategory.PICKPOCKET] <= placed)

  def test_hybrid_regions_reachable_from_either_side(self) -> None:
    hybrids = [
      region for region in self.multiworld.get_regions(self.player)
      if "/" in region.name
    ]
    self.assertTrue(hybrids)
    for region in hybrids:
      parents = region.name.split("/")
      self.assertEqual(
        {
          entrance.parent_region.name for entrance in region.entrances
          if entrance.parent_region is not None
        },
        set(parents)
      )
      for location in region.locations:
        self.assertIn(
          location.name, location_groups[LocationCategory.PICKPOCKET]
        )


class GoalTestBase(Sly2TestBase):
  def test_beatable_only_with_items(self) -> None:
    self.assertBeatable(False)
    self.collect_all_but([])
    self.assertBeatable(True)


class TestGoalDimitri(GoalTestBase):
  options = {"goal": "Dimitri"}

  def test_victory_event(self) -> None:
    location = self.multiworld.get_location(VICTORY_JOBS[0], self.player)
    self.assertIsNone(location.address)
    assert location.item is not None
    self.assertEqual(location.item.name, VICTORY)
    self.assertTrue(location.locked)


class TestGoalRajan(GoalTestBase):
  options = {"goal": "Rajan"}


class TestGoalContessa(GoalTestBase):
  options = {"goal": "The_Contessa"}


class TestGoalJeanBison(GoalTestBase):
  options = {"goal": "Jean_Bison"}


class TestGoalClockLa(GoalTestBase):
  options = {"goal": "ClockLa"}

  def test_victory_event(self) -> None:
    location = self.multiworld.get_location(VICTORY_JOBS[4], self.player)
    self.assertIsNone(location.address)
    assert location.item is not None
    self.assertEqual(location.item.name, VICTORY)


class TestGoalAllBosses(GoalTestBase):
  options = {"goal": "All_Bosses"}

  def test_no_victory_event(self) -> None:
    for name in VICTORY_JOBS:
      location = self.multiworld.get_location(name, self.player)
      self.assertIsNotNone(location.address)


class TestGoalClockwerkHunt(GoalTestBase):
  options = {
    "goal": "Clockwerk_Hunt",
    "keys_in_pool": 12,
    "required_keys_goal": 8,
  }

  def test_needs_required_parts(self) -> None:
    parts = [
      item for item in self.multiworld.itempool
      if item.name.startswith("Clockwerk")
    ]
    self.collect(parts[:7])
    self.assertBeatable(False)
    self.collect(parts[7])
    self.assertBeatable(True)


class TestGoalAllVaults(GoalTestBase):
  options = {"goal": "All_Vaults", "include_vaults": True}

  def test_every_vault_required(self) -> None:
    for ep in list(EPISODES)[1:7]:
      self.multiworld.state = CollectionState(self.multiworld)
      self.collect_all_but(progressive_episode(ep))
      self.assertBeatable(False)


class TestGoalPickAndMixEpisodes(GoalTestBase):
  options = {
    "goal": "Pick_and_Mix",
    "pick_and_mix": {"the_black_chateau": 1, "jailbreak": 1},
  }


class TestGoalPickAndMixVaultsAndParts(GoalTestBase):
  options = {
    "goal": "Pick_and_Mix",
    "pick_and_mix": {"all_vaults": 1, "clockwerk_hunt": 1},
    "include_vaults": True,
    "episode_8_keys": "Off",
    "keys_in_pool": 10,
    "required_keys_goal": 5,
  }


class TestTasksanity(Sly2TestBase):
  options = {"tasksanity": True}

  def test_task_locations_follow_job_rules(self) -> None:
    self.collect_all_but(ItemName.PARAGLIDER)
    prefix = job_location(
      EpisodeName.HE_WHO_TAMES_THE_IRON_HORSE, "Spice in the Sky"
    ) + " -"
    tasks = [
      loc.name for loc in self.multiworld.get_locations()
      if loc.name.startswith(prefix)
    ]
    self.assertTrue(tasks)
    for task in tasks:
      self.assertFalse(self.can_reach_location(task))


class TestEpisode8First(Sly2TestBase):
  options = {
    "episode_8_keys": "First_section",
    "keys_in_pool": 10,
    "required_keys_episode_8": 6,
  }

  def test_parts_gate_first_chapter(self) -> None:
    self.collect_all_but(
      [n for n in self.world.item_name_to_id if n.startswith("Clockwerk")]
    )
    self.assertFalse(self.can_reach_region(episode_region(8, 1)))
    parts = [
      item for item in self.multiworld.itempool
      if item.name.startswith("Clockwerk")
    ]
    self.collect(parts[:6])
    self.assertTrue(self.can_reach_region(episode_region(8, 1)))
    self.assertTrue(self.can_reach_region(episode_region(8, 4)))


class TestEpisode8Whole(Sly2TestBase):
  options = {"episode_8_keys": "Whole_episode"}


class TestEpisode8Gradual(Sly2TestBase):
  options = {
    "episode_8_keys": "Gradual_sections",
    "keys_in_pool": 8,
    "required_keys_episode_8": 8,
  }

  def test_sections_unlock_gradually(self) -> None:
    parts = [
      item for item in self.multiworld.itempool
      if item.name.startswith("Clockwerk")
    ]
    for n, needed in enumerate([2, 4, 6, 8], start=1):
      self.multiworld.state = CollectionState(self.multiworld)
      self.collect_all_but([item.name for item in parts])
      self.collect(parts[:needed - 1])
      self.assertFalse(self.can_reach_region(episode_region(8, n)))
      self.collect(parts[needed - 1])
      self.assertTrue(self.can_reach_region(episode_region(8, n)))


class TestBottlesanity(Sly2TestBase):
  options = {
    "bottle_item_bundle_size": 1,
    "bottle_location_bundle_size": 1,
    "bottlesanity": True,
  }


class TestStartAnatomyForDisaster(Sly2TestBase):
  options = {
    "starting_episode": "Anatomy_for_Disaster",
    "episode_8_keys": "Off",
  }

  def test_start_reaches_episode_8(self) -> None:
    self.assertTrue(self.can_reach_region(episode_region(8, 1)))
    self.assertFalse(self.can_reach_region(episode_region(1, 1)))
