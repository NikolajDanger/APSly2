import os
import re
import unittest

from ..data.Constants import (
  ADDRESSES,
  ENEMIES,
  EPISODES,
  HUB_MAPS,
  LOOT,
  LOOT_IDS,
  LOOT_PRICES,
  OTHER_POWERUPS,
  PICKPOCKET_LOOT_TABLE_CHANCES,
  POWERUP_TEXT,
  TASKS,
  TREASURE_PRICES,
  TREASURES,
  episode_name,
  episode_number,
)
from ..data.Items import item_dict, item_groups, ordered_group
from ..data.Items import from_id as item_from_id
from ..data.Names import (
  EpisodeName,
  ItemCategory,
  ItemName,
  bottle_item,
  bottle_location,
  bottles_collected_location,
  job_location,
  parse_bottle_item,
  parse_progressive_episode,
  progressive_episode,
  treasure_location,
)
from ..data.Locations import location_dict, tasksanity_list
from ..data.Locations import from_id as location_from_id
from ..Sly2Interface import PowerUps, Sly2Episode
from ..Sly2Options import BottleItemBundleSize, ScoutThiefnet

GAME_ID = "SCUS-97316"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RULE_LOCATIONS = [
  treasure_location(EpisodeName.A_TANGLED_WEB, "Crystal Vase"),
  job_location(EpisodeName.A_TANGLED_WEB, "Operation: High Road"),
  job_location(EpisodeName.HE_WHO_TAMES_THE_IRON_HORSE, "Spice in the Sky"),
  job_location(
    EpisodeName.HE_WHO_TAMES_THE_IRON_HORSE, "Ride the Iron Horse"
  ),
  job_location(EpisodeName.MENACE_FROM_THE_NORTH_EH, "Thermal Ride"),
  bottle_location(EpisodeName.MENACE_FROM_THE_NORTH_EH, 4),
  treasure_location(EpisodeName.MENACE_FROM_THE_NORTH_EH, "Jeweled Chalice"),
  bottle_location(EpisodeName.ANATOMY_FOR_DISASTER, 3),
  bottles_collected_location(EpisodeName.MENACE_FROM_THE_NORTH_EH, 30),
  bottles_collected_location(EpisodeName.ANATOMY_FOR_DISASTER, 30),
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


class TestIds(unittest.TestCase):
  def test_item_codes_unique(self) -> None:
    codes = [item.code for item in item_dict.values()]
    self.assertEqual(len(codes), len(set(codes)))

  def test_location_codes_unique(self) -> None:
    codes = [loc.code for loc in location_dict.values()]
    self.assertEqual(len(codes), len(set(codes)))

  def test_item_from_id_round_trips(self) -> None:
    for name, item in item_dict.items():
      self.assertEqual(item_from_id(item.code).name, name)

  def test_location_from_id_round_trips(self) -> None:
    for name, loc in location_dict.items():
      self.assertEqual(location_from_id(loc.code).name, name)


class TestEpisodes(unittest.TestCase):
  def test_episode_shape(self) -> None:
    self.assertEqual(len(EPISODES), 8)
    for ep, chapters in EPISODES.items():
      self.assertEqual(len(chapters), 3 if ep == "Jailbreak" else 4, ep)
    self.assertEqual(sum(len(c) for ch in EPISODES.values() for c in ch), 69)

  def test_per_episode_tables(self) -> None:
    self.assertEqual(len(ENEMIES), len(EPISODES))
    self.assertEqual(len(HUB_MAPS), len(EPISODES))
    self.assertEqual(set(TREASURES), set(EPISODES))
    self.assertTrue(set(TASKS) <= set(EPISODES))

  def test_tasks_belong_to_jobs(self) -> None:
    for ep, jobs in TASKS.items():
      all_jobs = {job for chapter in EPISODES[ep] for job in chapter}
      self.assertTrue(set(jobs) <= all_jobs, ep)

  def test_job_addresses_match_episode_shape(self) -> None:
    jobs = ADDRESSES[GAME_ID]["jobs"]
    self.assertEqual(
      [[len(chapter) for chapter in episode] for episode in jobs],
      [[len(chapter) for chapter in episode] for episode in EPISODES.values()]
    )
    for i, episode in enumerate(jobs):
      indices = [
        index
        for chapter in episode
        for job in chapter
        for index in (job if isinstance(job, tuple) else (job,))
      ]
      self.assertEqual(len(indices), len(set(indices)), i)


class TestLocationNames(unittest.TestCase):
  def assert_locations(self, names: list[str]) -> None:
    missing = [name for name in names if name not in location_dict]
    self.assertEqual(missing, [])

  def test_jobs(self) -> None:
    self.assert_locations([
      f"{ep} - {job}"
      for ep, chapters in EPISODES.items()
      for chapter in chapters for job in chapter
    ])

  def test_tasks(self) -> None:
    self.assert_locations([
      f"{ep} - {job} - {task}"
      for ep, jobs in TASKS.items()
      for job, tasks in jobs.items() for _, task in tasks
    ])
    self.assertEqual(
      len(tasksanity_list),
      sum(len(t) for jobs in TASKS.values() for t in jobs.values())
    )

  def test_vaults_treasures_thiefnet(self) -> None:
    self.assert_locations([f"{ep} - Vault" for ep in EPISODES])
    self.assert_locations([
      f"{ep} - {name}" for ep, t in TREASURES.items() for name, _ in t
    ])
    self.assert_locations([f"ThiefNet {i:02}" for i in range(1, 25)])
    self.assert_locations([f"Pickpocket {loot}" for loot in LOOT])

  def test_rule_literals(self) -> None:
    self.assert_locations(RULE_LOCATIONS)

  def test_rule_item_literals(self) -> None:
    src = ""
    for module in ("Rules.py", "Regions.py"):
      with open(os.path.join(REPO_ROOT, module)) as f:
        src += f.read()
    self.assertEqual(re.findall(r'state\.has(?:_group)?\("', src), [])
    names = set(re.findall(r'state\.has\(ItemName\.([A-Z_0-9]+)', src))
    groups = set(re.findall(
      r'state\.(?:has_group|count_group)\(ItemCategory\.([A-Z_0-9]+)', src
    ))
    self.assertTrue(names)
    self.assertTrue(groups)
    for name in names:
      self.assertIn(getattr(ItemName, name), item_dict)
    for group in groups:
      self.assertIn(getattr(ItemCategory, group), item_groups)

  def test_bottle_items_cover_bundle_range(self) -> None:
    for ep in EPISODES:
      self.assertIn(f"Bottle - {ep}", item_dict)
      for n in range(2, BottleItemBundleSize.range_end + 1):
        self.assertIn(f"{n} bottles - {ep}", item_dict)

  def test_treasure_chapters(self) -> None:
    for ep, t in TREASURES.items():
      for name, chapter in t:
        self.assertIn(chapter, range(1, len(EPISODES[ep]) + 1), name)


class TestLootAndPrices(unittest.TestCase):
  def test_treasure_prices(self) -> None:
    names = [name for t in TREASURES.values() for name, _ in t]
    self.assertEqual(len(TREASURE_PRICES), len(names) + 1)
    self.assertIn("Gold Painting", TREASURE_PRICES)
    self.assertTrue(set(names) <= set(TREASURE_PRICES))
    self.assertEqual(
      set(ADDRESSES[GAME_ID]["treasure prices"]), set(TREASURE_PRICES)
    )

  def test_loot_tables_aligned(self) -> None:
    self.assertEqual(set(LOOT_PRICES), set(LOOT))
    self.assertEqual(set(LOOT_IDS), set(LOOT))
    self.assertEqual(set(ADDRESSES[GAME_ID]["loot prices"]), set(LOOT))
    self.assertEqual(len(set(LOOT_IDS.values())), len(LOOT))
    self.assertEqual(len(ADDRESSES[GAME_ID]["loot"]), len(LOOT))

  def test_loot_locations(self) -> None:
    for loot, locations in LOOT.items():
      for ep, big, slot in locations:
        self.assertIn(ep, range(1, 9), loot)
        self.assertIsInstance(big, bool, loot)
        self.assertIn(slot, range(1, 7), loot)

  def test_loot_table_chances(self) -> None:
    self.assertEqual(len(PICKPOCKET_LOOT_TABLE_CHANCES), 100)
    for row in PICKPOCKET_LOOT_TABLE_CHANCES:
      self.assertEqual(len(row), 6)


class TestNames(unittest.TestCase):
  def test_episode_name_number_round_trip(self) -> None:
    for i in range(1, 9):
      name = episode_name(i)
      self.assertEqual(episode_number(name), i)
      self.assertEqual(
        Sly2Episode(i).name,
        name.replace(",", "").replace("!", "").replace(" ", "_")
      )

  def test_episode_name_constants_are_episode_keys(self) -> None:
    constants = {
      value for key, value in vars(EpisodeName).items()
      if not key.startswith("_")
    }
    self.assertEqual(constants, set(EPISODES))

  def test_bottle_item_round_trip(self) -> None:
    for name, item in item_dict.items():
      if item.category == ItemCategory.BOTTLES:
        count, ep = parse_bottle_item(name)
        self.assertEqual(bottle_item(count, ep), name)
        self.assertIn(ep, EPISODES)

  def test_progressive_episode_round_trip(self) -> None:
    for name, item in item_dict.items():
      if item.category == ItemCategory.EPISODE:
        ep = parse_progressive_episode(name)
        self.assertEqual(progressive_episode(ep), name)
        self.assertIn(ep, EPISODES)

  def test_parsers_reject_other_names(self) -> None:
    with self.assertRaises(ValueError):
      parse_bottle_item(ItemName.COINS)
    with self.assertRaises(ValueError):
      parse_progressive_episode(ItemName.COINS)


class TestPowerUps(unittest.TestCase):
  def test_powerup_fields_match_text_tables(self) -> None:
    names = list(POWERUP_TEXT.keys()) + OTHER_POWERUPS
    self.assertEqual(len(names), len(PowerUps._fields))
    for name, field in zip(names, PowerUps._fields):
      self.assertEqual(name.lower().replace(" ", "_"), field)

  def test_every_powerup_item_is_known(self) -> None:
    names = list(POWERUP_TEXT.keys()) + OTHER_POWERUPS
    for name in ordered_group("Power-Up"):
      self.assertIn(name.replace("Paraglider", "Paraglide"), names)


class TestScoutThiefnetAliases(unittest.TestCase):
  def test_old_toggle_values(self) -> None:
    for value in ("true", "True", True):
      self.assertEqual(
        ScoutThiefnet.from_any(value).value,
        ScoutThiefnet.option_show_and_scout
      )
    for value in ("false", False):
      self.assertEqual(
        ScoutThiefnet.from_any(value).value, ScoutThiefnet.option_show_only
      )
