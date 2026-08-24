import json
import unittest
from logging import getLogger

from ..data.Constants import (
  ADDRESSES,
  CAVE_BLOB,
  CAVE_HOOK_ENTRY,
  CAVE_HOOK_ORIG,
  COIN_POP_INTERVAL,
  LOOT,
  LOOT_IDS,
  LOOT_PRICES,
  MEGA_JUMP_GADGET_ID,
  MEGA_JUMP_UNLOAD_CALL,
  PEDESTAL_VTABLE,
  INTERACTABLE_NEXT,
  PEDESTAL_USERS,
  ENTITY_MANAGER_FREE,
  ENTITY_SLOT,
  ENTITY_NEXT,
  ENTITY_PREV,
  ENTITY_FIRST_CHILD,
  ENTITY_LAST_CHILD,
  ENTITY_CHILD_LINK,
  SLY_BACK_NODE,
  TREASURE_VTABLE,
  POWERUP_TEXT,
  TREASURE_PRICES
)
from ..Sly2Interface import (
  EE_RAM_START,
  MAX_GUARDS,
  CycleCounts,
  PowerUps,
  Sly2Episode,
  Sly2Interface
)
from .client_base import (
  GAME_ID,
  HEAP,
  InterfaceTestBase,
  build_dag,
  dag_node,
  guard,
  job_status,
  make_guard_list,
  set_active_character,
  set_infobox_pointers,
  set_job_mission,
  set_job_status,
  set_location,
  set_parents,
  set_string_table,
  string_buffer
)
from .fake_pine import FakePine

WIRE_LOOT = json.loads(json.dumps(LOOT))


class TestFakePine(unittest.TestCase):
  def setUp(self) -> None:
    self.pine = FakePine()

  def test_untouched_memory_is_zero(self) -> None:
    self.assertEqual(self.pine.read_int32(0x200000), 0)
    self.assertEqual(self.pine.read_bytes(0x200000, 4), bytes(4))

  def test_int_round_trips(self) -> None:
    self.pine.write_int8(0x200000, 0xAB)
    self.pine.write_int16(0x200010, 0xBEEF)
    self.pine.write_int32(0x200020, 0xFFFF_FFFF)
    self.assertEqual(self.pine.read_int8(0x200000), 0xAB)
    self.assertEqual(self.pine.read_int16(0x200010), 0xBEEF)
    self.assertEqual(self.pine.read_int32(0x200020), 0xFFFF_FFFF)

  def test_little_endian(self) -> None:
    self.pine.write_int32(0x200000, 0x11223344)
    self.assertEqual(self.pine.read_bytes(0x200000, 4), b"\x44\x33\x22\x11")

  def test_float_round_trip(self) -> None:
    self.pine.write_float(0x200000, 1.5)
    self.assertEqual(self.pine.peek_float(0x200000), 1.5)

  def test_batch_ops(self) -> None:
    self.pine.batch_write_int32([(0x200000, 1), (0x200004, 2)])
    self.pine.batch_write_float([(0x200008, 0.5)])
    self.assertEqual(self.pine.batch_read_int32([0x200000, 0x200004]), [1, 2])
    self.assertEqual(self.pine.peek_float(0x200008), 0.5)
    self.assertEqual(len(self.pine.writes), 3)

  def test_negative_write_raises(self) -> None:
    with self.assertRaises(OverflowError):
      self.pine.write_int32(0x200000, -1)

  def test_cstring(self) -> None:
    self.pine.write_bytes(0x200000, b"abc\0def")
    self.assertEqual(self.pine.peek_cstring(0x200000), b"abc")


class TestConnection(unittest.TestCase):
  def make(self, game_id: str) -> tuple[Sly2Interface, FakePine]:
    pine = FakePine(game_id)
    interface = Sly2Interface(getLogger("Sly2Test"))
    interface.pcsx2_interface = pine
    return interface, pine

  def test_right_game(self) -> None:
    interface, _ = self.make(GAME_ID)
    interface.connect_to_game()
    self.assertEqual(interface.current_game, GAME_ID)
    self.assertIs(interface.addresses, ADDRESSES[GAME_ID])
    self.assertTrue(interface.get_connection_state())

  def test_no_game(self) -> None:
    interface, _ = self.make("")
    with self.assertNoLogs("Sly2Test", "WARNING"):
      interface.connect_to_game()
    self.assertIsNone(interface.current_game)
    self.assertFalse(interface.get_connection_state())

  def test_wrong_game_warns_once(self) -> None:
    interface, _ = self.make("SLUS-00000")
    with self.assertLogs("Sly2Test", "WARNING") as logs:
      interface.connect_to_game()
    self.assertEqual(len(logs.output), 1)
    with self.assertNoLogs("Sly2Test", "WARNING"):
      interface.connect_to_game()
    self.assertIsNone(interface.current_game)

  def test_disconnected_state(self) -> None:
    interface, pine = self.make(GAME_ID)
    interface.connect_to_game()
    pine.disconnect()
    self.assertFalse(interface.get_connection_state())


class TestMemoryGuards(InterfaceTestBase):
  def test_read_outside_ram_is_zero(self) -> None:
    self.pine.memory[0x10] = 5
    self.assertEqual(self.interface._read32(0x10), 0)
    self.assertEqual(self.interface._read_bytes(0x10, 4), bytes(4))

  def test_write_outside_ram_refused_once(self) -> None:
    with self.assertLogs("Sly2Test", "WARNING") as logs:
      self.interface._write32(0x10, 1)
      self.interface._write32(0x20, 1)
    self.assertEqual(len(logs.output), 1)
    self.assertEqual(self.pine.writes, [])

  def test_write_at_ram_edge(self) -> None:
    self.interface._write32(EE_RAM_START, 1)
    self.assertEqual(self.pine.peek32(EE_RAM_START), 1)
    self.interface._write32(EE_RAM_START - 1, 1)
    self.assertFalse(self.pine.written(EE_RAM_START - 1))

  def test_batch_write_drops_only_bad_addresses(self) -> None:
    self.interface._batch_write32([(0x10, 1), (0x200000, 2)])
    self.assertEqual(
      self.pine.writes, [("bw32", 0x200000, (2).to_bytes(4, "little"))]
    )

  def test_safe_patch(self) -> None:
    address = 0x200000
    self.pine.poke32(address, 0xAA)
    self.interface.safe_patch(address, 0xBB, 0xAA)
    self.assertEqual(self.pine.peek32(address), 0xBB)

    self.pine.clear_writes()
    self.interface.safe_patch(address, 0xBB, 0xAA)
    self.assertEqual(self.pine.writes, [])

  def test_safe_patch_refuses_unexpected_word(self) -> None:
    address = 0x200000
    self.pine.poke32(address, 0xCC)
    with self.assertLogs("Sly2Test", "WARNING") as logs:
      self.interface.safe_patch(address, 0xBB, 0xAA)
    self.assertEqual(len(logs.output), 1)
    self.assertEqual(self.pine.peek32(address), 0xCC)
    with self.assertNoLogs("Sly2Test", "WARNING"):
      self.interface.safe_patch(address, 0xBB, 0xAA)

  def test_batched_patches_one_message(self) -> None:
    first, second, refused = 0x200000, 0x200010, 0x200020
    self.pine.poke32(first, 0xAA)
    self.pine.poke32(second, 0xAA)
    self.pine.poke32(refused, 0xCC)
    with self.assertLogs("Sly2Test", "WARNING") as logs:
      with self.interface.batched_patches():
        self.interface.safe_patch(first, 0xBB, 0xAA)
        self.interface.safe_patch(second, 0xDD, 0xAA)
        self.interface.safe_patch(refused, 0xBB, 0xAA)
        self.assertEqual(self.pine.writes, [])
    self.assertEqual(len(logs.output), 1)
    self.assertEqual(self.pine.writes, [
      ("bw32", first, (0xBB).to_bytes(4, "little")),
      ("bw32", second, (0xDD).to_bytes(4, "little"))
    ])
    self.assertEqual(self.pine.peek32(refused), 0xCC)
    self.pine.clear_writes()
    self.interface.safe_patch(first, 0xBB, 0xAA)
    self.assertEqual(self.pine.writes, [])


class TestCave(InterfaceTestBase):
  def _prime_hook(self) -> None:
    self.pine.poke32(self.addr["cave hook"], CAVE_HOOK_ORIG)

  def test_install_writes_cave_and_hook(self) -> None:
    self._prime_hook()
    self.pine.poke32(self.addr["coin pops"], 3)
    self.interface.install_cave()
    blob = bytes.fromhex(CAVE_BLOB)
    self.assertEqual(self.pine.peek_bytes(self.addr["cave"], len(blob)), blob)
    hook = self.addr["cave hook"]
    self.assertEqual(self.pine.peek32(hook), CAVE_HOOK_ENTRY)
    self.assertEqual(self.pine.peek32(self.addr["coin pops"]), 0)
    self.assertEqual(
      self.pine.peek32(self.addr["coin interval"]), COIN_POP_INTERVAL
    )
    self.assertTrue(self.interface.cave_live())

  def test_install_is_idempotent(self) -> None:
    self._prime_hook()
    self.interface.install_cave()
    self.pine.clear_writes()
    self.interface.install_cave()
    self.assertEqual(self.pine.writes, [])

  def test_install_never_rewrites_present_blob(self) -> None:
    self._prime_hook()
    self.pine.poke_bytes(self.addr["cave"], bytes.fromhex(CAVE_BLOB))
    self.interface.clear_cache()
    self.interface.install_cave()
    self.assertFalse(self.pine.written(self.addr["cave"]))
    self.assertTrue(self.interface.cave_live())
    self.assertEqual(self.pine.writes[-1], (
      "bw32", self.addr["cave hook"], CAVE_HOOK_ENTRY.to_bytes(4, "little")
    ))

  def test_code_patch_goes_through_cave(self) -> None:
    self._prime_hook()
    self.interface.install_cave()
    self.pine.clear_writes()
    code, data = 0x200000, 0x300000
    self.pine.poke32(code, 0xAA)
    self.pine.poke32(data, 0xAA)
    with self.interface.batched_patches():
      self.interface.safe_patch(code, 0xBB, 0xAA)
      self.interface.safe_patch(data, 0xCC, 0xAA)
    slot = self.addr["cave patches"]
    self.assertEqual(self.pine.peek32(code), 0xAA)
    self.assertEqual(self.pine.peek32(slot + 4), 0xBB)
    self.assertEqual(self.pine.peek32(slot), code)
    self.assertEqual(self.pine.peek32(data), 0xCC)
    self.assertFalse(self.pine.written(code))

  def test_code_patch_direct_without_cave(self) -> None:
    self.pine.poke32(0x200000, 0xAA)
    self.interface.safe_patch(0x200000, 0xBB, 0xAA)
    self.assertEqual(self.pine.peek32(0x200000), 0xBB)
    self.assertFalse(self.pine.written(self.addr["cave patches"]))

  def test_code_patch_direct_when_slots_full(self) -> None:
    self._prime_hook()
    self.interface.install_cave()
    slots = self.addr["cave patches"]
    for i in range(4):
      self.pine.poke32(slots + 8*i, 0x100000 + 4*i)
    self.interface.clear_cache()
    self.pine.poke32(0x200000, 0xAA)
    self.interface.safe_patch(0x200000, 0xBB, 0xAA)
    self.assertEqual(self.pine.peek32(0x200000), 0xBB)

  def test_install_refuses_wrong_hook(self) -> None:
    hook = self.addr["cave hook"]
    self.pine.poke32(hook, 0x12345678)
    self.pine.poke32(hook + 4, 0x12345678)
    with self.assertLogs("Sly2Test", "WARNING"):
      self.interface.install_cave()
    self.assertEqual(self.pine.peek32(hook), 0x12345678)
    self.assertFalse(self.interface.cave_live())

  def test_queue_coins(self) -> None:
    self.pine.poke32(self.addr["cave hook"], CAVE_HOOK_ENTRY)
    self.assertTrue(self.interface.queue_coins(50, 5))
    self.assertEqual(self.pine.peek32(self.addr["coin amount"]), 50)
    self.assertEqual(self.pine.peek32(self.addr["coin pops"]), 5)
    self.assertTrue(self.interface.coins_paying_out())

  def test_queue_coins_waits_for_payout(self) -> None:
    self.pine.poke32(self.addr["cave hook"], CAVE_HOOK_ENTRY)
    self.pine.poke32(self.addr["coin pops"], 2)
    self.pine.clear_writes()
    self.assertFalse(self.interface.queue_coins(50, 5))
    self.assertEqual(self.pine.writes, [])

  def test_queue_coins_without_cave(self) -> None:
    self.pine.poke32(self.addr["cave hook"], CAVE_HOOK_ORIG)
    self.pine.clear_writes()
    self.assertFalse(self.interface.queue_coins(50, 5))
    self.assertEqual(self.pine.writes, [])

  def test_install_clears_sound_slots(self) -> None:
    self._prime_hook()
    for name in ("sound id", "sound interval", "sound timer"):
      self.pine.poke32(self.addr[name], 7)
    self.interface.install_cave()
    for name in ("sound id", "sound interval", "sound timer"):
      self.assertEqual(self.pine.peek32(self.addr[name]), 0)

  def test_play_sound_once(self) -> None:
    self.pine.poke32(self.addr["cave hook"], CAVE_HOOK_ENTRY)
    self.pine.poke32(self.addr["sound timer"], 9)
    self.assertTrue(self.interface.play_sound(0x158))
    self.assertEqual(self.pine.peek32(self.addr["sound id"]), 0x158)
    self.assertEqual(self.pine.peek32(self.addr["sound interval"]), 0)
    self.assertEqual(self.pine.peek32(self.addr["sound timer"]), 0)
    self.assertTrue(self.interface.sound_playing())

  def test_play_sound_repeat(self) -> None:
    self.pine.poke32(self.addr["cave hook"], CAVE_HOOK_ENTRY)
    self.assertTrue(self.interface.play_sound(0x158, 60))
    self.assertEqual(self.pine.peek32(self.addr["sound interval"]), 60)

  def test_stop_sound(self) -> None:
    self.pine.poke32(self.addr["cave hook"], CAVE_HOOK_ENTRY)
    self.interface.play_sound(0x158, 60)
    self.interface.stop_sound()
    self.assertEqual(self.pine.peek32(self.addr["sound id"]), 0)
    self.assertEqual(self.pine.peek32(self.addr["sound interval"]), 0)
    self.assertFalse(self.interface.sound_playing())

  def test_play_sound_without_cave(self) -> None:
    self.pine.poke32(self.addr["cave hook"], CAVE_HOOK_ORIG)
    self.pine.clear_writes()
    self.assertFalse(self.interface.play_sound(0x158))
    self.assertEqual(self.pine.writes, [])


class TestPowerUps(InterfaceTestBase):
  def test_round_trip_each_field(self) -> None:
    for field in PowerUps._fields:
      powerups = PowerUps(**{field: True})
      self.interface.load_powerups(powerups)
      self.assertEqual(self.interface.read_powerups(), powerups, field)

  def test_round_trip_all(self) -> None:
    powerups = PowerUps(*[True]*len(PowerUps._fields))
    self.interface.load_powerups(powerups)
    self.assertEqual(self.interface.read_powerups(), powerups)

  def test_raw_layout(self) -> None:
    gadgets = self.addr["gadgets"]
    self.interface.load_powerups(PowerUps(trigger_bomb=True))
    self.assertEqual(self.pine.peek_bytes(gadgets, 6), b"\x80\0\0\0\0\0")
    self.interface.load_powerups(PowerUps(size_destabilizer=True))
    self.assertEqual(self.pine.peek_bytes(gadgets, 6), b"\0\x01\0\0\0\0")
    self.interface.load_powerups(PowerUps(tom=True, time_rush=True))
    self.assertEqual(self.pine.peek_bytes(gadgets, 6), b"\0\0\0\0\0\x06")

  def test_ignores_foreign_bits(self) -> None:
    self.pine.poke_bytes(self.addr["gadgets"], b"\x7f\0\0\0\0\xf8")
    self.assertEqual(self.interface.read_powerups(), PowerUps())


class TestBottles(InterfaceTestBase):
  def test_count(self) -> None:
    address = self.addr["bottle flags"][2]
    self.pine.poke32(address, 0b1011)
    self.assertEqual(
      self.interface.get_bottles(Sly2Episode.The_Predator_Awakens), 3
    )
    self.assertEqual(self.interface.get_bottles(Sly2Episode.Jailbreak), 0)

  def test_list(self) -> None:
    address = self.addr["bottle flags"][0]
    episode = Sly2Episode.The_Black_Chateau

    self.pine.poke32(address, 1 << 29)
    bottles = self.interface.get_bottle_list(episode)
    self.assertEqual(len(bottles), 30)
    self.assertTrue(bottles[0])
    self.assertEqual(sum(bottles), 1)

    self.pine.poke32(address, 1)
    self.assertTrue(self.interface.get_bottle_list(episode)[29])

    self.pine.poke32(address, 0x3FFFFFFF)
    self.assertEqual(sum(self.interface.get_bottle_list(episode)), 30)

    self.pine.poke32(address, 0xC0000000)
    self.assertEqual(sum(self.interface.get_bottle_list(episode)), 0)

  def test_set(self) -> None:
    self.interface.set_bottles(12)
    self.assertEqual(self.pine.peek32(self.addr["bottle count"]), 12)


class TestText(InterfaceTestBase):
  def test_direct_address(self) -> None:
    self.interface.set_text(0x200000, "A&B")
    self.assertEqual(self.pine.peek_bytes(0x200000, 5), b"A&&B\0")

  def test_named_text_resolves_per_episode(self) -> None:
    for episode in (1, 3):
      self.pine.poke32(self.addr["world id"], episode)
      set_string_table(self.pine, self.addr, episode)
      self.interface.set_text("infobox", f"ep{episode}")
      buffer = string_buffer(self.pine, self.addr, "infobox", episode)
      self.assertEqual(self.pine.peek_cstring(buffer), f"ep{episode}".encode())

  def test_unresolved_pointer_refused(self) -> None:
    self.pine.poke32(self.addr["world id"], 1)
    with self.assertLogs("Sly2Test", "WARNING"):
      self.interface.set_text("infobox", "x")
    self.assertEqual(self.pine.writes, [])


class TestThiefNet(InterfaceTestBase):
  def setUp(self) -> None:
    super().setUp()
    self.pine.poke32(self.addr["world id"], 1)
    self.texts = self.addr["text"]["powerups"][0]

  def written_text(self, powerup: int) -> tuple[bytes, bytes]:
    name, description = list(self.texts.values())[powerup]
    return self.pine.peek_cstring(name), self.pine.peek_cstring(description)

  def test_short_texts_unchanged(self) -> None:
    self.interface.set_thiefnet(0, ("Check #1", "Tester's Thing"))
    self.assertEqual(self.written_text(0), (b"Check #1", b"Tester's Thing"))

  def test_name_truncation(self) -> None:
    # "Trigger Bomb" is 12 chars, so the slot holds 15
    self.interface.set_thiefnet(0, ("ABCDEFGHIJKLMNO", "d"))
    self.assertEqual(self.written_text(0)[0], b"ABCDEFGHIJKLMNO")
    self.interface.set_thiefnet(0, ("ABCDEFGHIJKLMNOP", "d"))
    self.assertEqual(self.written_text(0)[0], b"ABCDEFGHIJKLM..")

  def test_name_budget_at_multiple_of_16(self) -> None:
    # "Adrenaline Burst" is 16 chars, so the slot holds 31
    index = list(POWERUP_TEXT).index("Adrenaline Burst")
    self.interface.set_thiefnet(index, ("x"*31, "d"))
    self.assertEqual(self.written_text(index)[0], b"x"*31)
    self.interface.set_thiefnet(index, ("x"*32, "d"))
    self.assertEqual(self.written_text(index)[0], b"x"*29 + b"..")

  def test_description_truncation(self) -> None:
    # The vanilla Trigger Bomb description is 37 chars, so the slot holds 47
    self.interface.set_thiefnet(0, ("n", "y"*47))
    self.assertEqual(self.written_text(0)[1], b"y"*47)
    self.interface.set_thiefnet(0, ("n", "y"*48))
    self.assertEqual(self.written_text(0)[1], b"y"*45 + b"..")

  def test_cost_and_unlock(self) -> None:
    self.interface.set_thiefnet_cost(3, 250)
    self.assertEqual(self.pine.peek32(self.addr["thiefnet costs"][3]), 250)
    self.interface.set_thiefnet_unlock()
    for address in self.addr["thiefnet unlock"]:
      self.assertEqual(self.pine.peek32(address), 1)

  def test_reset(self) -> None:
    self.interface.set_thiefnet(0, ("Check #1", "Tester's Thing"))
    self.interface.reset_thiefnet()
    for i, (name, description) in enumerate(POWERUP_TEXT.items()):
      self.assertEqual(
        self.written_text(i), (name.encode(), description.encode())
      )


class TestGoals(InterfaceTestBase):
  def complete(self, *indices: int) -> None:
    for address in self.addr["operation completion"]:
      self.pine.poke32(address, 0)
    for i in indices:
      self.pine.poke32(self.addr["operation completion"][i], 1)

  def test_operation_completion(self) -> None:
    self.complete(1, 7)
    self.assertEqual(
      self.interface.get_operation_completion(),
      [False, True, False, False, False, False, False, True]
    )

  def test_is_goaled_mapping(self) -> None:
    for goal, index in enumerate([0, 2, 4, 6, 7]):
      self.complete(index)
      self.assertTrue(self.interface.is_goaled(goal), goal)
      self.complete(*(i for i in range(8) if i != index))
      self.assertFalse(self.interface.is_goaled(goal), goal)

  def test_all_bosses(self) -> None:
    self.complete(0, 2, 4, 6)
    self.assertFalse(self.interface.is_goaled(5))
    self.complete(0, 2, 4, 6, 7)
    self.assertTrue(self.interface.is_goaled(5))
    self.assertFalse(self.interface.is_goaled(6))


class TestCollectibles(InterfaceTestBase):
  def test_treasures(self) -> None:
    self.pine.poke32(self.addr["treasures"][1][2], 1)
    self.pine.poke32(self.addr["treasures"][7][0], 5)
    stolen = self.interface.all_treasures_stolen()
    self.assertEqual(len(stolen), 8)
    self.assertTrue(all(len(row) == 3 for row in stolen))
    self.assertEqual(sum(sum(row) for row in stolen), 2)
    self.assertTrue(stolen[1][2])
    self.assertTrue(stolen[7][0])

  def test_loot(self) -> None:
    self.pine.poke32(self.addr["loot"][4], 1)
    stolen = self.interface.all_loot_stolen()
    self.assertEqual(len(stolen), len(LOOT))
    self.assertEqual([i for i, s in enumerate(stolen) if s], [4])

  def test_vaults(self) -> None:
    self.assertFalse(self.interface.all_vaults_opened())
    for address in self.addr["vaults"][1:]:
      self.pine.poke32(address, 1)
    self.assertEqual(self.interface.all_vault_statuses(), [False] + [True]*7)
    self.assertFalse(self.interface.all_vaults_opened())
    self.pine.poke32(self.addr["vaults"][0], 1)
    self.assertTrue(self.interface.all_vaults_opened())


class TestLootTables(InterfaceTestBase):
  def test_set_loot_table(self) -> None:
    episode = Sly2Episode.The_Black_Chateau
    self.interface.set_loot_table(episode, WIRE_LOOT)
    tables = self.addr["loot table"][0]
    for loot, locations in LOOT.items():
      for ep, large, slot in locations:
        if ep != 1:
          continue
        self.assertEqual(
          self.pine.peek32(tables[int(large)][slot-1]), LOOT_IDS[loot], loot
        )
    other_episodes = [
      address
      for i in range(1, 8)
      for table in self.addr["loot table"][i]
      for address in table
    ]
    self.assertFalse(any(self.pine.written(a) for a in other_episodes))

  def test_set_loot_table_odds(self) -> None:
    episode = Sly2Episode.Jailbreak
    odds = ((50, 30, 10, 5, 3, 2), (40, 40, 10, 5, 3, 2))
    self.interface.set_loot_table_odds(episode, odds)
    addresses = self.addr["loot table odds"][3]
    for i in range(2):
      for j in range(6):
        self.assertEqual(self.pine.peek32(addresses[i][j]), odds[i][j])

  def test_set_loot_chance(self) -> None:
    episode = Sly2Episode.A_Tangled_Web
    self.interface.set_loot_chance(episode, (0.25, 0.5))
    small, large = self.addr["loot chance"][4]
    self.assertEqual(self.pine.peek_float(small), 0.25)
    self.assertEqual(self.pine.peek_float(large), 0.5)

  def test_set_prices(self) -> None:
    loot_prices = {loot: i + 1 for i, loot in enumerate(LOOT_PRICES)}
    treasure_prices = {t: i + 100 for i, t in enumerate(TREASURE_PRICES)}
    self.interface.set_prices(loot_prices, treasure_prices)
    for loot, price in loot_prices.items():
      self.assertEqual(self.pine.peek32(self.addr["loot prices"][loot]), price)
    for treasure, price in treasure_prices.items():
      address = self.addr["treasure prices"][treasure]
      self.assertEqual(self.pine.peek32(address), price)


class TestCoins(InterfaceTestBase):
  def test_add_and_clamp(self) -> None:
    coins = self.addr["coins"]
    self.pine.poke32(coins, 100)
    self.interface.add_coins(50)
    self.assertEqual(self.interface.get_coins(), 150)
    self.interface.add_coins(-30)
    self.assertEqual(self.interface.get_coins(), 120)
    self.interface.add_coins(-500)
    self.assertEqual(self.interface.get_coins(), 0)

  def test_items_received(self) -> None:
    self.interface.set_items_received(7)
    self.assertEqual(self.interface.read_items_received(), 7)


class TestBindings(InterfaceTestBase):
  def test_get_signed(self) -> None:
    base = self.addr["sly bindings"]
    self.pine.poke32(base, 0xFFFF_FFFF)
    self.pine.poke32(base + 4, MEGA_JUMP_GADGET_ID)
    self.assertEqual(
      self.interface.get_sly_bindings(), [-1, MEGA_JUMP_GADGET_ID, 0]
    )

  def test_set_without_sly_object(self) -> None:
    self.interface.set_sly_binding(2)
    self.assertEqual(
      self.pine.peek32(self.addr["sly bindings"] + 8), MEGA_JUMP_GADGET_ID
    )
    self.assertEqual(len(self.pine.writes), 1)

  def test_set_with_sly_object(self) -> None:
    self.pine.poke32(self.addr["sly pointer"], HEAP)
    self.interface.set_sly_binding(1, 0x10)
    self.assertEqual(self.pine.peek32(self.addr["sly bindings"] + 4), 0x10)
    self.assertEqual(self.pine.peek32(HEAP + 0x1180 + 0xC), 0x10)

  def test_patch_mega_jump_unload(self) -> None:
    address = self.addr["unload mega jump"]
    self.pine.poke32(address, MEGA_JUMP_UNLOAD_CALL)
    self.interface.patch_mega_jump_unload()
    self.assertEqual(self.pine.peek32(address), 0)


class TestGuards(InterfaceTestBase):
  def test_walk_linear(self) -> None:
    guards = make_guard_list(self.pine, self.addr, 0, 3)
    self.assertEqual(list(self.interface._walk_guards()), guards)

  def test_walk_all_heads(self) -> None:
    make_guard_list(self.pine, self.addr, 0, 2)
    self.pine.poke32(self.addr["guard structs"][2], guard(5))
    self.assertEqual(
      list(self.interface._walk_guards()), [guard(0), guard(1), guard(5)]
    )

  def test_walk_stops_on_cycle(self) -> None:
    guards = make_guard_list(self.pine, self.addr, 0, 3)
    self.pine.poke32(guards[2] + 0x20, guards[0])
    self.assertEqual(list(self.interface._walk_guards()), guards)

  def test_walk_stops_on_implausible_length(self) -> None:
    make_guard_list(self.pine, self.addr, 0, MAX_GUARDS + 10)
    self.assertEqual(len(list(self.interface._walk_guards())), MAX_GUARDS)

  def test_walk_ignores_freed_head(self) -> None:
    self.pine.poke32(self.addr["guard structs"][0], 0x10)
    self.assertEqual(list(self.interface._walk_guards()), [])

  def test_despawn(self) -> None:
    guards = make_guard_list(self.pine, self.addr, 0, 2)
    self.pine.poke32(guards[1] + 0x54, 0)
    self.interface.despawn_guards()
    self.assertEqual(self.pine.peek32(guards[0] + 0x800 + 0xA0), 1)
    self.assertFalse(self.pine.written(0xA0))
    self.assertEqual(len(self.pine.writes), 1)

  def test_alert_and_release_only_targeting_guards(self) -> None:
    active = set_active_character(self.pine, self.addr)
    guards = make_guard_list(self.pine, self.addr, 2, 2)
    self.pine.poke32(guards[0] + 0x1110, active)
    self.interface.alert_guards()
    self.assertEqual(self.pine.peek32(guards[0] + 0x1100), 1)
    self.assertEqual(self.pine.peek32(guards[0] + 0x1114), 1)
    self.assertFalse(self.pine.written(guards[1] + 0x1100))
    self.interface.release_guards()
    self.assertEqual(self.pine.peek32(guards[0] + 0x1100), 0)

  def test_no_active_character(self) -> None:
    make_guard_list(self.pine, self.addr, 2, 2)
    self.interface.alert_guards()
    self.assertEqual(self.pine.writes, [])


class TestCharacter(InterfaceTestBase):
  def test_active_character_pointer_validated(self) -> None:
    self.assertEqual(self.interface.get_active_character(), 0)
    self.pine.poke32(self.addr["active character pointer"], 0x10)
    self.assertEqual(self.interface.get_active_character(), 0)
    active = set_active_character(self.pine, self.addr)
    self.assertEqual(self.interface.get_active_character(), active)

  def test_health_and_power(self) -> None:
    active = set_active_character(self.pine, self.addr)
    self.interface.set_current_health(1)
    self.interface.set_current_gadget_power(0)
    self.assertEqual(self.pine.peek32(self.pine.peek32(active + 0xe00)), 1)
    self.assertEqual(self.pine.peek32(self.pine.peek32(active + 0x12fc)), 0)

  def test_damage_type(self) -> None:
    self.assertEqual(self.interface.get_damage_type(), 0)
    active = set_active_character(self.pine, self.addr)
    self.pine.poke32(active + 0xe2c, 0x400)
    self.assertEqual(self.interface.get_damage_type(), 0x400)

  def test_kill_player(self) -> None:
    active = set_active_character(self.pine, self.addr)
    self.pine.poke32(self.addr["world id"], 0)
    self.interface.kill_player()
    self.assertFalse(self.pine.written(active + 0xdf4))
    self.pine.poke32(self.addr["world id"], 1)
    self.interface.kill_player()
    self.assertEqual(self.pine.peek32(active + 0xdf4), 8)

  def test_trap_values(self) -> None:
    self.interface.set_clock_speed(0.5)
    self.interface.set_friction(0.2)
    self.assertEqual(self.pine.peek_float(self.addr["clock speed"]), 0.5)
    self.assertAlmostEqual(
      self.pine.peek_float(self.addr["friction"]), 0.2, places=6
    )


class TestAlive(InterfaceTestBase):
  def locate(self, episode: int, map_id: int) -> None:
    set_location(self.pine, self.addr, episode, map_id)

  def test_no_active_character(self) -> None:
    self.locate(1, 2)
    self.assertTrue(self.interface.alive())

  def test_character_health(self) -> None:
    self.locate(1, 2)
    set_active_character(self.pine, self.addr, kind=8, health=50)
    self.assertTrue(self.interface.alive())
    self.pine.poke32(self.addr["health"]["Bentley"], 0)
    self.assertFalse(self.interface.alive())
    self.pine.poke32(self.addr["health"]["Sly"], 0)
    set_active_character(self.pine, self.addr, kind=9, health=50)
    self.assertTrue(self.interface.alive())

  def test_vehicle_health_by_map(self) -> None:
    cases = [
      (9, 5, 17, "Tank"),
      (8, 6, 29, "ChopperCanada1"),
      (7, 6, 30, "ChopperCanada2"),
      (9, 7, 33, "RCTank"),
      (8, 2, 8, "ChopperIndia"),
    ]
    for kind, episode, map_id, vehicle in cases:
      self.pine = FakePine()
      self.interface.pcsx2_interface = self.pine
      self.locate(episode, map_id)
      set_active_character(self.pine, self.addr, kind=kind, health=50)
      self.pine.poke32(self.addr["health"]["Murray"], 50)
      self.pine.poke32(self.addr["health"][vehicle], 50)
      self.assertTrue(self.interface.alive(), vehicle)
      self.pine.poke32(self.addr["health"][vehicle], 0)
      self.assertFalse(self.interface.alive(), vehicle)
      self.locate(episode, map_id + 1)
      self.assertTrue(self.interface.alive(), vehicle)

  def test_hackpack(self) -> None:
    self.locate(4, 14)
    set_active_character(self.pine, self.addr, kind=8, health=50)
    self.pine.poke32(self.addr["health"]["ChopperPrague"], 50)
    self.pine.poke32(self.addr["hackpack"], HEAP)
    self.pine.poke32(HEAP + 0x184, 10)
    self.assertTrue(self.interface.alive())
    self.pine.poke32(HEAP + 0x184, 0)
    self.assertFalse(self.interface.alive())
    self.locate(4, 16)
    self.assertTrue(self.interface.alive())


class TestStateChecks(InterfaceTestBase):
  def test_stuck_in_cairo(self) -> None:
    self.assertFalse(self.interface.stuck_in_cairo())
    self.pine.poke32(self.addr["savefile last world"], 3)
    self.assertTrue(self.interface.stuck_in_cairo())
    self.pine.poke32(self.addr["map id"], 2)
    self.assertFalse(self.interface.stuck_in_cairo())

  def test_in_safehouse(self) -> None:
    set_location(self.pine, self.addr, 1, 2)
    self.pine.poke32(self.addr["infobox string"], 306)
    self.assertTrue(self.interface.in_safehouse())
    for address, value in [
      (self.addr["job id"], 5),
      (self.addr["active character pointer"], HEAP),
      (self.addr["camera focus"], 1),
      (self.addr["infobox string"], 1),
      (self.addr["map id"], 3),
      (self.addr["world id"], 0),
    ]:
      old = self.pine.peek32(address)
      self.pine.poke32(address, value)
      self.assertFalse(self.interface.in_safehouse(), hex(address))
      self.pine.poke32(address, old)
    self.assertTrue(self.interface.in_safehouse())


class TestTickCache(InterfaceTestBase):
  def test_prefetch_serves_reads(self) -> None:
    a = self.addr
    self.pine.poke32(a["coins"], 42)
    self.pine.poke16(a["frame counter"], 7)
    self.pine.poke_bytes(a["gadgets"], bytes(range(1, 7)))
    self.interface.prefetch(
      [(4, a["coins"]), (2, a["frame counter"]), (6, a["gadgets"])]
    )
    self.assertEqual(self.pine.batches, 1)
    self.pine.clear_counts()
    self.assertEqual(self.interface._read32(a["coins"]), 42)
    self.assertEqual(self.interface._read16(a["frame counter"]), 7)
    self.assertEqual(
      self.interface._read_bytes(a["gadgets"], 6), bytes(range(1, 7))
    )
    self.assertEqual(self.interface._read32(a["gadgets"]), 0x04030201)
    self.assertEqual((self.pine.reads, self.pine.batches), (0, 0))

    # Not prefetched, and a byte range split differently from its chunks
    self.interface._read32(a["map id"])
    self.interface._read_bytes(a["gadgets"], 5)
    self.assertEqual((self.pine.reads, self.pine.batches), (2, 0))

  def test_cache_is_a_snapshot_until_cleared(self) -> None:
    address = self.addr["coins"]
    self.interface.prefetch([(4, address)])
    self.pine.poke32(address, 9)
    self.assertEqual(self.interface._read32(address), 0)
    self.interface.clear_cache()
    self.assertEqual(self.interface._read32(address), 9)

  def test_batch_read_merges_hits_and_misses(self) -> None:
    a, b, c = 0x200000, 0x200004, 0x200008
    for address, value in [(a, 1), (b, 2), (c, 3)]:
      self.pine.poke32(address, value)
    self.interface.prefetch([(4, a), (4, c)])
    self.pine.clear_counts()
    self.assertEqual(self.interface._batch_read32([c, b, a]), [3, 2, 1])
    self.assertEqual((self.pine.reads, self.pine.batches), (0, 1))
    self.pine.clear_counts()
    self.assertEqual(self.interface._batch_read32([a, c]), [1, 3])
    self.assertEqual((self.pine.reads, self.pine.batches), (0, 0))

  def test_writes_update_cache_and_skip_when_unchanged(self) -> None:
    address = 0x200000
    self.pine.poke32(address, 5)
    self.interface.prefetch([(4, address)])
    self.interface._write32(address, 5)
    self.assertEqual(self.pine.writes, [])
    self.interface._write32(address, 6)
    self.assertEqual(len(self.pine.writes), 1)
    self.assertEqual(self.interface._read32(address), 6)
    self.interface._write32(address, 6)
    self.interface._batch_write32([(address, 6)])
    self.assertEqual(len(self.pine.writes), 1)
    self.interface._batch_write32([(address, 6), (address + 4, 1)])
    self.assertEqual(
      self.pine.writes[1:], [("bw32", address + 4, (1).to_bytes(4, "little"))]
    )

  def test_overlapping_write_invalidates_chunks(self) -> None:
    address = self.addr["gadgets"]
    self.interface.prefetch([(6, address)])
    self.interface._write_bytes(address + 2, bytes([0xAA, 0xBB]))
    self.pine.clear_counts()
    self.assertEqual(
      self.interface._read_bytes(address, 6), bytes([0, 0, 0xAA, 0xBB, 0, 0])
    )
    self.assertEqual(self.pine.reads, 1)

  def test_write_outside_cache_is_not_skipped(self) -> None:
    address = 0x200000
    self.pine.poke32(address, 5)
    self.interface._write32(address, 5)
    self.assertEqual(len(self.pine.writes), 1)

  def test_float_round_trip(self) -> None:
    address = self.addr["clock speed"]
    self.interface._write_float(address, 0.5)
    self.assertEqual(self.interface._read_float(address), 0.5)
    self.interface._write_float(address, 0.5)
    self.assertEqual(len(self.pine.writes), 1)

  def test_tick_state_is_two_batches(self) -> None:
    set_location(self.pine, self.addr, 1, 2)
    build_dag(self.pine, self.addr)
    self.interface.clear_cache()
    self.interface.prefetch_tick_state()
    self.assertEqual(self.pine.batches, 2)
    self.pine.clear_counts()
    self.interface.in_safehouse()
    self.interface.in_cutscene()
    self.interface.is_infobox()
    self.interface.alive()
    self.interface.all_treasures_stolen()
    self.interface.all_loot_stolen()
    self.interface.all_vault_statuses()
    self.interface.get_operation_completion()
    self.interface.read_powerups()
    self.interface.get_sly_bindings()
    self.interface.get_bottles(Sly2Episode.Jailbreak)
    self.interface.jobs_completed([4, 10, 36])
    self.interface.tasks_completed([5, 6])
    self.assertEqual((self.pine.reads, self.pine.batches), (0, 0))

  def test_tick_state_skips_dag_while_loading(self) -> None:
    set_location(self.pine, self.addr, 1, 2)
    self.pine.poke32(self.addr["loading"], 2)
    self.interface.prefetch_tick_state()
    self.assertEqual(self.pine.reads, 0)

  def test_cycle_counts_prefetched_tick(self) -> None:
    set_location(self.pine, self.addr, 1, 2)
    build_dag(self.pine, self.addr)
    # First prefetch walks the DAG; measure a steady tick after it
    self.interface.clear_cache()
    self.interface.prefetch_tick_state()
    self.interface.take_cycle_counts()
    self.interface.clear_cache()
    self.interface.prefetch_tick_state()
    self.interface.in_safehouse()
    self.interface.alive()
    self.interface.set_clock_speed(1.0)
    counts = self.interface.take_cycle_counts()
    self.assertEqual(counts.batches, 2)
    self.assertGreaterEqual(counts.reads, 2)
    self.assertEqual(counts.writes, 1)
    self.assertEqual((counts.pine_reads, counts.pine_writes), (0, 1))
    self.assertEqual(self.interface.take_cycle_counts(), CycleCounts())


class TestDagCache(InterfaceTestBase):
  def setUp(self) -> None:
    super().setUp()
    set_location(self.pine, self.addr, 1, 2)
    build_dag(self.pine, self.addr)
    self.pine.clear_counts()

  def test_walk_once(self) -> None:
    # Every lookup reads the root and map id to validate the cache; those
    # are hits within a tick, single reads here.
    self.assertEqual(self.interface._get_job_address(10), dag_node(10))
    self.assertEqual(self.pine.reads, 2 + 10)
    self.pine.clear_counts()
    self.assertEqual(self.interface._get_job_address(10), dag_node(10))
    self.assertEqual(self.interface._get_job_address(3), dag_node(3))
    self.assertEqual(self.pine.reads, 2 + 2)
    self.pine.clear_counts()
    self.assertEqual(self.interface._get_job_address(20), dag_node(20))
    self.assertEqual(self.pine.reads, 2 + 10)

  def test_invalidated_by_root_or_map(self) -> None:
    self.interface._get_job_address(5)
    self.pine.poke32(dag_node(1) + 0x20, dag_node(7))
    self.assertEqual(self.interface._get_job_address(2), dag_node(2))
    self.pine.poke32(self.addr["map id"], 3)
    self.assertEqual(self.interface._get_job_address(2), dag_node(7))
    self.pine.poke32(self.addr["map id"], 2)
    self.pine.poke32(self.addr["DAG root"], dag_node(1))
    self.assertEqual(self.interface._get_job_address(1), dag_node(7))
    self.interface.invalidate_dag()
    self.pine.poke32(dag_node(1) + 0x20, dag_node(2))
    self.assertEqual(self.interface._get_job_address(1), dag_node(2))

  def test_parents_cached(self) -> None:
    set_parents(self.pine, 3, [1, 2])
    self.assertEqual(
      self.interface._get_task_parents(3), [dag_node(1), dag_node(2)]
    )
    set_parents(self.pine, 3, [1])
    self.assertEqual(
      self.interface._get_task_parents(3), [dag_node(1), dag_node(2)]
    )
    self.interface.invalidate_dag()
    self.assertEqual(self.interface._get_task_parents(3), [dag_node(1)])


class TestFixJobs(InterfaceTestBase):
  def setUp(self) -> None:
    super().setUp()
    build_dag(self.pine, self.addr)
    set_location(self.pine, self.addr, 1, 2)

  def test_no_op_when_job_active(self) -> None:
    set_location(self.pine, self.addr, 1, 2, job=4)
    set_job_status(self.pine, 4, 2)
    self.interface.fix_jobs()
    self.assertEqual(self.pine.writes, [])
    self.assertEqual(job_status(self.pine, 4), 2)

  def test_repairs_status_two_job(self) -> None:
    set_job_status(self.pine, 4, 2)
    self.interface.fix_jobs()
    self.assertEqual(job_status(self.pine, 4), 1)

  def test_zeros_same_mission_successors(self) -> None:
    set_job_status(self.pine, 4, 2)
    set_job_mission(self.pine, 4, 5)
    for i in (5, 6):
      set_job_mission(self.pine, i, 5)
      set_job_status(self.pine, i, 1)
    set_job_mission(self.pine, 7, 9)
    set_job_status(self.pine, 7, 3)
    self.interface.fix_jobs()
    self.assertEqual(job_status(self.pine, 4), 1)
    self.assertEqual(job_status(self.pine, 5), 0)
    self.assertEqual(job_status(self.pine, 6), 0)
    self.assertEqual(job_status(self.pine, 7), 3)


class TestStaleTriggers(InterfaceTestBase):
  def setUp(self) -> None:
    super().setUp()
    build_dag(self.pine, self.addr)
    set_location(self.pine, self.addr, 7, 34)

  def test_completes_trigger_of_finished_job(self) -> None:
    set_job_status(self.pine, 40, 3)
    set_job_status(self.pine, 42, 1)
    self.interface.disarm_stale_triggers()
    self.assertEqual(job_status(self.pine, 42), 3)

  def test_leaves_unfinished_job(self) -> None:
    set_job_status(self.pine, 40, 1)
    set_job_status(self.pine, 42, 0)
    self.interface.disarm_stale_triggers()
    self.assertEqual(self.pine.writes, [])

  def test_leaves_started_trigger(self) -> None:
    set_job_status(self.pine, 40, 3)
    set_job_status(self.pine, 42, 2)
    self.interface.disarm_stale_triggers()
    self.assertEqual(job_status(self.pine, 42), 2)

  def test_other_episode(self) -> None:
    set_location(self.pine, self.addr, 1, 2)
    set_job_status(self.pine, 40, 3)
    set_job_status(self.pine, 42, 1)
    self.interface.disarm_stale_triggers()
    self.assertEqual(job_status(self.pine, 42), 1)


def make_interactables(
  pine: FakePine, addr: dict, vtables: list[int], users: int = 6
) -> list[int]:
  entities = [0x900000 + 0x400*i for i in range(len(vtables))]
  pine.poke32(addr["interactables"], entities[0] if entities else 0)
  for entity, vtable, following in zip(
    entities, vtables, entities[1:] + [0]
  ):
    pine.poke32(entity + 0xC, vtable)
    pine.poke32(entity + PEDESTAL_USERS, users)
    pine.poke32(entity + INTERACTABLE_NEXT, following)
  return entities


class TestTreasurePickup(InterfaceTestBase):
  def test_opens_pedestals_to_sly(self) -> None:
    entities = make_interactables(
      self.pine, self.addr, [0x123456, PEDESTAL_VTABLE, PEDESTAL_VTABLE]
    )
    self.interface.allow_sly_treasure_pickup()
    self.assertEqual(self.pine.peek32(entities[0] + PEDESTAL_USERS), 6)
    self.assertEqual(self.pine.peek32(entities[1] + PEDESTAL_USERS), 7)
    self.assertEqual(self.pine.peek32(entities[2] + PEDESTAL_USERS), 7)

  def test_leaves_open_pedestals(self) -> None:
    make_interactables(self.pine, self.addr, [PEDESTAL_VTABLE], users=7)
    self.interface.allow_sly_treasure_pickup()
    self.assertEqual(self.pine.writes, [])

  def test_empty_list(self) -> None:
    make_interactables(self.pine, self.addr, [])
    self.interface.allow_sly_treasure_pickup()
    self.assertEqual(self.pine.writes, [])

  def test_stops_on_cycle(self) -> None:
    entities = make_interactables(
      self.pine, self.addr, [PEDESTAL_VTABLE, PEDESTAL_VTABLE]
    )
    self.pine.poke32(entities[1] + INTERACTABLE_NEXT, entities[0])
    self.assertEqual(list(self.interface._walk_interactables()), entities)


def make_entity(
  pine: FakePine, address: int, children: list[int], registered: bool
) -> None:
  if children:
    pine.poke32(address + ENTITY_CHILD_LINK, ENTITY_NEXT)
    pine.poke32(address + ENTITY_FIRST_CHILD, children[0])
    pine.poke32(address + ENTITY_LAST_CHILD, children[-1])
    for previous, child, following in zip(
      [0] + children, children, children[1:] + [0]
    ):
      pine.poke32(child + 0x10, address)
      pine.poke32(child + ENTITY_NEXT, following)
      pine.poke32(child + ENTITY_PREV, previous)
  if registered:
    slot = 0x47F000 + (address >> 8) * 8
    pine.poke32(slot, 0x25)
    pine.poke32(slot + 4, address)
    pine.poke32(address + ENTITY_SLOT, slot)
  else:
    pine.poke32(address + ENTITY_SLOT, 0x25)


class TestMegaJumpPack(InterfaceTestBase):
  SLY = 0xB3C000
  NODE = 0xB9E000
  CHILD = 0x13EE000
  GROUP = 0x13F2000
  LIGHTS = [0x13F2400, 0x13F2600, 0x13F2800]

  def setUp(self) -> None:
    super().setUp()
    self.pine.poke32(self.addr["sly pointer"], self.SLY)
    self.pine.poke32(self.SLY + SLY_BACK_NODE, self.NODE)
    self.free = self.addr["entity manager"] + ENTITY_MANAGER_FREE
    self.pine.poke32(self.free, 5)
    self.pine.clear_writes()

  def build_pack(self, registered: bool = True) -> None:
    make_entity(self.pine, self.NODE, [self.CHILD], True)
    make_entity(self.pine, self.CHILD, [self.GROUP] + self.LIGHTS, registered)
    for entity in [self.GROUP] + self.LIGHTS:
      make_entity(self.pine, entity, [], registered)

  def slot(self, entity: int) -> int:
    return self.pine.peek32(entity + ENTITY_SLOT)

  def test_unregisters_pack_subtree(self) -> None:
    self.build_pack()
    slots = {e: self.slot(e) for e in [self.CHILD, self.GROUP] + self.LIGHTS}
    self.interface.hide_mega_jump_pack()
    for entity, slot in slots.items():
      self.assertEqual(self.pine.peek32(slot), 0)
      self.assertEqual(self.pine.peek32(slot + 4), 0)
      self.assertEqual(self.slot(entity), 0x25)
    self.assertEqual(self.pine.peek32(self.free), 10)

  def test_unlinks_pack_from_node(self) -> None:
    self.build_pack()
    self.interface.hide_mega_jump_pack()
    self.assertEqual(self.pine.peek32(self.NODE + ENTITY_FIRST_CHILD), 0)
    self.assertEqual(self.pine.peek32(self.NODE + ENTITY_LAST_CHILD), 0)
    self.assertEqual(self.pine.peek32(self.CHILD + ENTITY_NEXT), 0)
    self.assertEqual(self.pine.peek32(self.CHILD + ENTITY_PREV), 0)
    self.assertEqual(
      self.pine.peek32(self.CHILD + ENTITY_FIRST_CHILD), self.GROUP
    )
    self.pine.clear_writes()
    self.interface.hide_mega_jump_pack()
    self.assertEqual(self.pine.writes, [])

  def test_keeps_treasure_linked(self) -> None:
    treasure = 0xE86000
    self.build_pack()
    make_entity(self.pine, self.NODE, [self.CHILD, treasure], True)
    self.pine.poke32(treasure + 0xC, TREASURE_VTABLE)
    self.interface.hide_mega_jump_pack()
    self.assertEqual(self.pine.peek32(self.NODE + ENTITY_FIRST_CHILD), treasure)
    self.assertEqual(self.pine.peek32(self.NODE + ENTITY_LAST_CHILD), treasure)
    self.assertEqual(self.pine.peek32(treasure + ENTITY_PREV), 0)
    self.assertEqual(self.pine.peek32(treasure + ENTITY_NEXT), 0)

  def test_leaves_held_treasure(self) -> None:
    treasure, part = 0xE86000, 0xE89000
    self.build_pack()
    make_entity(self.pine, self.NODE, [self.CHILD, treasure], True)
    make_entity(self.pine, treasure, [part], True)
    make_entity(self.pine, part, [], True)
    self.pine.poke32(treasure + 0xC, TREASURE_VTABLE)
    slots = {e: self.slot(e) for e in (treasure, part)}
    self.interface.hide_mega_jump_pack()
    for entity, slot in slots.items():
      self.assertEqual(self.pine.peek32(slot + 4), entity)
      self.assertEqual(self.slot(entity), slot)
    self.assertEqual(self.slot(self.CHILD), 0x25)

  def test_leaves_node_registered(self) -> None:
    self.build_pack()
    slot = self.slot(self.NODE)
    self.interface.hide_mega_jump_pack()
    self.assertEqual(self.pine.peek32(slot + 4), self.NODE)
    self.assertEqual(self.slot(self.NODE), slot)

  def test_only_unlinks_when_unregistered(self) -> None:
    self.build_pack(registered=False)
    self.interface.hide_mega_jump_pack()
    self.assertEqual(self.pine.peek32(self.NODE + ENTITY_FIRST_CHILD), 0)
    self.assertEqual(self.pine.peek32(self.free), 5)
    self.assertEqual(self.slot(self.CHILD), 0x25)

  def test_no_writes_without_pack(self) -> None:
    make_entity(self.pine, self.NODE, [], True)
    self.interface.hide_mega_jump_pack()
    self.assertEqual(self.pine.writes, [])

  def test_no_writes_without_sly(self) -> None:
    self.pine.poke32(self.addr["sly pointer"], 0)
    self.interface.hide_mega_jump_pack()
    self.assertEqual(self.pine.writes, [])

  def test_stops_on_cycle(self) -> None:
    self.build_pack()
    self.pine.poke32(self.LIGHTS[-1] + ENTITY_NEXT, self.GROUP)
    self.pine.poke32(self.CHILD + ENTITY_LAST_CHILD, 0)
    descendants = list(self.interface._walk_entity_descendants(self.NODE))
    self.assertEqual(descendants, [self.CHILD, self.GROUP] + self.LIGHTS)


class TestInfobox(InterfaceTestBase):
  def setUp(self) -> None:
    super().setUp()
    set_infobox_pointers(self.pine, self.addr)
    set_string_table(self.pine, self.addr, 1)
    set_location(self.pine, self.addr, 1, 5, job=4)

  def infobox_ptr(self) -> int:
    return self.pine.peek32(self.addr["infobox"])

  def test_is_infobox(self) -> None:
    self.pine.poke32(self.infobox_ptr() + 0x64, 2)
    self.assertTrue(self.interface.is_infobox())
    self.pine.poke32(self.infobox_ptr() + 0x64, 1)
    self.assertFalse(self.interface.is_infobox())

  def test_current_infobox(self) -> None:
    self.pine.poke32(self.addr["infobox string"], 42)
    self.assertEqual(self.interface.current_infobox(), 42)

  def test_set_infobox_writes_text_and_state(self) -> None:
    self.interface.set_infobox("hello")
    buffer = string_buffer(self.pine, self.addr, "infobox", 1)
    self.assertEqual(self.pine.peek_cstring(buffer), b" "*10 + b"hello")
    self.assertEqual(self.pine.peek32(self.addr["infobox string"]), 1)
    self.assertEqual(self.pine.peek32(self.infobox_ptr() + 0x64), 2)
    self.assertEqual(self.pine.peek_float(self.addr["infobox duration"]), 10.0)
    self.assertEqual(self.pine.peek32(self.addr["infobox scrolling"]), 1)

  def test_set_infobox_skips_title_screen(self) -> None:
    set_location(self.pine, self.addr, 0, 0)
    self.interface.set_infobox("hello")
    self.assertEqual(self.pine.writes, [])

  def test_set_infobox_skips_safehouse(self) -> None:
    set_location(self.pine, self.addr, 1, 2)
    self.pine.poke32(self.addr["infobox string"], 305)
    self.interface.set_infobox("hello")
    self.assertEqual(self.pine.writes, [])

  def test_disable_infobox_when_showing(self) -> None:
    self.pine.poke32(self.infobox_ptr() + 0x64, 2)
    self.pine.poke32(self.addr["infobox scrolling"], 2)
    self.interface.disable_infobox()
    self.assertEqual(self.pine.peek32(self.infobox_ptr() + 0x64), 1)
    self.assertEqual(self.pine.peek32(self.addr["infobox scrolling"]), 3)

  def test_disable_infobox_noop_when_already_off(self) -> None:
    self.pine.poke32(self.infobox_ptr() + 0x64, 1)
    self.interface.disable_infobox()
    self.assertEqual(self.pine.writes, [])
