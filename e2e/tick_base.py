"""Base for tests that drive whole client ticks (prefetch, init, update)
against a savestate with the real poll-loop sleeps. Kept out of the
e2e_*.py modules so it is never collected on its own."""

import asyncio
import unittest
from contextlib import suppress
from types import SimpleNamespace
from typing import Any

from NetUtils import NetworkItem, NetworkPlayer, NetworkSlot, SlotType

from ..data.Items import item_dict
from ..data.Names import EpisodeName, progressive_episode
from ..Sly2Client import Sly2Context, _handle_game_ready
from ..Sly2Interface import Sly2Episode
from ..test.client_base import RecordingContext, make_slot_data
from .harness import ENABLED, connect, load_state

TICKS = 5


@unittest.skipUnless(ENABLED, "set SLY2_E2E=1 to run against PCSX2")
class TickTestBase(unittest.IsolatedAsyncioTestCase):
  state = "ep1_hub"
  episode = 1
  map_id = 2
  options: dict[str, Any] = {}

  async def asyncSetUp(self) -> None:
    self.pine = connect()
    load_state(self.pine, self.state, self.episode, self.map_id)
    self.ctx = RecordingContext()
    self.interface = self.ctx.game_interface
    self.interface.pcsx2_interface = self.pine
    self.interface.connect_to_game()
    self.ctx.slot = 1
    self.ctx.team = 0
    self.ctx.slot_info = {
      1: NetworkSlot("Tester", Sly2Context.game, SlotType.player)
    }
    self.ctx.consume_players_package([NetworkPlayer(0, 1, "Tester", "Tester")])
    self.ctx.slot_data = make_slot_data(**self.options)
    self.ctx.reset_world_state()
    self.ctx.items_received.append(
      NetworkItem(item_dict[
        progressive_episode(EpisodeName.THE_BLACK_CHATEAU)
      ].code, -1, 1)
    )
    self.ctx.server = SimpleNamespace()

  async def asyncTearDown(self) -> None:
    self.ctx.exit_event.set()
    task = getattr(self.ctx, "keep_alive_task", None)
    if task is not None:
      task.cancel()
      with suppress(asyncio.CancelledError):
        await task
    load_state(self.pine, self.state, self.episode, self.map_id)
    self.pine.disconnect()

  async def run_ticks(self) -> None:
    for _ in range(TICKS):
      await asyncio.wait_for(_handle_game_ready(self.ctx), 15.0)
      # A reload here means the client booted us out; loading a savestate
      # on top of a level transition has crashed PCSX2.
      self.interface.clear_cache()
      reloading = (
        self.ctx.is_loading or
        self.pine.read_int32(self.interface.addresses["reload"]) != 0
      )
      self.assertFalse(reloading, "the client triggered a reload")
    self.assertEqual(self.interface.refused_patches, set())
    self.assertEqual(self.ctx.current_episode, Sly2Episode(self.episode))
    self.assertEqual(self.ctx.current_map, self.map_id)
    self.assertFalse(self.ctx.is_loading)
    self.assertEqual(self.ctx.deaths, [])
    self.interface.clear_cache()
