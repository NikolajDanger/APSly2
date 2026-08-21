import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from NetUtils import ClientStatus, NetworkItem

from .. import Callbacks, Sly2Client
from ..Callbacks import (
  activate_trap,
  check_clockla,
  check_jobs,
  compute_available_episodes,
  dynamic_loot_odds,
  episode_loot,
  fix_jobs,
  fix_mega_jump,
  handle_check_goal,
  handle_checks,
  handle_deathlink,
  handle_episode_hint,
  handle_notifications,
  handle_received,
  handle_ring_link,
  handle_traps,
  init,
  loot_odds_row,
  reset_traps,
  set_jobs,
  set_thiefnet,
  update
)
from ..data.Constants import (
  DEATH_HOOK_JAL,
  DEATH_HOOK_ORIG0,
  EPISODES,
  LOOT,
  LOOT_IDS,
  MEGA_JUMP_GADGET_ID,
  MEGA_JUMP_UNLOAD_CALL,
  PICKPOCKET_LOOT_TABLE_CHANCES,
  POWERUP_TEXT,
  episode_key
)
from ..data.Items import Trap, item_dict
from ..data.Locations import location_dict
from ..Sly2Client import _handle_game_ready
from ..Sly2Interface import PowerUps, Sly2Episode
from .client_base import (
  ClientTestBase,
  build_dag,
  dag_node,
  job_status,
  make_guard_list,
  set_active_character,
  set_infobox_pointers,
  set_job_status,
  set_parents,
  set_string_table,
  string_buffer
)

WIRE_LOOT = json.loads(json.dumps(LOOT))
EPISODE_NAMES = list(EPISODES)
EP8 = Sly2Episode.Anatomy_for_Disaster
CLOCKWERK_PARTS = [
  name for name, item in item_dict.items()
  if item.category == "Clockwerk Part"
]


def pickpocket_codes(names: list[str]) -> set[int]:
  return {location_dict[f"Pickpocket {n}"].code for n in names}


class TestLootHelpers(unittest.TestCase):
  def test_episode_loot_needs_wire_shape(self) -> None:
    for i in range(8):
      for j in range(2):
        self.assertEqual(len(episode_loot(WIRE_LOOT, i, j)), 6, (i, j))
        self.assertEqual(episode_loot(LOOT, i, j), [])

  def test_dynamic_odds_unchanged_cases(self) -> None:
    base = PICKPOCKET_LOOT_TABLE_CHANCES[49]
    names = episode_loot(WIRE_LOOT, 0, 0)
    self.assertEqual(dynamic_loot_odds(WIRE_LOOT, set(), 0, 0, base), base)
    self.assertEqual(
      dynamic_loot_odds(WIRE_LOOT, pickpocket_codes(names), 0, 0, base), base
    )
    partial = {k: v for k, v in WIRE_LOOT.items() if k != names[0]}
    self.assertEqual(
      dynamic_loot_odds(partial, pickpocket_codes(names[1:2]), 0, 0, base),
      base
    )

  def test_dynamic_odds_invariants(self) -> None:
    for distribution in (0, 9, 49, 99):
      base = PICKPOCKET_LOOT_TABLE_CHANCES[distribution]
      for i in range(8):
        for j in range(2):
          names = episode_loot(WIRE_LOOT, i, j)
          for k in range(1, 6):
            checked = pickpocket_codes(names[:k])
            odds = dynamic_loot_odds(WIRE_LOOT, checked, i, j, base)
            context = (distribution, i, j, k)
            self.assertEqual(sum(odds), 100, context)
            self.assertTrue(all(o >= 1 for o in odds), context)
            for n, (o, b) in enumerate(zip(odds, base)):
              if n < k:
                self.assertLessEqual(o, b, context)
              else:
                self.assertGreaterEqual(o, b, context)


class TestLootOddsRow(ClientTestBase):
  def test_static(self) -> None:
    self.slot_data["loot_table_distribution"] = 10
    self.slot_data["dynamic_loot_tables"] = False
    self.ctx.checked_locations = pickpocket_codes(
      episode_loot(WIRE_LOOT, 0, 0)[:2]
    )
    self.assertEqual(
      loot_odds_row(self.ctx, 0, 0), PICKPOCKET_LOOT_TABLE_CHANCES[9]
    )

  def test_dynamic_uses_both_checked_sets(self) -> None:
    self.slot_data["loot_table_distribution"] = 50
    self.slot_data["dynamic_loot_tables"] = True
    base = PICKPOCKET_LOOT_TABLE_CHANCES[49]
    names = episode_loot(WIRE_LOOT, 0, 0)
    self.assertEqual(loot_odds_row(self.ctx, 0, 0), base)
    self.ctx.checked_locations = pickpocket_codes(names[:1])
    self.ctx.locations_checked = pickpocket_codes(names[1:2])
    self.assertEqual(
      loot_odds_row(self.ctx, 0, 0),
      dynamic_loot_odds(WIRE_LOOT, pickpocket_codes(names[:2]), 0, 0, base)
    )


class TestAvailableEpisodes(ClientTestBase):
  def available(self) -> dict:
    return compute_available_episodes(self.ctx)

  def parts(self, n: int) -> None:
    self.give(*CLOCKWERK_PARTS[:n])

  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.slot_data["required_keys_episode_8"] = 8

  def test_no_slot_data(self) -> None:
    self.ctx.slot_data = None
    self.assertEqual(self.available(), {e: 0 for e in Sly2Episode})

  def test_progressive_episodes(self) -> None:
    self.give("Progressive The Black Chateau", "Progressive The Black Chateau")
    self.give("Progressive Menace from the North, Eh!")
    available = self.available()
    self.assertEqual(available[Sly2Episode.The_Black_Chateau], 2)
    self.assertEqual(available[Sly2Episode.Menace_from_the_North_Eh], 1)
    self.assertEqual(available[Sly2Episode.Jailbreak], 0)

  def test_off(self) -> None:
    self.slot_data["episode_8_keys"] = 4
    self.parts(8)
    self.assertEqual(self.available()[EP8], 0)
    self.give(*["Progressive Anatomy for Disaster"]*4)
    self.assertEqual(self.available()[EP8], 4)

  def test_first_section(self) -> None:
    self.slot_data["episode_8_keys"] = 0
    self.give("Progressive Anatomy for Disaster")
    self.parts(7)
    self.assertEqual(self.available()[EP8], 0)
    self.parts(8)
    self.assertEqual(self.available()[EP8], 2)

  def test_whole_episode(self) -> None:
    self.slot_data["episode_8_keys"] = 2
    self.parts(7)
    self.assertEqual(self.available()[EP8], 0)
    self.parts(8)
    self.assertEqual(self.available()[EP8], 4)

  def test_gradual_sections(self) -> None:
    self.slot_data["episode_8_keys"] = 3
    for parts, expected in [(0, 0), (1, 0), (2, 1), (4, 2), (6, 3), (8, 4)]:
      self.ctx.items_received = []
      self.parts(parts)
      self.assertEqual(self.available()[EP8], expected, parts)

  def test_last_section(self) -> None:
    self.slot_data["episode_8_keys"] = 1
    self.give(*["Progressive Anatomy for Disaster"]*3)
    self.assertEqual(self.available()[EP8], 3)
    self.parts(8)
    self.assertEqual(self.available()[EP8], 4)
    self.ctx.items_received = []
    self.give(*["Progressive Anatomy for Disaster"]*2)
    self.parts(8)
    self.assertEqual(self.available()[EP8], 2)


class TestHandleReceived(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.enter(1, 2)

  async def test_powerups(self) -> None:
    self.give("Paraglider", "Mega Jump")
    await handle_received(self.ctx, False)
    self.assertTrue(self.ctx.powerups.paraglide)
    self.assertTrue(self.ctx.powerups.mega_jump)
    self.assertEqual(self.interface.read_powerups(), self.ctx.powerups)
    self.assertEqual(self.ctx.inventory[item_dict["Paraglider"].code], 1)

  async def test_powerups_not_written_in_safehouse(self) -> None:
    self.give("Paraglider")
    self.ctx.in_safehouse = True
    await handle_received(self.ctx, True)
    self.assertTrue(self.ctx.powerups.paraglide)
    self.assertEqual(self.interface.read_powerups(), PowerUps())

  async def test_bottles(self) -> None:
    self.give(
      "Bottle - The Black Chateau",
      "5 bottles - Menace from the North, Eh!",
      "Bottle - The Black Chateau"
    )
    await handle_received(self.ctx, False)
    self.assertEqual(self.ctx.all_bottles[Sly2Episode.The_Black_Chateau], 2)
    self.assertEqual(
      self.ctx.all_bottles[Sly2Episode.Menace_from_the_North_Eh], 5
    )

  async def test_notifications_from_high_water(self) -> None:
    self.give("Paraglider", "Clockwerk Beak", "Progressive Jailbreak")
    self.pine.poke32(self.addr["items received"], 2)
    await handle_received(self.ctx, False)
    self.assertEqual(
      list(self.ctx.notification_queue),
      ["Received Progressive Jailbreak from Tester"]
    )
    self.assertEqual(self.ctx.notified_items, 3)
    self.assertEqual(self.interface.read_items_received(), 3)
    self.assertEqual(self.ctx.clockwerk_parts_count, 1)
    self.assertEqual(
      self.ctx.available_episodes[Sly2Episode.Jailbreak], 1
    )

    await handle_received(self.ctx, False)
    self.assertEqual(len(self.ctx.notification_queue), 1)

  async def test_clockwerk_count_on_reconnect(self) -> None:
    self.give("Clockwerk Beak", "Clockwerk Skull")
    self.pine.poke32(self.addr["items received"], 2)
    await handle_received(self.ctx, False)
    self.assertEqual(self.ctx.clockwerk_parts_count, 2)
    self.assertEqual(len(self.ctx.notification_queue), 0)

  async def test_coins(self) -> None:
    self.pine.poke32(self.addr["coins"], 10)
    self.give("Coins", "Coins")
    self.pine.poke32(self.addr["items received"], 1)
    with patch.object(Callbacks, "randint", return_value=40) as randint:
      await handle_received(self.ctx, False)
    randint.assert_called_once_with(
      self.slot_data["coins_minimum"], self.slot_data["coins_maximum"]
    )
    self.assertEqual(self.interface.get_coins(), 50)

  async def test_trap_baseline_skips_backlog(self) -> None:
    self.give("Slow-mo Trap")
    self.ctx.trap_baseline_pending = True
    with patch.object(Callbacks, "time", return_value=1000.0):
      await handle_received(self.ctx, False)
    self.assertFalse(self.ctx.trap_baseline_pending)
    self.assertEqual(self.ctx.active_traps, {})
    self.assertEqual(self.ctx.trap_cursor, 1)

    self.give("Ice Trap")
    with patch.object(Callbacks, "time", return_value=1000.0):
      await handle_received(self.ctx, False)
    self.assertEqual(self.ctx.active_traps, {Trap.ICE: 1020.0})
    self.assertEqual(self.ctx.trap_cursor, 2)

  async def test_traps_wait_for_safehouse_exit(self) -> None:
    self.give("Ice Trap")
    with patch.object(Callbacks, "time", return_value=1000.0):
      await handle_received(self.ctx, True)
    self.assertEqual(self.ctx.active_traps, {})
    self.assertEqual(self.ctx.trap_cursor, 0)
    with patch.object(Callbacks, "time", return_value=1000.0):
      await handle_received(self.ctx, False)
    self.assertIn(Trap.ICE, self.ctx.active_traps)


class TestHandleChecks(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.enter(1, 2)

  def sent_locations(self) -> list[set[int]]:
    return [set(m["locations"]) for m in self.ctx.sent_cmds("LocationChecks")]

  async def test_nothing_new_sends_nothing(self) -> None:
    await handle_checks(self.ctx)
    self.assertEqual(self.ctx.sent, [])

  async def test_thiefnet(self) -> None:
    self.ctx.thiefnet_purchases = PowerUps(snooze_bomb=True)
    await handle_checks(self.ctx)
    self.assertEqual(self.sent_locations(), [{self.loc("ThiefNet 03")}])

  async def test_thiefnet_reread_in_safehouse(self) -> None:
    self.ctx.in_safehouse = True
    self.interface.load_powerups(PowerUps(paraglide=True, mega_jump=True))
    await handle_checks(self.ctx)
    self.assertEqual(self.sent_locations(), [{self.loc("ThiefNet 21")}])

  async def test_bottle_bundles(self) -> None:
    self.slot_data["bottle_location_bundle_size"] = 5
    self.slot_data["bottlesanity"] = False
    self.pine.poke32(self.addr["bottle flags"][0], (1 << 12) - 1)
    self.pine.poke32(self.addr["bottle flags"][6], (1 << 30) - 1)
    await handle_checks(self.ctx)
    expected = {
      self.loc("The Black Chateau - 05 bottles collected"),
      self.loc("The Black Chateau - 10 bottles collected"),
    } | {
      self.loc(f"Menace from the North, Eh! - {i:02} bottles collected")
      for i in range(5, 31, 5)
    }
    self.assertEqual(self.sent_locations(), [expected])

  async def test_bottlesanity(self) -> None:
    self.slot_data["bottle_location_bundle_size"] = 1
    self.slot_data["bottlesanity"] = True
    self.pine.poke32(self.addr["bottle flags"][3], 1 << 29)
    await handle_checks(self.ctx)
    self.assertEqual(
      self.sent_locations(), [{self.loc("Jailbreak - Bottle #01")}]
    )

  async def test_jobs(self) -> None:
    self.ctx.jobs_completed[0][1][2] = True
    self.ctx.jobs_completed[7][3][0] = True
    await handle_checks(self.ctx)
    self.assertEqual(self.sent_locations(), [{
      self.loc("The Black Chateau - Waterpump Destruction"),
      self.loc("Anatomy for Disaster - Carmelita's Gunner/Defeat Clock-la")
    }])

  async def test_treasures_loot_vaults(self) -> None:
    self.pine.poke32(self.addr["treasures"][2][1], 1)
    self.pine.poke32(self.addr["loot"][list(LOOT).index("Gold Ring")], 1)
    self.ctx.vaults[5] = True
    await handle_checks(self.ctx)
    treasure = f"{EPISODE_NAMES[2]} - Golden Scroll Case"
    self.assertEqual(self.sent_locations(), [{
      self.loc(treasure),
      self.loc("Pickpocket Gold Ring"),
      self.loc(f"{EPISODE_NAMES[5]} - Vault")
    }])

  async def test_only_new_locations_trigger_send(self) -> None:
    self.ctx.vaults[0] = True
    await handle_checks(self.ctx)
    await handle_checks(self.ctx)
    self.assertEqual(len(self.ctx.sent_cmds("LocationChecks")), 1)
    self.ctx.vaults[1] = True
    await handle_checks(self.ctx)
    sent = self.sent_locations()
    self.assertEqual(len(sent), 2)
    self.assertEqual(
      sent[1],
      {self.loc(f"{EPISODE_NAMES[0]} - Vault"),
        self.loc(f"{EPISODE_NAMES[1]} - Vault")}
    )
    self.assertEqual(self.ctx.last_checked_locations, sent[1])


class TestHandleCheckGoal(ClientTestBase):
  def goaled(self) -> bool:
    return any(
      m["status"] == ClientStatus.CLIENT_GOAL
      for m in self.ctx.sent_cmds("StatusUpdate")
    )

  def complete(self, *indices: int) -> None:
    for i in indices:
      self.pine.poke32(self.addr["operation completion"][i], 1)

  def open_vaults(self, n: int) -> None:
    for address in self.addr["vaults"][:n]:
      self.pine.poke32(address, 1)

  async def test_boss_goals(self) -> None:
    for goal, index in enumerate([0, 2, 4, 6, 7]):
      self.slot_data["goal"] = goal
      self.ctx.sent.clear()
      self.ctx.goal_sent = False
      await handle_check_goal(self.ctx)
      self.assertFalse(self.goaled(), goal)
      self.complete(index)
      await handle_check_goal(self.ctx)
      self.assertTrue(self.goaled(), goal)

  async def test_goal_sent_once(self) -> None:
    self.slot_data["goal"] = 0
    self.complete(0)
    await handle_check_goal(self.ctx)
    await handle_check_goal(self.ctx)
    self.assertEqual(len(self.ctx.sent_cmds("StatusUpdate")), 1)
    self.ctx.reset_world_state()
    await handle_check_goal(self.ctx)
    self.assertEqual(len(self.ctx.sent_cmds("StatusUpdate")), 2)

  async def test_clockwerk_hunt(self) -> None:
    self.slot_data["goal"] = 6
    self.slot_data["required_keys_goal"] = 5
    self.ctx.clockwerk_parts_count = 4
    await handle_check_goal(self.ctx)
    self.assertFalse(self.goaled())
    self.ctx.clockwerk_parts_count = 5
    await handle_check_goal(self.ctx)
    self.assertTrue(self.goaled())

  async def test_all_vaults(self) -> None:
    self.slot_data["goal"] = 7
    self.open_vaults(7)
    await handle_check_goal(self.ctx)
    self.assertFalse(self.goaled())
    self.open_vaults(8)
    await handle_check_goal(self.ctx)
    self.assertTrue(self.goaled())

  async def test_pick_and_mix(self) -> None:
    self.slot_data["goal"] = 8
    self.slot_data["required_keys_goal"] = 3
    self.slot_data["pick_and_mix"] = {
      episode_key(EPISODE_NAMES[1]): 1,
      "clockwerk_hunt": 1,
      "all_vaults": 1
    }
    self.complete(1)
    self.ctx.clockwerk_parts_count = 3
    self.open_vaults(7)
    await handle_check_goal(self.ctx)
    self.assertFalse(self.goaled())
    self.open_vaults(8)
    self.ctx.clockwerk_parts_count = 2
    await handle_check_goal(self.ctx)
    self.assertFalse(self.goaled())
    self.ctx.clockwerk_parts_count = 3
    self.pine.poke32(self.addr["operation completion"][1], 0)
    await handle_check_goal(self.ctx)
    self.assertFalse(self.goaled())
    self.complete(1)
    await handle_check_goal(self.ctx)
    self.assertTrue(self.goaled())


class TestHandleDeathlink(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.enter(1, 2)
    self.ctx.death_link_enabled = True
    self.active = set_active_character(self.pine, self.addr)
    # Pretend the cave is installed so kill_player takes the animated path.
    self.pine.poke32(self.addr["death hook"], DEATH_HOOK_JAL)

  async def run_at(self, now: float) -> None:
    with patch.object(Callbacks, "time", return_value=now):
      await handle_deathlink(self.ctx)

  async def test_disabled(self) -> None:
    self.ctx.death_link_enabled = False
    self.ctx.queued_deaths = 1
    await self.run_at(1000.0)
    self.assertFalse(self.pine.written(self.addr["death flag"]))

  async def test_queued_death_kills(self) -> None:
    self.ctx.queued_deaths = 2
    self.ctx.deathlink_timestamp = 990.0
    await self.run_at(1000.0)
    self.assertFalse(self.pine.written(self.addr["death flag"]))
    await self.run_at(1011.0)
    self.assertEqual(self.pine.peek32(self.addr["death flag"]), 1)
    struct_addr = self.addr["death struct"]
    self.assertEqual(self.pine.peek32(struct_addr + 0x08), self.active)
    self.assertEqual(self.pine.peek32(struct_addr + 0x0c), 0x200)
    self.assertEqual(self.ctx.queued_deaths, 0)
    self.assertEqual(self.ctx.deathlink_timestamp, 1011.0)

  async def test_fallback_without_cave(self) -> None:
    # Cave not installed -> blunt kill so the death is not lost.
    self.pine.poke32(self.addr["death hook"], DEATH_HOOK_ORIG0)
    self.ctx.queued_deaths = 1
    self.ctx.deathlink_timestamp = 990.0
    await self.run_at(1011.0)
    self.assertEqual(self.pine.peek32(self.active + 0xdf4), 8)
    self.assertFalse(self.pine.written(self.addr["death flag"]))

  async def test_death_sent_with_cause(self) -> None:
    self.pine.poke32(self.addr["health"]["Sly"], 0)
    self.pine.poke32(self.active + 0xe2c, 0x400)
    await self.run_at(1000.0)
    self.assertEqual(self.ctx.deaths, ["Tester was flattened"])
    self.assertEqual(self.ctx.deathlink_timestamp, 1000.0)
    await self.run_at(1005.0)
    self.assertEqual(len(self.ctx.deaths), 1)

  async def test_unknown_cause(self) -> None:
    self.pine.poke32(self.addr["health"]["Sly"], 0)
    await self.run_at(1000.0)
    self.assertEqual(self.ctx.deaths, ["Tester died"])


class TestHandleRingLink(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.ctx.ring_link_enabled = True
    self.pine.poke32(self.addr["coins"], 100)

  def bounces(self) -> list[int]:
    return [m["data"]["amount"] for m in self.ctx.sent_cmds("Bounce")]

  async def test_disabled(self) -> None:
    self.ctx.ring_link_enabled = False
    await handle_ring_link(self.ctx)
    self.assertIsNone(self.ctx.prev_coins)

  async def test_baseline_then_diff(self) -> None:
    await handle_ring_link(self.ctx)
    self.assertEqual(self.ctx.prev_coins, 100)
    self.assertEqual(self.bounces(), [])
    self.pine.poke32(self.addr["coins"], 130)
    await handle_ring_link(self.ctx)
    self.assertEqual(self.bounces(), [30])
    self.assertEqual(self.ctx.prev_coins, 130)
    await handle_ring_link(self.ctx)
    self.assertEqual(self.bounces(), [30])

  async def test_pending_applied_without_echo(self) -> None:
    await handle_ring_link(self.ctx)
    self.ctx.pending_ring_link = -150
    await handle_ring_link(self.ctx)
    self.assertEqual(self.interface.get_coins(), 0)
    self.assertEqual(self.ctx.pending_ring_link, 0)
    self.assertEqual(self.ctx.prev_coins, 0)
    self.assertEqual(self.bounces(), [])


class TestHandleNotifications(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.enter(1, 2)
    set_string_table(self.pine, self.addr, 1)
    set_infobox_pointers(self.pine, self.addr)
    self.infobox = self.pine.peek32(self.addr["infobox"])
    self.ctx.notification("hello")

  async def run_at(self, now: float) -> None:
    with patch.object(Callbacks, "time", return_value=now):
      await handle_notifications(self.ctx)

  def shown_text(self) -> bytes:
    return self.pine.peek_cstring(
      string_buffer(self.pine, self.addr, "infobox", 1)
    )

  async def test_shows_queued_notification(self) -> None:
    await self.run_at(1000.0)
    self.assertTrue(self.ctx.showing_notification)
    self.assertEqual(self.ctx.notification_timestamp, 1000.0)
    self.assertEqual(len(self.ctx.notification_queue), 0)
    self.assertEqual(self.shown_text(), b" "*10 + b"hello")
    self.assertEqual(self.pine.peek32(self.infobox + 0x64), 2)

  async def test_holds_for_ten_seconds(self) -> None:
    await self.run_at(1000.0)
    self.ctx.notification("second")
    await self.run_at(1005.0)
    self.assertEqual(len(self.ctx.notification_queue), 1)
    await self.run_at(1011.0)
    self.assertEqual(len(self.ctx.notification_queue), 0)
    self.assertEqual(self.shown_text(), b" "*10 + b"second")

  async def test_waits_for_game_infobox(self) -> None:
    self.pine.poke32(self.infobox + 0x64, 2)
    self.pine.poke32(self.addr["infobox string"], 42)
    await self.run_at(1000.0)
    self.assertFalse(self.ctx.showing_notification)
    self.assertEqual(len(self.ctx.notification_queue), 1)

  async def test_not_in_cutscene(self) -> None:
    self.pine.poke16(self.addr["frame counter"], 50)
    await self.run_at(1000.0)
    self.assertEqual(len(self.ctx.notification_queue), 1)

  async def test_only_in_hub(self) -> None:
    self.enter(1, 3)
    await self.run_at(1000.0)
    self.assertFalse(self.ctx.showing_notification)
    self.assertEqual(len(self.ctx.notification_queue), 1)
    self.assertEqual(self.pine.peek32(self.infobox + 0x64), 1)


class TestSetJobs(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    build_dag(self.pine, self.addr)

  def statuses(self, jobs: list) -> list[int]:
    return [job_status(self.pine, j) for j in jobs]

  async def test_chapter_gating(self) -> None:
    self.enter(1, 2)
    jobs = self.addr["jobs"][0]
    for job in jobs[1] + jobs[2]:
      set_job_status(self.pine, job, 1)
    self.ctx.available_episodes[Sly2Episode.The_Black_Chateau] = 1
    set_jobs(self.ctx)
    self.assertEqual(self.statuses(jobs[0]), [1, 1])
    self.assertEqual(self.statuses(jobs[1] + jobs[2]), [0]*7)

    self.ctx.available_episodes[Sly2Episode.The_Black_Chateau] = 3
    set_jobs(self.ctx)
    self.assertEqual(self.statuses(jobs[1]), [0]*3)
    self.ctx.jobs_completed[0][0] = [True, True]
    set_jobs(self.ctx)
    self.assertEqual(self.statuses(jobs[1]), [1]*3)
    self.assertEqual(self.statuses(jobs[2]), [0]*4)

  async def test_parents_must_be_finished(self) -> None:
    self.enter(1, 2)
    jobs = self.addr["jobs"][0]
    set_parents(self.pine, jobs[0][0], [3])
    self.ctx.available_episodes[Sly2Episode.The_Black_Chateau] = 1
    set_jobs(self.ctx)
    self.assertEqual(self.statuses(jobs[0]), [0, 1])
    set_job_status(self.pine, 3, 3)
    set_jobs(self.ctx)
    self.assertEqual(self.statuses(jobs[0]), [1, 1])

  async def test_check_jobs_latches(self) -> None:
    self.enter(1, 2)
    job = self.addr["jobs"][0][1][0]
    set_job_status(self.pine, job, 3)
    check_jobs(self.ctx)
    self.assertTrue(self.ctx.jobs_completed[0][1][0])
    self.assertFalse(self.ctx.jobs_completed[0][1][1])
    set_job_status(self.pine, job, 0)
    check_jobs(self.ctx)
    self.assertTrue(self.ctx.jobs_completed[0][1][0])

  async def test_check_jobs_uses_completion_index(self) -> None:
    self.enter(3, 12)
    activate, check = self.addr["jobs"][2][3][0]
    set_job_status(self.pine, activate, 3)
    check_jobs(self.ctx)
    self.assertFalse(self.ctx.jobs_completed[2][3][0])
    set_job_status(self.pine, check, 3)
    check_jobs(self.ctx)
    self.assertTrue(self.ctx.jobs_completed[2][3][0])

  async def test_multi_section_jobs_use_first_index(self) -> None:
    self.enter(3, 12)
    self.ctx.available_episodes[Sly2Episode.The_Predator_Awakens] = 4
    self.ctx.jobs_completed[2] = [
      [True]*len(chapter) for chapter in self.ctx.jobs_completed[2]
    ]
    set_jobs(self.ctx)
    activate, check = self.addr["jobs"][2][3][0]
    self.assertEqual(job_status(self.pine, activate), 1)
    self.assertEqual(job_status(self.pine, check), 0)


class TestEpisodeHint(ClientTestBase):
  def stuck_in(self, episode: Sly2Episode, available: int) -> None:
    self.enter(episode.value, 2)
    self.ctx.available_episodes[episode] = available
    completed = self.ctx.jobs_completed[episode - 1]
    for chapter in completed[:available]:
      chapter[:] = [True]*len(chapter)

  async def test_not_stuck(self) -> None:
    self.enter(1, 2)
    self.ctx.available_episodes[Sly2Episode.The_Black_Chateau] = 1
    self.ctx.episode_hint_shown = True
    handle_episode_hint(self.ctx)
    self.assertFalse(self.ctx.episode_hint_shown)
    self.assertEqual(len(self.ctx.notification_queue), 0)

  async def test_hint_once(self) -> None:
    self.stuck_in(Sly2Episode.Jailbreak, 1)
    handle_episode_hint(self.ctx)
    handle_episode_hint(self.ctx)
    self.assertTrue(self.ctx.episode_hint_shown)
    self.assertEqual(
      list(self.ctx.notification_queue),
      ["Collect another Progressive Jailbreak to unlock the next jobs."]
    )

  async def test_waits_for_free_infobox(self) -> None:
    self.stuck_in(Sly2Episode.Jailbreak, 1)
    self.ctx.showing_notification = True
    handle_episode_hint(self.ctx)
    self.assertFalse(self.ctx.episode_hint_shown)
    self.ctx.showing_notification = False
    self.ctx.notification("other")
    handle_episode_hint(self.ctx)
    self.assertFalse(self.ctx.episode_hint_shown)

  async def test_all_done_is_not_stuck(self) -> None:
    self.stuck_in(Sly2Episode.Jailbreak, 3)
    handle_episode_hint(self.ctx)
    self.assertEqual(len(self.ctx.notification_queue), 0)

  async def test_anatomy_clockwerk_hint(self) -> None:
    clockwerk = "Collect more Clockwerk parts to unlock the next jobs."
    self.slot_data["episode_8_keys"] = 1
    self.stuck_in(EP8, 3)
    handle_episode_hint(self.ctx)
    self.assertEqual(list(self.ctx.notification_queue), [clockwerk])

    self.ctx.notification_queue.clear()
    self.ctx.episode_hint_shown = False
    self.slot_data["episode_8_keys"] = 3
    self.stuck_in(EP8, 1)
    handle_episode_hint(self.ctx)
    self.assertEqual(list(self.ctx.notification_queue), [clockwerk])

    self.ctx.notification_queue.clear()
    self.ctx.episode_hint_shown = False
    self.slot_data["episode_8_keys"] = 1
    self.stuck_in(EP8, 1)
    handle_episode_hint(self.ctx)
    self.assertEqual(
      list(self.ctx.notification_queue),
      ["Collect another Progressive Anatomy for Disaster to unlock the next "
        "jobs."]
    )


class TestTraps(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.enter(1, 2)
    self.active = set_active_character(self.pine, self.addr)

  def health(self) -> int:
    return self.pine.peek32(self.pine.peek32(self.active + 0xe00))

  def power(self) -> int:
    return self.pine.peek32(self.pine.peek32(self.active + 0x12fc))

  async def test_instant_traps(self) -> None:
    activate_trap(self.ctx, Trap.SLY_1)
    self.assertEqual(self.health(), 1)
    activate_trap(self.ctx, Trap.ENERGY_DRAIN)
    self.assertEqual(self.power(), 0)
    self.assertEqual(self.ctx.active_traps, {})

  async def test_timed_trap_lifecycle(self) -> None:
    clock = self.addr["clock speed"]
    with patch.object(Callbacks, "time", return_value=1000.0):
      activate_trap(self.ctx, Trap.SLOW_MO)
      handle_traps(self.ctx)
    self.assertEqual(self.ctx.active_traps, {Trap.SLOW_MO: 1015.0})
    self.assertEqual(self.pine.peek_float(clock), 0.5)
    with patch.object(Callbacks, "time", return_value=1015.0):
      handle_traps(self.ctx)
    self.assertEqual(self.ctx.active_traps, {})
    self.assertEqual(self.pine.peek_float(clock), 1.0)

  async def test_sugar_rush_and_ice(self) -> None:
    with patch.object(Callbacks, "time", return_value=1000.0):
      activate_trap(self.ctx, Trap.SUGAR_RUSH)
      activate_trap(self.ctx, Trap.ICE)
      handle_traps(self.ctx)
    self.assertEqual(self.pine.peek_float(self.addr["clock speed"]), 1.5)
    self.assertAlmostEqual(
      self.pine.peek_float(self.addr["friction"]), 0.2, places=6
    )
    with patch.object(Callbacks, "time", return_value=1016.0):
      handle_traps(self.ctx)
    self.assertEqual(self.ctx.active_traps, {Trap.ICE: 1020.0})
    self.assertEqual(self.pine.peek_float(self.addr["clock speed"]), 1.0)
    with patch.object(Callbacks, "time", return_value=1020.0):
      handle_traps(self.ctx)
    self.assertEqual(self.pine.peek_float(self.addr["friction"]), 1.5)

  async def test_noise(self) -> None:
    with (
      patch.object(self.interface, "alert_guards") as alert,
      patch.object(self.interface, "release_guards") as release,
      patch.object(Callbacks, "time", return_value=1000.0)
    ):
      activate_trap(self.ctx, Trap.NOISE)
    alert.assert_called_once()
    with (
      patch.object(self.interface, "release_guards") as release,
      patch.object(Callbacks, "time", return_value=1010.0)
    ):
      handle_traps(self.ctx)
    release.assert_called_once()

  async def test_reset(self) -> None:
    self.ctx.active_traps[Trap.ICE] = 5000.0
    self.pine.poke_float(self.addr["clock speed"], 0.5)
    self.pine.poke_float(self.addr["friction"], 0.2)
    reset_traps(self.ctx)
    self.assertEqual(self.ctx.active_traps, {Trap.ICE: 5000.0})
    self.assertEqual(self.pine.peek_float(self.addr["clock speed"]), 1.0)
    self.assertEqual(self.pine.peek_float(self.addr["friction"]), 1.5)
    self.ctx.reset_world_state()
    self.assertEqual(self.ctx.active_traps, {})


class TestMegaJump(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.unload = self.addr["unload mega jump"]
    self.bindings = self.addr["sly bindings"]
    self.pine.poke32(self.unload, MEGA_JUMP_UNLOAD_CALL)

  async def test_without_mega_jump(self) -> None:
    fix_mega_jump(self.ctx)
    self.assertEqual(self.pine.writes, [])

  async def test_patches_and_binds(self) -> None:
    self.give("Mega Jump")
    self.pine.poke32(self.bindings, 5)
    self.pine.poke32(self.bindings + 4, 0xFFFF_FFFF)
    fix_mega_jump(self.ctx)
    self.assertEqual(self.pine.peek32(self.unload), 0)
    self.assertEqual(self.pine.peek32(self.bindings + 4), MEGA_JUMP_GADGET_ID)
    self.assertEqual(self.pine.peek32(self.bindings + 8), 0)

  async def test_already_bound(self) -> None:
    self.ctx.powerups = PowerUps(mega_jump=True)
    self.pine.poke32(self.bindings + 8, MEGA_JUMP_GADGET_ID)
    fix_mega_jump(self.ctx)
    fix_mega_jump(self.ctx)
    self.assertEqual(len(self.pine.writes), 1)
    self.assertFalse(self.pine.written(self.bindings))

  async def test_check_clockla(self) -> None:
    address = self.addr["clock-la defeated"]
    check_clockla(self.ctx)
    self.assertFalse(self.ctx.jobs_completed[7][3][0])
    self.pine.poke32(address, 3)
    check_clockla(self.ctx)
    self.assertTrue(self.ctx.jobs_completed[7][3][0])
    self.pine.poke32(address, 0)
    check_clockla(self.ctx)
    self.assertTrue(self.ctx.jobs_completed[7][3][0])


class TestSetThiefnet(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.enter(1, 2)
    self.ctx.locations_info = {
      self.loc(f"ThiefNet {i+1:02}"): NetworkItem(
        item_dict["Paraglider"].code, self.loc(f"ThiefNet {i+1:02}"), 1
      )
      for i in range(24)
    }
    self.ctx.checked_locations = {self.loc("ThiefNet 02")}
    self.texts = self.addr["text"]["powerups"][0]

  def written_text(self, powerup: int) -> tuple[bytes, bytes]:
    name, description = list(self.texts.values())[powerup]
    return self.pine.peek_cstring(name), self.pine.peek_cstring(description)

  async def test_sets_up_shop(self) -> None:
    self.slot_data["scout_thiefnet"] = False
    await set_thiefnet(self.ctx)
    self.assertEqual(self.ctx.thiefnet_items, ["Tester's Paraglider"]*24)
    self.assertEqual(
      self.ctx.thiefnet_purchases, PowerUps(size_destabilizer=True)
    )
    self.assertEqual(
      self.interface.read_powerups(), PowerUps(size_destabilizer=True)
    )
    for address in self.addr["thiefnet unlock"]:
      self.assertEqual(self.pine.peek32(address), 1)
    for i, cost in enumerate(self.slot_data["thiefnet_costs"]):
      self.assertEqual(self.pine.peek32(self.addr["thiefnet costs"][i]), cost)
    for i in range(len(POWERUP_TEXT)):
      self.assertEqual(
        self.written_text(i), (f"Check #{i+1}".encode(), b"Tester's Paraglider")
      )
    self.assertEqual(self.ctx.sent, [])

  async def test_scouts(self) -> None:
    self.slot_data["scout_thiefnet"] = True
    await set_thiefnet(self.ctx)
    scouts = self.ctx.sent_cmds("LocationScouts")
    self.assertEqual(len(scouts), 1)
    self.assertEqual(
      set(scouts[0]["locations"]),
      {self.loc(f"ThiefNet {i+1:02}") for i in range(24)}
    )
    self.assertEqual(scouts[0]["create_as_hint"], 2)

  async def test_names_cached(self) -> None:
    self.slot_data["scout_thiefnet"] = False
    self.ctx.thiefnet_items = ["cached"]*24
    await set_thiefnet(self.ctx)
    self.assertEqual(self.written_text(0)[1], b"cached")


class TestInit(ClientTestBase):
  options = {"include_pickpocketing": True}

  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.enter(1, 2)
    build_dag(self.pine, self.addr)
    self.guards = make_guard_list(self.pine, self.addr, 0, 2)

  async def test_connected(self) -> None:
    self.ctx.active_traps[Trap.ICE] = 5000.0
    self.ctx.prev_coins = 5
    self.pine.poke_float(self.addr["clock speed"], 0.5)
    await init(self.ctx, True)
    self.assertEqual(self.ctx.active_traps, {Trap.ICE: 5000.0})
    self.assertIsNone(self.ctx.prev_coins)
    self.assertEqual(self.pine.peek_float(self.addr["clock speed"]), 1.0)
    for guard in self.guards:
      self.assertEqual(self.pine.peek32(guard + 0x800 + 0xA0), 1)
    self.assertEqual(
      [m["key"] for m in self.ctx.sent_cmds("Set")], ["Slot:1:Episode"]
    )
    self.assertEqual(
      self.ctx.sent_cmds("Set")[0]["operations"][0]["value"],
      "The Black Chateau"
    )

  async def test_not_connected(self) -> None:
    await init(self.ctx, False)
    self.assertEqual(self.ctx.sent, [])
    self.assertEqual(self.pine.peek32(self.guards[0] + 0x800 + 0xA0), 0)

  async def test_guards_left_alone_without_pickpocketing(self) -> None:
    self.slot_data["include_pickpocketing"] = False
    await init(self.ctx, True)
    self.assertEqual(self.pine.peek32(self.guards[0] + 0x800 + 0xA0), 0)

  async def test_title_screen_start_disabled(self) -> None:
    address = self.addr["title start mask"]
    self.pine.poke32(address, 0x24050800)
    self.enter(0, 0)
    await init(self.ctx, True)
    self.assertEqual(self.pine.peek32(address), 0x24050000)
    self.enter(1, 2)
    await init(self.ctx, True)
    self.assertEqual(self.pine.peek32(address), 0x24050800)


class TestUpdate(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    build_dag(self.pine, self.addr)
    set_string_table(self.pine, self.addr, 1)
    set_infobox_pointers(self.pine, self.addr)
    self.give("Progressive The Black Chateau")

  async def tick(self) -> None:
    self.interface.clear_cache()
    with (
      patch.object(Callbacks, "sleep") as sleep,
      patch.object(Callbacks, "time", return_value=1000.0)
    ):
      await update(self.ctx, True)
    self.sleep = sleep

  async def test_title_screen(self) -> None:
    self.enter(0, 0)
    self.ctx.available_episodes = compute_available_episodes(self.ctx)
    await self.tick()
    self.assertEqual(self.pine.peek8(self.addr["episode unlocks"]), 8)
    self.assertEqual(
      self.pine.peek_cstring(self.addr["text"]["Press START (new)"]),
      b"Connected to Archipelago server"
    )
    self.assertEqual(
      self.pine.peek_cstring(self.addr["text"]["Episode 1"]), b"Unlocked 1/4"
    )
    self.assertEqual(
      self.pine.peek_cstring(self.addr["text"]["Episode 2"]), b"Locked"
    )
    self.sleep.assert_not_called()

  async def test_hub_tick(self) -> None:
    self.enter(1, 2)
    self.give("Mega Jump")
    self.pine.poke32(self.addr["unload mega jump"], MEGA_JUMP_UNLOAD_CALL)
    self.ctx.jobs_completed[0][0][0] = True
    await self.tick()
    await self.tick()
    self.assertEqual(self.pine.peek32(self.addr["unload mega jump"]), 0)
    self.assertEqual(self.interface.read_items_received(), 2)
    self.assertTrue(self.ctx.in_hub)
    self.assertEqual(
      [job_status(self.pine, j) for j in self.addr["jobs"][0][0]], [1, 1]
    )
    self.assertEqual(
      [set(m["locations"]) for m in self.ctx.sent_cmds("LocationChecks")],
      [{self.loc("The Black Chateau - Satellite Sabotage")}]
    )
    self.sleep.assert_not_called()

  async def test_locked_episode_boots_to_menu(self) -> None:
    self.enter(4, 14)
    await self.tick()
    self.assertEqual(self.pine.peek32(self.addr["reload"]), 1)
    self.sleep.assert_called_once()

  async def test_safehouse_exit_resets_hint(self) -> None:
    self.enter(1, 2)
    await self.tick()
    self.ctx.jobs_completed[0][0] = [True, True]
    self.ctx.episode_hint_shown = True
    self.ctx.in_hub = True
    self.ctx.notification("busy")
    await self.tick()
    self.assertTrue(self.ctx.episode_hint_shown)

    self.ctx.in_safehouse = True
    self.ctx.notification("busy")
    await self.tick()
    self.assertFalse(self.ctx.in_safehouse)
    self.assertFalse(self.ctx.episode_hint_shown)

  async def test_safehouse_entry_sets_up_thiefnet(self) -> None:
    self.slot_data["scout_thiefnet"] = False
    self.enter(1, 2)
    self.pine.poke32(self.addr["infobox string"], 305)
    self.ctx.thiefnet_items = ["x"]*24
    await self.tick()
    self.assertTrue(self.ctx.in_safehouse)
    for address in self.addr["thiefnet unlock"]:
      self.assertEqual(self.pine.peek32(address), 1)

  async def test_bottles_text_written_on_change(self) -> None:
    self.enter(1, 2)
    buffer = string_buffer(self.pine, self.addr, "right back", 1)
    await self.tick()
    self.assertEqual(
      self.pine.peek_cstring(buffer), b"Bottles Collected: 0"
    )
    self.pine.poke_bytes(buffer, b"junk\0")
    await self.tick()
    self.assertEqual(self.pine.peek_cstring(buffer), b"junk")
    self.pine.poke32(self.addr["bottle flags"][0], 0b101)
    await self.tick()
    self.assertEqual(
      self.pine.peek_cstring(buffer), b"Bottles Collected: 2"
    )

  async def test_title_text_follows_items(self) -> None:
    self.enter(0, 0)
    address = self.addr["text"]["Episode 2"]
    await self.tick()
    self.assertEqual(self.pine.peek_cstring(address), b"Locked")
    self.pine.poke_bytes(address, b"junk\0")
    await self.tick()
    self.assertEqual(self.pine.peek_cstring(address), b"junk")
    self.give("Progressive A Starry Eyed Encounter")
    self.pine.poke32(self.addr["map id"], 1)
    await self.tick()
    await self.tick()
    self.assertEqual(self.pine.peek_cstring(address), b"Unlocked 1/4")

  async def test_jobs_follow_items_and_game_changes(self) -> None:
    self.enter(1, 2)
    await self.tick()
    await self.tick()
    self.assertEqual(
      [job_status(self.pine, j) for j in self.addr["jobs"][0][0]], [1, 1]
    )
    self.assertFalse(self.ctx.jobs_dirty)
    # The game activating a job that should be locked is reverted
    set_job_status(self.pine, self.addr["jobs"][0][1][0], 1)
    await self.tick()
    self.assertEqual(job_status(self.pine, self.addr["jobs"][0][1][0]), 0)
    # ...until its chapter is unlocked by an item
    self.ctx.jobs_completed[0][0] = [True, True]
    self.give("Progressive The Black Chateau")
    await self.tick()
    await self.tick()
    self.assertEqual(job_status(self.pine, self.addr["jobs"][0][1][0]), 1)

  async def test_bottles_follow_flags_and_items(self) -> None:
    self.slot_data["bottle_location_bundle_size"] = 5
    self.enter(1, 2)
    await self.tick()
    self.assertEqual(self.pine.peek32(self.addr["bottle count"]), 0)
    self.give("5 bottles - The Black Chateau")
    await self.tick()
    await self.tick()
    self.assertEqual(self.pine.peek32(self.addr["bottle count"]), 5)
    self.pine.poke32(self.addr["bottle count"], 6)
    await self.tick()
    self.assertEqual(self.pine.peek32(self.addr["bottle count"]), 6)
    self.pine.poke32(self.addr["bottle flags"][0], 1)
    await self.tick()
    self.assertEqual(self.pine.peek32(self.addr["bottle count"]), 5)

  async def test_loot_odds_follow_pickpocket_checks(self) -> None:
    self.slot_data["dynamic_loot_tables"] = True
    self.slot_data["loot_table_distribution"] = 50
    self.enter(1, 2)
    await self.tick()
    odds_address = self.addr["loot table odds"][0][0][0]
    before = self.pine.peek32(odds_address)
    self.assertFalse(self.ctx.loot_dirty)
    loot = episode_loot(self.slot_data["loot_table"], 0, 0)[0]
    index = LOOT_IDS[loot] - LOOT_IDS[list(LOOT)[0]]
    self.pine.poke32(self.addr["loot"][index], 1)
    await self.tick()
    self.assertIn(
      self.loc(f"Pickpocket {loot}"),
      self.ctx.sent_cmds("LocationChecks")[-1]["locations"]
    )
    self.assertTrue(self.ctx.loot_dirty)
    await self.tick()
    self.assertNotEqual(self.pine.peek32(odds_address), before)

  async def test_cutscene_skips_ap_block(self) -> None:
    self.enter(1, 2)
    self.ctx.jobs_completed[0][0][0] = True
    self.pine.poke16(self.addr["frame counter"], 50)
    await self.tick()
    self.assertEqual(self.ctx.sent_cmds("LocationChecks"), [])
    self.assertEqual(self.interface.read_items_received(), 0)
    self.pine.poke16(self.addr["frame counter"], 0)
    await self.tick()
    self.assertTrue(self.ctx.sent_cmds("LocationChecks"))
    self.assertEqual(self.interface.read_items_received(), 1)


class TestFixJobs(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    build_dag(self.pine, self.addr)

  async def test_fixes_when_in_hub_and_no_job(self) -> None:
    self.enter(1, 2)
    set_job_status(self.pine, 4, 2)
    fix_jobs(self.ctx)
    self.assertEqual(job_status(self.pine, 4), 1)

  async def test_skips_outside_hub(self) -> None:
    self.enter(1, 3)
    set_job_status(self.pine, 4, 2)
    fix_jobs(self.ctx)
    self.assertEqual(job_status(self.pine, 4), 2)

  async def test_skips_when_job_active(self) -> None:
    self.enter(1, 2, job=4)
    set_job_status(self.pine, 4, 2)
    fix_jobs(self.ctx)
    self.assertEqual(job_status(self.pine, 4), 2)


class TestOnPackage(ClientTestBase):
  def run_package(self, cmd: str, args: dict) -> list:
    scheduled: list = []
    with (
      patch.object(Sly2Client.CommonContext, "on_package"),
      patch.object(
        Sly2Client.Utils, "async_start",
        side_effect=lambda coro, *_a, **_k: scheduled.append(coro)
      )
    ):
      self.ctx.on_package(cmd, args)
    return scheduled

  async def drain(self, scheduled: list) -> None:
    for coro in scheduled:
      await coro

  async def test_room_update_marks_loot_dirty(self) -> None:
    self.ctx.loot_dirty = False
    self.run_package("RoomUpdate", {"checked_locations": [1, 2]})
    self.assertTrue(self.ctx.loot_dirty)

  async def test_room_update_without_locations_ignored(self) -> None:
    self.ctx.loot_dirty = False
    self.run_package("RoomUpdate", {})
    self.assertFalse(self.ctx.loot_dirty)

  async def test_ring_link_bounce_accumulates(self) -> None:
    self.ctx.ring_link_enabled = True
    self.run_package("Bounced", {
      "tags": ["RingLink"],
      "data": {"source": self.ctx.ring_link_source + 1, "amount": 7}
    })
    self.assertEqual(self.ctx.pending_ring_link, 7)

  async def test_ring_link_ignores_own_source(self) -> None:
    self.ctx.ring_link_enabled = True
    self.run_package("Bounced", {
      "tags": ["RingLink"],
      "data": {"source": self.ctx.ring_link_source, "amount": 7}
    })
    self.assertEqual(self.ctx.pending_ring_link, 0)

  async def test_ring_link_ignored_when_disabled(self) -> None:
    self.ctx.ring_link_enabled = False
    self.run_package("Bounced", {
      "tags": ["RingLink"],
      "data": {"source": self.ctx.ring_link_source + 1, "amount": 7}
    })
    self.assertEqual(self.ctx.pending_ring_link, 0)

  async def test_ring_link_ignores_other_tags(self) -> None:
    self.ctx.ring_link_enabled = True
    self.run_package("Bounced", {
      "tags": ["DeathLink"], "data": {"source": 0, "amount": 7}
    })
    self.assertEqual(self.ctx.pending_ring_link, 0)

  async def test_connected_populates_state(self) -> None:
    self.ctx.checked_locations = {
      self.loc("ThiefNet 01"),
      self.loc("The Black Chateau - Vault")
    }
    scheduled = self.run_package("Connected", {"slot_data": self.slot_data})
    await self.drain(scheduled)
    self.assertIs(self.ctx.slot_data, self.slot_data)
    self.assertTrue(self.ctx.thiefnet_purchases[0])
    self.assertEqual(sum(self.ctx.thiefnet_purchases), 1)
    self.assertTrue(self.ctx.vaults[0])
    self.assertEqual(sum(self.ctx.vaults), 1)
    self.assertTrue(self.ctx.sent_cmds("LocationScouts"))

  async def test_connected_version_mismatch_raises(self) -> None:
    bad = dict(self.slot_data)
    bad["world_version"] = [9, 9, 0]
    with self.assertRaises(Exception):
      self.run_package("Connected", {"slot_data": bad})


class TestInitPerMap(ClientTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    build_dag(self.pine, self.addr)

  async def test_resets_bottles_text(self) -> None:
    self.enter(1, 2)
    self.ctx.bottles_text = 3
    await init(self.ctx, False)
    self.assertIsNone(self.ctx.bottles_text)

  async def test_stuck_in_cairo_boots_to_menu(self) -> None:
    self.enter(0, 0)
    self.pine.poke32(self.addr["savefile last world"], 3)
    await init(self.ctx, False)
    self.assertEqual(self.pine.peek32(self.addr["reload"]), 0)
    await init(self.ctx, True)
    self.assertEqual(self.pine.peek32(self.addr["reload"]), 1)

  async def test_fixes_abandoned_jobs_in_hub(self) -> None:
    self.enter(1, 2)
    set_job_status(self.pine, 4, 2)
    await init(self.ctx, True)
    self.assertEqual(job_status(self.pine, 4), 1)
    set_job_status(self.pine, 4, 2)
    self.enter(1, 3)
    await init(self.ctx, True)
    self.assertEqual(job_status(self.pine, 4), 2)

  async def test_episode_set_once_per_episode(self) -> None:
    self.enter(1, 2)
    await init(self.ctx, True)
    self.enter(1, 3)
    await init(self.ctx, True)
    self.assertEqual(len(self.ctx.sent_cmds("Set")), 1)
    self.enter(2, 8)
    await init(self.ctx, True)
    self.assertEqual(
      [m["operations"][0]["value"] for m in self.ctx.sent_cmds("Set")],
      ["The Black Chateau", "A Starry Eyed Encounter"]
    )
    self.ctx.reset_world_state()
    await init(self.ctx, True)
    self.assertEqual(len(self.ctx.sent_cmds("Set")), 3)


class TestTick(ClientTestBase):
  """Whole ticks through _handle_game_ready, including the prefetch"""
  options = {"tasksanity": True, "include_vaults": True}

  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    build_dag(self.pine, self.addr)
    set_string_table(self.pine, self.addr, 1)
    set_infobox_pointers(self.pine, self.addr)
    self.give("Progressive The Black Chateau")
    self.ctx.server = SimpleNamespace()

  def place(self, episode: int, map_id: int) -> None:
    self.enter(episode, map_id)
    self.ctx.current_episode = None

  async def tick(self) -> None:
    with (
      patch.object(Sly2Client.asyncio, "sleep"),
      patch.object(Callbacks, "sleep"),
      patch.object(Callbacks, "time", return_value=1000.0)
    ):
      await _handle_game_ready(self.ctx)

  async def settle(self) -> None:
    await self.tick()
    await self.tick()
    self.pine.clear_counts()
    self.ctx.sent.clear()

  def assert_cost(self, reads: int, batches: int) -> None:
    self.assertEqual(
      (self.pine.reads, self.pine.batches, self.pine.writes),
      (reads, batches, [])
    )
    self.assertEqual(self.ctx.sent, [])

  async def test_hub_steady_state(self) -> None:
    self.place(1, 2)
    await self.settle()
    await self.tick()
    self.assert_cost(0, 2)
    self.assertEqual(self.ctx.current_map, 2)
    self.assertEqual(
      [job_status(self.pine, j) for j in self.addr["jobs"][0][0]], [1, 1]
    )

  async def test_title_screen_steady_state(self) -> None:
    self.place(0, 0)
    await self.settle()
    await self.tick()
    self.assert_cost(0, 2)
    self.assertEqual(self.pine.peek8(self.addr["episode unlocks"]), 8)

  async def test_first_tick_walks_dag_once(self) -> None:
    self.place(1, 2)
    await self.tick()
    self.assertLess(self.pine.reads, 128)
    self.pine.clear_counts()
    await self.tick()
    self.assertLess(self.pine.reads, 10)

  async def test_map_change_runs_init(self) -> None:
    self.place(1, 2)
    await self.settle()
    self.ctx.bottles_text = 5
    self.ctx.prev_coins = 7
    self.pine.poke32(self.addr["map id"], 3)
    await self.tick()
    self.assertEqual(self.ctx.current_map, 3)
    self.assertIsNone(self.ctx.bottles_text)
    self.assertIsNone(self.ctx.prev_coins)
    self.assertEqual(self.ctx.current_episode, Sly2Episode.The_Black_Chateau)
    self.assertEqual(self.ctx.sent_cmds("Set"), [])

  async def test_dag_relinked_on_map_change(self) -> None:
    self.place(1, 2)
    await self.settle()
    self.pine.poke32(dag_node(3) + 0x20, dag_node(50))
    self.pine.poke32(self.addr["map id"], 3)
    await self.tick()
    self.assertEqual(self.interface._get_job_address(4), dag_node(50))

  async def test_loading_defers_everything(self) -> None:
    self.place(1, 2)
    self.pine.poke32(self.addr["loading"], 2)
    await self.tick()
    self.assertTrue(self.ctx.is_loading)
    self.assertIsNone(self.ctx.current_episode)
    self.assertEqual(self.pine.writes, [])
    self.pine.poke32(self.addr["loading"], 0)
    await self.tick()
    self.assertFalse(self.ctx.is_loading)
    self.assertIsNone(self.ctx.current_episode)
    await self.tick()
    self.assertEqual(self.ctx.current_episode, Sly2Episode.The_Black_Chateau)
