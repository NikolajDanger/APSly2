from typing import Any
from unittest.mock import patch

from .. import Sly2Client
from ..data.Names import clockwerk_part
from .client_base import (
  CHARACTER,
  ClientTestBase,
  set_active_character
)


class CommandTestBase(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.cmd = Sly2Client.Sly2CommandProcessor(self.ctx)

  def run_scheduling(self, method: str) -> list[Any]:
    scheduled: list[Any] = []
    with patch.object(
      Sly2Client.Utils, "async_start",
      side_effect=lambda coro, *_a, **_k: scheduled.append(coro)
    ):
      getattr(self.cmd, method)()
    for coro in scheduled:
      coro.close()
    return scheduled


class TestLinkToggles(CommandTestBase):
  async def test_deathlink_toggles_and_notifies(self) -> None:
    self.ctx.death_link_enabled = False
    scheduled = self.run_scheduling("_cmd_deathlink")
    self.assertTrue(self.ctx.death_link_enabled)
    self.assertEqual(len(scheduled), 1)
    self.assertEqual(list(self.ctx.notification_queue), ["Deathlink enabled"])
    self.run_scheduling("_cmd_deathlink")
    self.assertFalse(self.ctx.death_link_enabled)

  async def test_ringlink_toggles_and_notifies(self) -> None:
    self.ctx.ring_link_enabled = False
    scheduled = self.run_scheduling("_cmd_ringlink")
    self.assertTrue(self.ctx.ring_link_enabled)
    self.assertEqual(len(scheduled), 1)
    self.assertEqual(list(self.ctx.notification_queue), ["Ringlink enabled"])
    self.run_scheduling("_cmd_ringlink")
    self.assertFalse(self.ctx.ring_link_enabled)


class TestThiefnetText(CommandTestBase):
  async def test_toggles_and_notifies(self) -> None:
    self.assertTrue(self.ctx.thiefnet_text_color)
    with patch.object(Sly2Client, "apply_thiefnet_text") as apply:
      self.cmd._cmd_thiefnet_text()
    self.assertFalse(self.ctx.thiefnet_text_color)
    apply.assert_called_once_with(self.ctx)
    self.assertEqual(
      list(self.ctx.notification_queue), ["ThiefNet text color turned off"]
    )
    with patch.object(Sly2Client, "apply_thiefnet_text"):
      self.cmd._cmd_thiefnet_text()
    self.assertTrue(self.ctx.thiefnet_text_color)


class TestNotification(CommandTestBase):
  async def test_queues_message(self) -> None:
    self.cmd._cmd_notification("hello there")
    self.assertEqual(list(self.ctx.notification_queue), ["hello there"])


class TestKill(CommandTestBase):
  async def test_kills_active_character(self) -> None:
    self.enter(1, 2)
    active = set_active_character(self.pine, self.addr)
    self.cmd._cmd_kill()
    self.assertEqual(self.pine.peek32(active + 0xdf4), 8)

  async def test_no_kill_on_title_screen(self) -> None:
    self.enter(0, 0)
    set_active_character(self.pine, self.addr)
    self.cmd._cmd_kill()
    self.assertEqual(self.pine.peek32(CHARACTER + 0xdf4), 0)


class TestMenu(CommandTestBase):
  async def test_triggers_reload(self) -> None:
    self.enter(1, 2)
    self.cmd._cmd_menu()
    self.assertEqual(self.pine.peek32(self.addr["reload"]), 1)


class TestClockwerkParts(CommandTestBase):
  options = {"goal": 6}

  async def test_counts_parts_and_requirements(self) -> None:
    self.slot_data["episode_8_keys"] = 1
    self.slot_data["required_keys_episode_8"] = 3
    self.slot_data["required_keys_goal"] = 5
    self.give(
      clockwerk_part("Feather"), clockwerk_part("Bone"),
      clockwerk_part("Screw")
    )
    with self.assertLogs("Client.Sly2", "INFO") as logs:
      self.cmd._cmd_clockwerk_parts()
    text = "\n".join(logs.output)
    self.assertIn("Clockwerk parts: 3", text)
    self.assertIn("unlock episode 8: 3", text)
    self.assertIn("Clockwerk Hunt goal: 5", text)


class TestSellValues(CommandTestBase):
  async def test_logs_loot_and_treasure_prices(self) -> None:
    with self.assertLogs("Client.Sly2", "INFO") as logs:
      self.cmd._cmd_sell_values()
    text = "\n".join(logs.output)
    self.assertIn("== Loot ==", text)
    self.assertIn("== Treasures ==", text)
    for loot, price in self.slot_data["loot_prices"].items():
      self.assertIn(f"{loot}: {price} coins", text)


class TestLootTables(CommandTestBase):
  async def test_plain_text_when_no_pickpocketing(self) -> None:
    self.slot_data["include_pickpocketing"] = False
    with self.assertLogs("Client.Sly2", "INFO") as logs:
      self.cmd._cmd_loot_tables()
    text = "\n".join(logs.output)
    for i in range(8):
      self.assertIn(f"== Episode {i+1} ==", text)

  async def test_json_lines_when_pickpocketing(self) -> None:
    self.slot_data["include_pickpocketing"] = True
    with self.assertLogs("Client.Sly2", "INFO") as logs:
      self.cmd._cmd_loot_tables()
    text = "\n".join(logs.output)
    for i in range(8):
      self.assertIn(f"== Episode {i+1} ==", text)


class TestGoal(CommandTestBase):
  def complete(self, *indices: int) -> None:
    for i in indices:
      self.pine.poke32(self.addr["operation completion"][i], 1)

  async def test_boss_goal(self) -> None:
    self.slot_data["goal"] = 0
    with self.assertLogs("Client.Sly2", "INFO") as logs:
      self.cmd._cmd_goal()
    self.assertIn("Goal: Beat Dimitri", "\n".join(logs.output))

  async def test_all_bosses(self) -> None:
    self.slot_data["goal"] = 5
    self.complete(0)
    with self.assertLogs("Client.Sly2", "INFO") as logs:
      self.cmd._cmd_goal()
    text = "\n".join(logs.output)
    self.assertIn("Goal: All Bosses", text)
    self.assertIn("Dimitri: X", text)
    self.assertIn("Rajan: \n", text + "\n")

  async def test_clockwerk_hunt(self) -> None:
    self.slot_data["goal"] = 6
    self.slot_data["required_keys_goal"] = 5
    self.ctx.clockwerk_parts_count = 4
    with self.assertLogs("Client.Sly2", "INFO") as logs:
      self.cmd._cmd_goal()
    text = "\n".join(logs.output)
    self.assertIn("Goal: Clockwerk Hunt", text)
    self.assertIn("Progress: 4/5 Clockwerk Parts", text)
