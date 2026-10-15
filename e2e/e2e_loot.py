"""Pickpocket loot configuration against the ep1_hub savestate: the vanilla
tables as the game ships them, every loot write read back, the guard
despawn, and the client's loot tick (tables, odds, prices and a pickpocket
location check)."""

import struct
import time
from typing import Callable

from ..data.Constants import (
  LOOT, LOOT_IDS, LOOT_PRICES, PICKPOCKET_LOOT_TABLE_CHANCES, TREASURE_PRICES
)
from ..data.Locations import location_dict
from ..data.Names import pickpocket_location
from ..pcsx2_interface.pine import Pine
from ..Sly2Interface import Sly2Episode
from ..test.client_base import make_slot_data
from .harness import E2ETestBase
from .tick_base import TickTestBase

EPISODE = Sly2Episode(1)
VANILLA_ODDS = (30, 30, 15, 15, 5, 5)
VANILLA_CHANCES = (0.2, 0.4)
LOOT_OPTIONS = {
  "loot_values": 2, "treasure_values": 2, "loot_table_distribution": 6,
  "small_guard_loot_chance": 55, "large_guard_loot_chance": 85
}


def episode_entries(
  loot_table: dict, episode: int
) -> dict[tuple[int, int], int]:
  return {
    (int(large), slot - 1): LOOT_IDS[loot]
    for loot, locations in loot_table.items()
    for ep, large, slot in locations
    if ep == episode
  }


class LootReads:
  pine: Pine
  addr: dict

  def table(self, episode: int = 1) -> dict[tuple[int, int], int]:
    rows = self.addr["loot table"][episode - 1]
    return {
      (row, slot): value
      for row in (0, 1)
      for slot, value in enumerate(
        self.pine.batch_read_int32(list(rows[row]))
      )
    }

  def odds(self, episode: int = 1) -> tuple[tuple[int, ...], ...]:
    rows = self.addr["loot table odds"][episode - 1]
    return tuple(
      tuple(self.pine.batch_read_int32(list(rows[row])))
      for row in (0, 1)
    )

  def chances(self, episode: int = 1) -> tuple[float, ...]:
    return tuple(
      struct.unpack("<f", self.pine.read_bytes(address, 4))[0]
      for address in self.addr["loot chance"][episode - 1]
    )

  def prices(self, key: str) -> dict[str, int]:
    names = list(self.addr[key])
    values = self.pine.batch_read_int32(
      [self.addr[key][name] for name in names]
    )
    return dict(zip(names, values))


class TestLoot(LootReads, E2ETestBase):
  state = "ep1_hub"
  episode = 1
  map_id = 2

  def setUp(self) -> None:
    super().setUp()
    self.mutated = True

  def tearDown(self) -> None:
    if self.mutated:
      self.reload()

  def _wait(self, cond: Callable[[], bool], timeout: float = 6.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      self.interface.clear_cache()
      if cond():
        return True
      time.sleep(0.05)
    return False

  def test_vanilla_config(self) -> None:
    self.mutated = False
    self.assertEqual(self.table(), episode_entries(LOOT, 1))
    self.assertEqual(self.odds(), (VANILLA_ODDS, VANILLA_ODDS))
    for actual, expected in zip(self.chances(), VANILLA_CHANCES):
      self.assertAlmostEqual(actual, expected, places=5)
    self.assertEqual(self.prices("loot prices"), LOOT_PRICES)
    self.assertEqual(self.prices("treasure prices"), TREASURE_PRICES)

  def test_set_loot_table(self) -> None:
    loot_table = make_slot_data()["loot_table"]
    self.interface.set_loot_table(EPISODE, loot_table)
    self.assertEqual(self.table(), episode_entries(loot_table, 1))
    self.assertEqual(self.table(2), episode_entries(LOOT, 2))

  def test_set_loot_odds_and_chance(self) -> None:
    odds = PICKPOCKET_LOOT_TABLE_CHANCES[5]
    self.interface.set_loot_table_odds(EPISODE, (odds, VANILLA_ODDS))
    self.assertEqual(self.odds(), (odds, VANILLA_ODDS))
    self.interface.set_loot_chance(EPISODE, (0.5, 0.75))
    self.assertEqual(self.chances(), (0.5, 0.75))

  def test_set_prices(self) -> None:
    slot_data = make_slot_data(**LOOT_OPTIONS)
    self.interface.set_prices(
      slot_data["loot_prices"], slot_data["treasure_prices"]
    )
    self.assertEqual(self.prices("loot prices"), slot_data["loot_prices"])
    self.assertEqual(
      self.prices("treasure prices"), slot_data["treasure_prices"]
    )
    self.assertNotEqual(slot_data["loot_prices"], LOOT_PRICES)

  def test_despawn_guards(self) -> None:
    self.interface.install_cave()
    self.assertTrue(self._wait(self.interface.cave_live))
    spawned = {
      g: self.pine.read_bytes(g + 0x230, 12)
      for g in self.interface._walk_guards()
      if self.pine.read_int32(g + 0x2c) & 0x10000000
    }
    self.assertGreater(len(spawned), 0)
    self.interface.despawn_guards()
    request = self.interface.addresses["remove guards"]
    self.assertTrue(self._wait(lambda: self.pine.read_int32(request) == 0))
    # The spawner can refill a slot within frames, but never at the spot the
    # removed guard was standing on
    for guard, position in spawned.items():
      self.assertTrue(
        not self.pine.read_int32(guard + 0x2c) & 0x10000000 or
        self.pine.read_bytes(guard + 0x230, 12) != position
      )


class TestLootTick(LootReads, TickTestBase):
  options = LOOT_OPTIONS

  async def test_ticks(self) -> None:
    self.addr = self.interface.addresses
    slot_data = self.ctx.slot_data
    assert slot_data is not None
    first_loot = next(
      loot for loot, locations in slot_data["loot_table"].items()
      if any(ep == 1 for ep, _, _ in locations)
    )
    self.pine.write_int32(
      self.addr["loot"][list(LOOT_IDS).index(first_loot)], 1
    )
    await self.run_ticks()
    self.assertEqual(self.table(), episode_entries(slot_data["loot_table"], 1))
    odds = tuple(PICKPOCKET_LOOT_TABLE_CHANCES[5])
    self.assertEqual(self.odds(), (odds, odds))
    for actual, expected in zip(self.chances(), (0.55, 0.85)):
      self.assertAlmostEqual(actual, expected, places=5)
    self.assertEqual(self.prices("loot prices"), slot_data["loot_prices"])
    sent = {
      code
      for message in self.ctx.sent_cmds("LocationChecks")
      for code in message["locations"]
    }
    self.assertIn(location_dict[pickpocket_location(first_loot)].code, sent)
