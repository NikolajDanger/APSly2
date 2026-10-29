"""Trap effects against the ep1_hub savestate: every trap write read back,
the cave's negative coin payout (the Debt trap) and the client's timed-trap
lifecycle (fire on receipt, re-apply per tick, restore on expiry)."""

import asyncio
import struct
import time
from typing import Callable

from NetUtils import NetworkItem

from ..data.Constants import (
  ALARM_INTERVAL,
  ALARM_SOUND_ID,
  CAVE_HYPNOSIS_VJOY,
  HYPNOSIS_SITE,
)
from ..data.Items import Trap, item_dict
from ..HypnosisInstall import (
  DRAW_IN_FRONT, OVERLAY_OBJECT_ID, PAD_MASK, STATE_MASK, STATE_OVERLAY,
  STATE_PACE_ON, STATE_VOICE
)
from ..LootInstall import HIDDEN_FLAG
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


class TestHypnosis(E2ETestBase):
  """The Hypnosis trap built in the Paris hub: the cave's vjoy hook,
  the overlay stepped by the cave, the walk, eyes and sound, and the
  restore"""
  state = "ep1_hub"
  episode = 1
  map_id = 2

  def setUp(self) -> None:
    super().setUp()
    self.mutated = True

  def tearDown(self) -> None:
    if self.mutated:
      self.reload()

  def overlay_state(self) -> int:
    obj = self.interface.hypnosis_installer.overlay
    assert obj is not None
    return self.pine.read_int32(obj + 0x58)

  def test_on_and_off(self) -> None:
    self.interface.install_cave()
    hook = 0x0C000000 | (CAVE_HYPNOSIS_VJOY >> 2)
    self.assertTrue(
      wait_for(lambda: self.pine.read_int32(HYPNOSIS_SITE) == hook, 2.0),
      "the vjoy fill was not hooked"
    )
    self.interface.clear_cache()
    entity = self.interface.get_active_character()
    installer = self.interface.hypnosis_installer
    self.assertTrue(self.interface.apply_hypnosis())
    obj = installer.overlay
    assert obj is not None
    self.assertEqual(self.pine.read_int32(obj + 0xC), 0x2DAF30)
    self.assertEqual(self.pine.read_int32(obj + 0x18), OVERLAY_OBJECT_ID)
    state = self.addr["hypnosis state"]
    self.assertEqual(self.pine.read_int32(state + STATE_PACE_ON), 1)
    self.assertEqual(self.pine.read_int32(state + STATE_MASK), PAD_MASK)
    self.assertEqual(self.pine.read_int32(state + STATE_OVERLAY), obj)
    self.assertTrue(
      wait_for(lambda: self.overlay_state() == 2, 2.0),
      "the cave never moved the overlay on to its loop"
    )
    # The loop is restarted before its last key, never left
    time.sleep(2.5)
    self.assertEqual(self.overlay_state(), 2)
    self.assertNotEqual(self.pine.read_int32(state + STATE_VOICE), 0)
    character = installer.active
    assert character is not None
    for slot, _, new in character.swaps:
      self.assertEqual(self.pine.read_int32(slot), new)
    self.assertEqual(len(character.eyes), 2)
    for entry in character.eyes:
      self.assertEqual(self.pine.read_int32(entry + 0xC) & HIDDEN_FLAG, 0)
    self.assertTrue(self.pine.read_int32(entity + 0xD4) & DRAW_IN_FRONT)
    self.assertGreaterEqual(len(character.front), 1)

    self.interface.end_hypnosis()
    self.assertTrue(
      wait_for(lambda: self.overlay_state() == 1, 2.0),
      "the cave never moved the overlay back to idle"
    )
    self.assertEqual(self.pine.read_int32(state + STATE_PACE_ON), 0)
    self.assertEqual(self.pine.read_int32(state + STATE_MASK), 0)
    self.assertEqual(self.pine.read_int32(state + STATE_VOICE), 0)
    for slot, old, _ in character.swaps:
      self.assertEqual(self.pine.read_int32(slot), old)
    for entry in character.eyes:
      self.assertTrue(self.pine.read_int32(entry + 0xC) & HIDDEN_FLAG)
    self.assertFalse(self.pine.read_int32(entity + 0xD4) & DRAW_IN_FRONT)


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

  async def test_hypnosis_trap(self) -> None:
    await self.run_ticks()
    self.ctx.items_received.append(
      NetworkItem(item_dict[Trap.HYPNOSIS.item_name].code, -1, 1)
    )
    await self.tick()
    await self.tick()
    expiry = self.ctx.active_traps[Trap.HYPNOSIS]
    self.assertLess(expiry, time.time() + 20)
    installer = self.interface.hypnosis_installer
    self.assertIsNotNone(installer.active)
    obj = installer.overlay
    assert obj is not None
    self.assertTrue(
      wait_for(lambda: self.pine.read_int32(obj + 0x58) == 2, 2.0)
    )
    self.ctx.active_traps[Trap.HYPNOSIS] = time.time() - 1
    await self.tick()
    self.assertEqual(self.ctx.active_traps, {})
    self.assertIsNone(installer.active)
    self.assertTrue(
      wait_for(lambda: self.pine.read_int32(obj + 0x58) == 1, 2.0)
    )

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
