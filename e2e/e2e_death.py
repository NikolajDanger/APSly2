"""Deathlink against the ep1_hub savestate: the cave-driven death, the
blunt fallback, and the client's handle_deathlink tick. Every death ends in
the game's own reload, which load_state waits out before restoring."""

import asyncio
import time
from typing import Callable


from ..Sly2Client import _handle_game_ready
from .harness import POLL_INTERVAL, E2ETestBase, load_state
from .tick_base import TickTestBase

DEAD_STATE = 8
REACTION_STATES = (1, 2, 4, 7, 9)
IDLE_STATE = 0xffffffff
# State 8 fades for ~10 s before the reload starts; the reload takes ~5 s.
RELOAD_TIMEOUT = 20.0
RESPAWN_TIMEOUT = 30.0


def wait_for(condition: Callable[[], bool], timeout: float) -> bool:
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    if condition():
      return True
    time.sleep(POLL_INTERVAL)
  return False


class TestDeath(E2ETestBase):
  state = "ep1_hub"
  episode = 1
  map_id = 2

  def tearDown(self) -> None:
    # Loading a savestate on top of a pending death transition has crashed
    # PCSX2, so wait for the game to finish the cycle first.
    if self.interface.get_current_episode() != 0:
      wait_for(self.settled, RELOAD_TIMEOUT + RESPAWN_TIMEOUT)
    self.reload()

  def settled(self) -> bool:
    self.interface.clear_cache()
    character = self.interface.get_active_character()
    return (
      character != 0 and
      self.pine.read_int32(character + 0xdf4) == IDLE_STATE and
      self.pine.read_int32(self.addr["loading"]) == 3
    )

  def fresh(self, read: Callable[[], object]) -> object:
    self.interface.clear_cache()
    return read()

  def dead(self) -> bool:
    return not self.fresh(self.interface.alive)

  def respawned(self) -> bool:
    return bool(self.fresh(self.interface.alive)) and (
      self.pine.read_int32(self.addr["loading"]) != 2
    )

  def assert_death_cycle(self) -> None:
    self.assertTrue(wait_for(self.dead, 2.0), "the player did not die")
    self.assertEqual(self.pine.read_int32(self.addr["health"]["Sly"]), 0)
    self.assertTrue(
      wait_for(self.respawned, RESPAWN_TIMEOUT), "the game did not respawn"
    )
    self.assertEqual(self.fresh(self.interface.get_current_map), 2)
    self.assertEqual(self.pine.read_int32(self.addr["health"]["Sly"]), 40)

  def test_cave_death(self) -> None:
    self.interface.install_cave()
    self.interface.clear_cache()
    self.assertTrue(self.interface.cave_live())
    character = self.interface.get_active_character()
    self.interface.kill_player()
    self.assertTrue(
      wait_for(
        lambda: self.pine.read_int32(self.addr["death flag"]) == 0, 1.0
      ),
      "the cave did not consume the death request"
    )
    self.assertTrue(wait_for(self.dead, 2.0), "the player did not die")
    self.assertIn(self.pine.read_int32(character + 0xdf4), REACTION_STATES)
    self.assertEqual(self.fresh(self.interface.get_damage_type), 0x200)
    self.assert_death_cycle()

  def reloading(self) -> bool:
    return self.pine.read_int32(self.addr["loading"]) == 2

  def test_blunt_death_without_cave(self) -> None:
    self.assertFalse(self.interface.cave_live())
    character = self.interface.get_active_character()
    self.interface.kill_player()
    self.assertEqual(self.pine.read_int32(character + 0xdf4), DEAD_STATE)
    # State 8 skips the reaction and goes straight to the map reload.
    self.assertTrue(
      wait_for(self.reloading, RELOAD_TIMEOUT), "the map did not reload"
    )
    self.assertTrue(
      wait_for(self.respawned, RESPAWN_TIMEOUT), "the game did not respawn"
    )
    self.assertEqual(self.fresh(self.interface.get_current_map), 2)

  def test_kill_refused_on_title(self) -> None:
    load_state(self.pine, "title", 0, 0)
    self.interface.clear_cache()
    before = self.pine.read_bytes(self.addr["death struct"], 16)
    self.interface.kill_player()
    self.assertEqual(self.pine.read_int32(self.addr["death flag"]), 0)
    self.assertEqual(
      self.pine.read_bytes(self.addr["death struct"], 16), before
    )


class TestDeathlinkTick(TickTestBase):
  """A queued deathlink kills the player on the next tick and the client
  does not echo that death back"""

  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.ctx.death_link_enabled = True
    self.ctx.queued_deaths = 1

  def settled(self) -> bool:
    self.interface.clear_cache()
    character = self.interface.get_active_character()
    return (
      character != 0 and self.interface.alive() and
      self.pine.read_int32(character + 0xdf4) == IDLE_STATE and
      self.pine.read_int32(self.interface.addresses["loading"]) == 3
    )

  async def asyncTearDown(self) -> None:
    wait_for(self.settled, RELOAD_TIMEOUT + RESPAWN_TIMEOUT)
    await super().asyncTearDown()

  async def test_ticks(self) -> None:
    for _ in range(3):
      await asyncio.wait_for(_handle_game_ready(self.ctx), 15.0)
    self.assertEqual(self.ctx.queued_deaths, 0)
    self.assertGreater(self.ctx.deathlink_timestamp, 0)
    self.interface.clear_cache()
    self.assertTrue(wait_for(lambda: not self.interface.alive(), 2.0))
    for _ in range(3):
      await asyncio.wait_for(_handle_game_ready(self.ctx), 15.0)
    self.assertEqual(self.ctx.deaths, [])
