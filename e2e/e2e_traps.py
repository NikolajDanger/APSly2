"""Trap effects against the ep1_hub savestate: every trap write read back,
the cave's negative coin payout (the Debt trap) and the client's timed-trap
lifecycle (fire on receipt, re-apply per tick, restore on expiry)."""

import asyncio
import struct
import time
from typing import Callable

from NetUtils import NetworkItem

from ..data.Constants import ALARM_INTERVAL, ALARM_SOUND_ID
from ..data.Items import Trap, item_dict
from ..Sly2Client import _handle_game_ready
from .harness import POLL_INTERVAL, E2ETestBase
from .tick_base import TickTestBase

DEFAULT_CLOCK = 1.0
DEFAULT_FRICTION = 1.5
DEFAULT_GADGET_POWER = 100
GUARD_TARGET = 0x1110
GUARD_REACH = 0x1100
GUARD_ALERT = 0x1114


def wait_for(condition: Callable[[], bool], timeout: float) -> bool:
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    if condition():
      return True
    time.sleep(POLL_INTERVAL)
  return False


class TestTraps(E2ETestBase):
  state = "ep1_hub"
  episode = 1
  map_id = 2

  def setUp(self) -> None:
    super().setUp()
    self.mutated = True

  def tearDown(self) -> None:
    if self.mutated:
      self.reload()

  def read_float(self, address: int) -> float:
    return struct.unpack("<f", self.pine.read_bytes(address, 4))[0]

  def test_defaults(self) -> None:
    self.mutated = False
    self.assertEqual(self.read_float(self.addr["clock speed"]), DEFAULT_CLOCK)
    self.assertEqual(self.read_float(self.addr["friction"]), DEFAULT_FRICTION)
    character = self.interface.get_active_character()
    self.assertEqual(
      self.pine.read_int32(character + 0xe00), self.addr["health"]["Sly"]
    )
    self.assertEqual(
      self.pine.read_int32(self.pine.read_int32(character + 0x12fc)),
      DEFAULT_GADGET_POWER
    )

  def test_clock_and_friction(self) -> None:
    self.interface.set_clock_speed(0.5)
    self.interface.set_friction(0.2)
    self.assertEqual(self.read_float(self.addr["clock speed"]), 0.5)
    self.assertAlmostEqual(
      self.read_float(self.addr["friction"]), 0.2, places=6
    )
    self.interface.set_clock_speed(DEFAULT_CLOCK)
    self.interface.set_friction(DEFAULT_FRICTION)
    self.assertEqual(self.read_float(self.addr["clock speed"]), DEFAULT_CLOCK)
    self.assertEqual(self.read_float(self.addr["friction"]), DEFAULT_FRICTION)

  def test_health_and_gadget_power(self) -> None:
    self.interface.set_current_health(1)
    self.assertEqual(self.pine.read_int32(self.addr["health"]["Sly"]), 1)
    self.interface.set_current_gadget_power(0)
    character = self.interface.get_active_character()
    self.assertEqual(
      self.pine.read_int32(self.pine.read_int32(character + 0x12fc)), 0
    )

  def test_alert_and_release_guards(self) -> None:
    character = self.interface.get_active_character()
    guards = list(self.interface._walk_guards())
    targeting = [
      g for g in guards
      if self.pine.read_int32(g + GUARD_TARGET) == character
    ]
    others = [g for g in guards if g not in targeting]
    self.assertGreater(len(targeting), 0)
    before = {
      g: self.pine.read_bytes(g + GUARD_REACH, 0x20) for g in others
    }
    self.interface.alert_guards()
    self.interface.clear_cache()
    for guard in targeting:
      self.assertEqual(self.pine.read_int32(guard + GUARD_REACH), 1)
      self.assertEqual(self.pine.read_int32(guard + GUARD_ALERT), 1)
    for guard, data in before.items():
      self.assertEqual(self.pine.read_bytes(guard + GUARD_REACH, 0x20), data)
    self.interface.release_guards()
    self.interface.clear_cache()
    for guard in targeting:
      self.assertEqual(self.pine.read_int32(guard + GUARD_REACH), 0)

  def paid_out(self) -> bool:
    self.interface.clear_cache()
    return not self.interface.coins_paying_out()

  def test_negative_payout(self) -> None:
    self.interface.install_cave()
    self.interface.clear_cache()
    self.assertTrue(self.interface.cave_live())
    coins = self.addr["coins"]
    self.pine.write_int32(coins, 100)
    self.assertTrue(self.interface.queue_coins(-25, 4))
    self.assertTrue(wait_for(self.paid_out, 2.0), "payout did not finish")
    self.assertEqual(self.pine.read_int32(coins), 75)
    self.assertEqual(self.pine.read_int32(self.addr["coin amount"]), 0)

  def test_negative_payout_floors_at_zero(self) -> None:
    self.interface.install_cave()
    self.interface.clear_cache()
    coins = self.addr["coins"]
    self.pine.write_int32(coins, 10)
    self.assertTrue(self.interface.queue_coins(-50, 3))
    self.assertTrue(wait_for(self.paid_out, 2.0), "payout did not finish")
    self.assertEqual(self.pine.read_int32(coins), 0)


class TestTrapTick(TickTestBase):
  """Traps received after connecting fire, re-apply and expire"""

  def read_float(self, address: int) -> float:
    return struct.unpack("<f", self.pine.read_bytes(address, 4))[0]

  async def tick(self) -> None:
    await asyncio.wait_for(_handle_game_ready(self.ctx), 15.0)
    self.interface.clear_cache()

  async def test_ticks(self) -> None:
    await self.run_ticks()
    addresses = self.interface.addresses
    self.ctx.items_received.extend(
      NetworkItem(item_dict[name].code, -1, 1)
      for name in (
        Trap.SLOW_MO.item_name, Trap.ICE.item_name, Trap.SLY_1.item_name,
        Trap.NOISE.item_name
      )
    )
    await self.tick()
    await self.tick()
    self.assertEqual(
      set(self.ctx.active_traps), {Trap.SLOW_MO, Trap.ICE, Trap.NOISE}
    )
    self.assertEqual(self.read_float(addresses["clock speed"]), 0.5)
    self.assertAlmostEqual(
      self.read_float(addresses["friction"]), 0.2, places=6
    )
    self.assertEqual(self.pine.read_int32(addresses["health"]["Sly"]), 1)
    self.assertTrue(self.interface.sound_playing())
    self.assertEqual(
      self.pine.read_int32(addresses["sound id"]), ALARM_SOUND_ID
    )
    self.assertEqual(
      self.pine.read_int32(addresses["sound interval"]), ALARM_INTERVAL
    )

    self.pine.write_float(addresses["clock speed"], DEFAULT_CLOCK)
    await self.tick()
    self.assertEqual(self.read_float(addresses["clock speed"]), 0.5)

    for trap in list(self.ctx.active_traps):
      self.ctx.active_traps[trap] = time.time() - 1
    await self.tick()
    self.assertEqual(self.ctx.active_traps, {})
    self.assertEqual(self.read_float(addresses["clock speed"]), DEFAULT_CLOCK)
    self.assertEqual(self.read_float(addresses["friction"]), DEFAULT_FRICTION)
    self.interface.clear_cache()
    self.assertFalse(self.interface.sound_playing())

  async def test_debt_trap(self) -> None:
    self.ctx.ring_link_enabled = True
    await self.run_ticks()
    coins = self.interface.get_coins()
    self.assertEqual(self.ctx.prev_coins, coins)
    self.ctx.items_received.append(
      NetworkItem(item_dict[Trap.DEBT.item_name].code, -1, 1)
    )
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
      await self.tick()
      if (
        self.ctx.pending_debt_traps == 0 and
        not self.interface.coins_paying_out()
      ):
        break
      time.sleep(POLL_INTERVAL)
    slot_data = self.ctx.slot_data
    assert slot_data is not None
    loss = coins * slot_data["debt_trap_percentage"] // 100
    self.assertGreater(loss, 0)
    self.assertEqual(self.interface.get_coins(), coins - loss)
    await self.tick()
    await self.tick()
    self.assertEqual(self.ctx.sent_cmds("Bounce"), [])
    self.assertEqual(self.ctx.prev_coins, coins - loss)
