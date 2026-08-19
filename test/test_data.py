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
)
from ..data.Items import item_dict, ordered_group
from ..data.Items import from_id as item_from_id
from ..data.Locations import location_dict, tasksanity_list
from ..data.Locations import from_id as location_from_id
from ..Sly2Interface import PowerUps

GAME_ID = "SCUS-97316"

RULE_LOCATIONS = [
  "A Tangled Web - Crystal Vase",
  "A Tangled Web - Operation: High Road",
  "He Who Tames the Iron Horse - Spice in the Sky",
  "He Who Tames the Iron Horse - Ride the Iron Horse",
  "Menace from the North, Eh! - Thermal Ride",
  "Menace from the North, Eh! - Bottle #04",
  "Anatomy for Disaster - Bottle #03",
  "Menace from the North, Eh! - 30 bottles collected",
  "Anatomy for Disaster - 30 bottles collected",
  "The Black Chateau - Operation: Thunder Beak",
  "The Predator Awakens - Operation: Wet Tiger",
  "A Tangled Web - Operation: High Road",
  "Menace from the North, Eh! - Operation: Canada Games",
  "Anatomy for Disaster - Carmelita's Gunner/Defeat Clock-la",
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
