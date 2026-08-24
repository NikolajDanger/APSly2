"""ThiefNet against the safehouse savestates: the safehouse/ThiefNet state
reads, and the client's shop rewrite on entry (unlocks, costs, names,
descriptions), purchase detection, and restore on leaving."""

import asyncio

from NetUtils import NetworkItem

from ..data.Constants import POWERUP_TEXT
from ..data.Items import item_dict
from ..data.Names import ItemName, thiefnet_location
from ..data.Locations import location_dict
from ..Sly2Client import _handle_game_ready
from ..Sly2Interface import PowerUps
from .harness import E2ETestBase, load_state
from .tick_base import TickTestBase

SAFEHOUSE_STRINGS = (305, 306, 307, 308)
SCOUTED = [
  ItemName.PARAGLIDER, ItemName.TRIGGER_BOMB, ItemName.MEGA_JUMP,
  ItemName.COINS
] * 6


def thiefnet_code(n: int) -> int:
  return location_dict[thiefnet_location(n)].code


class TestSafehouse(E2ETestBase):
  state = "ep1_safehouse"
  episode = 1
  map_id = 2

  def test_state(self) -> None:
    self.assertTrue(self.interface.in_safehouse())
    self.assertFalse(self.interface.in_thiefnet())
    self.assertTrue(self.interface.in_hub())
    self.assertEqual(self.interface.get_active_character(), 0)
    self.assertIn(self.interface.current_infobox(), SAFEHOUSE_STRINGS)

  def test_kill_refused(self) -> None:
    self.interface.install_cave()
    self.interface.clear_cache()
    self.interface.kill_player()
    self.assertEqual(self.pine.read_int32(self.addr["death flag"]), 0)
    self.reload()


class TestThiefNetOpen(E2ETestBase):
  state = "ep1_thiefnet"
  episode = 1
  map_id = 2

  def test_state(self) -> None:
    self.assertTrue(self.interface.in_safehouse())
    self.assertTrue(self.interface.in_thiefnet())
    self.assertEqual(
      self.pine.read_int32(self.addr["thiefnet control"]), 0x2DFC00
    )

  def test_set_thiefnet_unlock(self) -> None:
    self.interface.set_thiefnet_unlock()
    self.assertEqual(
      self.interface._batch_read32(self.addr["thiefnet unlock"]), [1] * 24
    )
    self.reload()


class TestThiefNetTick(TickTestBase):
  state = "ep1_thiefnet"

  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.ctx.locations_info = {
      thiefnet_code(n): NetworkItem(item_dict[name].code, thiefnet_code(n), 1)
      for n, name in enumerate(SCOUTED, 1)
    }

  async def tick(self) -> None:
    await asyncio.wait_for(_handle_game_ready(self.ctx), 15.0)
    self.interface.clear_cache()

  def name_at(self, n: int, length: int = 64) -> tuple[str, str]:
    powerups = self.interface.addresses["text"]["powerups"][0]
    name_address, description_address = list(powerups.values())[n]
    return (
      self.pine.read_string(name_address, 32),
      self.pine.read_string(description_address, length)
    )

  async def test_ticks(self) -> None:
    await self.run_ticks()
    addresses = self.interface.addresses
    slot_data = self.ctx.slot_data
    assert slot_data is not None
    self.assertTrue(self.ctx.in_safehouse)
    self.assertEqual(
      self.interface._batch_read32(addresses["thiefnet unlock"]), [1] * 24
    )
    self.assertEqual(
      self.interface._batch_read32(addresses["thiefnet costs"]),
      slot_data["thiefnet_costs"]
    )
    for n in range(24):
      with self.subTest(n=n + 1):
        name, description = self.name_at(n)
        self.assertEqual(name, f"Check #{n + 1}")
        self.assertTrue(
          description.startswith(f"Tester's {SCOUTED[n]}"[:10]), description
        )
    self.assertEqual(self.ctx.sent_cmds("LocationChecks"), [])

    self.interface.load_powerups(PowerUps(trigger_bomb=True))
    await self.tick()
    await self.tick()
    sent = {
      code
      for message in self.ctx.sent_cmds("LocationChecks")
      for code in message["locations"]
    }
    self.assertEqual(sent, {thiefnet_code(1)})

    load_state(self.pine, "ep1_hub", 1, 2)
    self.interface.clear_cache()
    self.interface.load_powerups(PowerUps(trigger_bomb=True))
    await self.tick()
    await self.tick()
    self.assertFalse(self.ctx.in_safehouse)
    first = list(POWERUP_TEXT)[0]
    self.assertEqual(self.name_at(0, 256), (first, POWERUP_TEXT[first]))
    self.assertTrue(self.ctx.thiefnet_purchases.trigger_bomb)
    self.assertFalse(self.interface.read_powerups().trigger_bomb)
    self.assertIn(thiefnet_code(1), self.ctx.locations_checked)
