"""Whole client ticks against each savestate"""


from NetUtils import NetworkItem

from ..data.Items import item_dict
from .tick_base import TickTestBase


class TestTick(TickTestBase):
  async def test_ticks(self) -> None:
    await self.run_ticks()
    self.assertTrue(self.ctx.in_hub)
    self.assertTrue(self.interface.cave_live())
    self.assertEqual(self.interface.get_current_map(), 2)
    self.assertEqual(self.ctx.sent_cmds("LocationChecks"), [])


class TestEp8Tick(TickTestBase):
  state = "ep8_hub"
  episode = 8
  map_id = 38
  options = {"episode_8_keys": 4}

  async def test_ticks(self) -> None:
    self.ctx.items_received.append(
      NetworkItem(item_dict["Progressive Anatomy for Disaster"].code, -1, 1)
    )
    await self.run_ticks()
    self.assertTrue(self.ctx.in_hub)
    self.assertTrue(self.interface.cave_live())
    self.assertEqual(self.ctx.sent_cmds("LocationChecks"), [])


class TestTitleTick(TickTestBase):
  state = "title"
  episode = 0
  map_id = 0

  async def test_ticks(self) -> None:
    await self.run_ticks()
    addresses = self.interface.addresses
    self.assertEqual(self.pine.read_int8(addresses["episode unlocks"]), 8)
    self.assertEqual(
      self.pine.read_string(addresses["text"]["Press START (new)"], 64),
      "Connected to Archipelago server"
    )
    self.assertEqual(
      self.pine.read_int32(addresses["title start mask"]), 0x24050000
    )


class TestEpisodeMenuTick(TickTestBase):
  state = "episode_menu"
  episode = 0
  map_id = 1

  async def test_ticks(self) -> None:
    await self.run_ticks()
    addresses = self.interface.addresses
    self.assertEqual(self.pine.read_int8(addresses["episode unlocks"]), 8)
    labels = [
      self.pine.read_string(addresses["text"][f"Episode {n}"], 32)
      for n in range(1, 9)
    ]
    self.assertTrue(labels[0].startswith("Unlocked 1/"), labels)
    self.assertEqual(labels[1:7], ["Locked"] * 6)
    self.assertTrue(labels[7].endswith("Clockwerk parts"), labels)


class TestGradualMenuTick(TickTestBase):
  state = "episode_menu"
  episode = 0
  map_id = 1
  options = {"episode_8_keys": 3, "required_keys_episode_8": 8}

  async def test_ticks(self) -> None:
    await self.run_ticks()
    addresses = self.interface.addresses
    self.assertEqual(
      self.pine.read_string(addresses["text"]["Episode 8"], 64),
      "Parts required for section 1: 0/2"
    )
