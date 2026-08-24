"""Read-only checks of data/Constants.py against the memory of the hub
savestates: a wrong address or DAG index shows up here and nowhere in the
unit suite."""

from typing import Any

from ..data.Constants import (
  CAVE_HOOK_ORIG, LOOT_PRICES, MEGA_JUMP_UNLOAD_CALL,
  POWERUP_TEXT, SLY_BACK_NODE, TREASURE_PRICES
)
from ..Sly2Interface import PowerUps, Sly2Episode, in_ee_ram
from .harness import E2ETestBase, HubTestMixin

VANILLA_THIEFNET_COSTS = [
  200, 500, 550, 1000, 1050, 1200, 1700, 2000,
  400, 400, 750, 900, 2100, 1400, 1500, 1150,
  300, 600, 650, 600, 600, 1300, 1600, 1900
]
VANILLA_THIEFNET_EPISODES = [
  1, 2, 3, 4, 5, 6, 7, 8, 1, 2, 3, 4, 8, 6, 7, 5, 1, 2, 3, 4, 5, 6, 7, 8
]
DAG_NODE_STATUSES = range(4)


def flatten_jobs(chapters: list[Any]) -> list[int]:
  return [
    index
    for chapter in chapters
    for job in chapter
    for index in (job if isinstance(job, tuple) else (job,))
  ]


class HubChecks(HubTestMixin):
  """A freshly entered hub: only the first job open, nothing collected,
  no gadgets, the client never connected. Mixed into a state-specific
  E2ETestBase so the base itself is never collected."""

  coins = 18

  def raw32(self, address: int) -> int:
    return self.pine.read_int32(address)

  def string_at(self, address: int, length: int = 64) -> str:
    data = self.pine.read_bytes(address, length)
    return data.split(b"\x00", 1)[0].decode("latin-1")

  def test_state(self) -> None:
    self.assertEqual(
      self.interface.get_current_episode(), Sly2Episode(self.episode)
    )
    self.assertEqual(self.interface.get_current_map(), self.map_id)
    self.assertTrue(self.interface.in_hub())
    self.assertFalse(self.interface.in_safehouse())
    self.assertFalse(self.interface.is_loading())
    self.assertFalse(self.interface.in_cutscene())
    self.assertFalse(self.interface.in_thiefnet())
    self.assertEqual(self.interface.get_current_job(), 0xffffffff)
    self.assertTrue(self.interface.alive())
    self.assertEqual(self.interface.get_coins(), self.coins)

  def test_price_tables(self) -> None:
    for key, prices in (
      ("loot prices", LOOT_PRICES), ("treasure prices", TREASURE_PRICES)
    ):
      with self.subTest(key):
        names = list(self.addr[key])
        values = self.interface._batch_read32(
          [self.addr[key][name] for name in names]
        )
        self.assertEqual(
          dict(zip(names, values)), {name: prices[name] for name in names}
        )

  def test_thiefnet_tables(self) -> None:
    self.assertEqual(
      self.interface._batch_read32(self.addr["thiefnet costs"]),
      VANILLA_THIEFNET_COSTS
    )
    self.assertEqual(
      self.interface._batch_read32(self.addr["thiefnet unlock"]),
      VANILLA_THIEFNET_EPISODES
    )

  def test_dag(self) -> None:
    nodes = self.interface._episode_nodes(self.episode)
    statuses = self.interface.job_statuses(nodes)
    count = len(self.interface._dag_nodes)
    self.assertGreaterEqual(count, max(nodes) + 1)
    self.assertLess(count, 256)
    self.assertTrue(all(in_ee_ram(node) for node in self.interface._dag_nodes))
    self.assertEqual(len(set(self.interface._dag_nodes)), count)
    for node, status in zip(nodes, statuses):
      with self.subTest(node=node):
        self.assertIn(status, DAG_NODE_STATUSES)
        self.assertEqual(
          status, self.raw32(self.interface._get_job_address(node) + 0x54)
        )
        self.assertEqual(status, int(node == nodes[0]))
    self.assertEqual(self.interface.jobs_completed(nodes), [False] * len(nodes))

  def test_dag_missions_and_parents(self) -> None:
    jobs = flatten_jobs(self.addr["jobs"][self.episode - 1])
    missions = {
      node: self.raw32(self.interface._get_job_address(node) + 0x7c)
      for node in self.interface._episode_nodes(self.episode)
    }
    self.assertTrue(all(in_ee_ram(mission) for mission in missions.values()))
    job_missions = [missions[node] for node in jobs]
    self.assertEqual(len(set(job_missions)), len(job_missions))
    for node in missions:
      address = self.interface._get_job_address(node)
      parents = self.raw32(address + 0x94)
      pointers = self.raw32(address + 0x98)
      with self.subTest(node=node):
        self.assertLess(parents, 16)
        if parents:
          self.assertTrue(in_ee_ram(pointers, 4 * parents))
          self.assertTrue(all(
            in_ee_ram(parent)
            for parent in self.interface._batch_read32(
              [pointers + 4 * i for i in range(parents)]
            )
          ))

  def test_bottles(self) -> None:
    episode = Sly2Episode(self.episode)
    self.assertEqual(self.interface.get_bottles(episode), 0)
    self.assertEqual(self.raw32(self.addr["bottle count"]), 0)
    for flags in self.interface.get_bottle_flags():
      self.assertEqual(flags >> 30, 0)
    self.assertEqual(
      self.interface.get_bottle_list(episode), [False] * 30
    )

  def test_collectibles(self) -> None:
    self.assertEqual(self.interface.all_vault_statuses(), [False] * 8)
    self.assertEqual(self.interface.get_operation_completion(), [False] * 8)
    self.assertFalse(any(self.interface.all_loot_stolen()))
    self.assertFalse(any(any(e) for e in self.interface.all_treasures_stolen()))
    for key in ("vaults", "operation completion", "loot"):
      with self.subTest(key):
        words = self.interface._batch_read32(list(self.addr[key]))
        self.assertTrue(all(word in (0, 1) for word in words))

  def test_strings(self) -> None:
    table = self.raw32(self.addr["string table"])
    self.assertTrue(in_ee_ram(table))
    expected = {
      "infobox": "DO NOT LOCALIZE",
      "right back": "RIGHT BACK",
      "this powerup.": ""
    }
    for name, substring in expected.items():
      with self.subTest(name):
        offset = self.addr["text"][name][self.episode - 1]
        pointer = self.raw32(table + offset)
        self.assertTrue(in_ee_ram(pointer))
        text = self.string_at(pointer)
        self.assertTrue(text.isprintable() and text)
        self.assertIn(substring, text)

  def test_powerup_texts(self) -> None:
    powerups = self.addr["text"]["powerups"][self.episode - 1]
    self.assertEqual(list(powerups), list(POWERUP_TEXT))
    for name, (name_address, description_address) in powerups.items():
      with self.subTest(name):
        self.assertEqual(self.string_at(name_address), name)
        description = self.string_at(description_address, 256)
        self.assertGreaterEqual(len(description), len(POWERUP_TEXT[name]))
        self.assertEqual(description[:16], POWERUP_TEXT[name][:16])

  def test_powerups_and_bindings(self) -> None:
    self.assertEqual(
      self.interface.read_powerups(),
      PowerUps(*([False] * len(PowerUps._fields)))
    )
    self.assertEqual(self.interface.get_sly_bindings(), [0, 0, 0])

  def test_entities(self) -> None:
    self.assertEqual(self.raw32(self.addr["health"]["Sly"]), 40)
    sly = self.raw32(self.addr["sly pointer"])
    self.assertTrue(in_ee_ram(sly))
    self.assertTrue(in_ee_ram(self.raw32(sly + SLY_BACK_NODE)))
    self.assertEqual(self.interface.get_active_character(), sly)
    self.assertTrue(in_ee_ram(self.raw32(self.addr["entity manager"])))

  def test_cave_pristine(self) -> None:
    hook = self.addr["cave hook"]
    self.assertEqual(self.raw32(hook), CAVE_HOOK_ORIG)
    self.assertFalse(self.interface.cave_live())
    self.assertEqual(
      self.pine.read_bytes(self.addr["cave"], 0x2000), bytes(0x2000)
    )

  def test_prefetch_parity(self) -> None:
    batches: list[list[tuple[int, int]]] = []
    original = self.interface.prefetch

    def recording(reads: list[tuple[int, int]]) -> None:
      batches.append(list(reads))
      original(reads)

    self.interface.prefetch = recording
    try:
      self.interface.prefetch_tick_state()
    finally:
      del self.interface.prefetch
    self.assertEqual(len(batches), 2)
    reads = [read for batch in batches for read in batch]
    for length, address in reads:
      with self.subTest(address=hex(address)):
        self.assertEqual(
          self.interface._read_bytes(address, length),
          self.pine.read_bytes(address, length)
        )
    statuses = {
      self.interface._get_job_address(node) + 0x54
      for node in self.interface._episode_nodes(self.episode)
    }
    self.assertTrue(statuses <= {address for _, address in batches[1]})


class TestEp1Hub(HubChecks, E2ETestBase):
  state = "ep1_hub"
  episode = 1
  map_id = 2


class TestEp8Hub(HubChecks, E2ETestBase):
  state = "ep8_hub"
  episode = 8
  map_id = 38

  def test_mega_jump_unload_patch(self) -> None:
    address = self.addr["unload mega jump"]
    self.assertEqual(self.raw32(address), MEGA_JUMP_UNLOAD_CALL)
    self.interface.patch_mega_jump_unload()
    self.assertEqual(self.raw32(address), 0)
    self.assertEqual(self.interface.refused_patches, set())
    self.reload()

  def test_mega_jump_pack_absent(self) -> None:
    sly = self.raw32(self.addr["sly pointer"])
    node = self.raw32(sly + SLY_BACK_NODE)
    before = self.pine.read_bytes(node, 0x40)
    self.interface.hide_mega_jump_pack()
    self.interface.allow_sly_treasure_pickup()
    self.interface.clear_cache()
    self.assertEqual(self.pine.read_bytes(node, 0x40), before)
    self.assertEqual(self.raw32(self.addr["clock-la defeated"]), 0)
