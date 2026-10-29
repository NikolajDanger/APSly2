"""HypnosisInstall against FakePine: a fake character with a walk blend,
model part arrays and children, the game functions the installer calls
served through the cave call slot."""

import math
import struct
import unittest

from ..data.Constants import CAVE_HYPNOSIS_BANK_LOAD
from ..data.Hypnosis import (
  EYES, OVERLAY, OVERLAY_CLUSTER, OVERLAY_OBJECT, OVERLAY_WORDS, PHASES,
  WALKS, decode
)
from ..HypnosisInstall import (
  BANK_BUSY,
  CONSTANT_CONTROLLER,
  DRAW_IN_FRONT,
  KEYED_CONTROLLER,
  NEW_OBJECT,
  OVERLAY_OFF,
  OVERLAY_ON,
  PAD_MASK,
  POST_LOAD,
  SOUND_PLAY,
  SOUND_STOP,
  SOUND_UNLOAD,
  STATE_BANK,
  STATE_MASK,
  STATE_OVERLAY,
  STATE_PACE_ON,
  STATE_PARAMS,
  STATE_VOICE,
  keys,
)
from ..LootInstall import HIDDEN_FLAG, PART_SIZE
from .client_base import InterfaceTestBase

ENTITY = 0x0140_0000
JOINTS = 0x0141_0000
BLEND = 0x0142_0000
TABLE = 0x0142_0100
CONTROLLERS = 0x0142_1000
SOURCES = 0x0143_0000
RECORDS = 0x0144_0000
PARTS = 0x0144_1000
CHAIN = 0x0144_2000
REF = 0x0144_3000
BOUNDS = 0x0144_4000
CHILDREN = 0x0145_0000
HEAP = 0x0150_0000
OBJECT = 0x0160_0000
MATERIAL_BASE = 0x0100_0000
SUB_OBJECT = 0x00FB_CA20
BANK_HANDLE = 0x1CBD00
VOICE = 0x85000346
UNLOADED = 0xD0D0
TEXTURE_BLOCK = 0x181A
CLUT_BLOCK = 0x1804
SLY, BENTLEY = 7, 8
BENTLEY_EYE_SCALE = 63


class HypnosisTestBase(InterfaceTestBase):
  def setUp(self) -> None:
    super().setUp()
    self.pine.poke32(self.addr["heap bottom"], HEAP)
    self.calls: list[tuple[int, list[int]]] = []
    self.pine.cave_functions = {
      NEW_OBJECT: self.serve(OBJECT),
      POST_LOAD: self.serve(0),
      CAVE_HYPNOSIS_BANK_LOAD: self.serve(BANK_HANDLE),
      SOUND_PLAY: self.serve_play,
      SOUND_STOP: self.serve(1),
      SOUND_UNLOAD: self.serve(UNLOADED),
      OVERLAY_ON: self.serve_state(3),
      OVERLAY_OFF: self.serve_state(4),
    }
    self.install_cave()
    self.installer = self.interface.hypnosis_installer
    self.pine.poke32(self.addr["active character pointer"], ENTITY)
    self.place_texture_records()

  def serve(self, result: int):  # noqa: ANN201
    def served(args: list[int]) -> int:
      self.calls.append((result, args))
      return result
    return served

  def serve_play(self, args: list[int]) -> int:
    self.pine.poke32(args[2], VOICE)
    self.calls.append((SOUND_PLAY, args))
    return 1

  def serve_state(self, state: int):  # noqa: ANN201
    def served(args: list[int]) -> int:
      self.pine.poke32(args[0] + 0x58, state)
      self.calls.append((state, args))
      return 0
    return served

  def called(self, function_result: int) -> list[list[int]]:
    return [args for result, args in self.calls if result == function_result]

  def place_texture_records(self) -> None:
    start, _ = self.addr["texture records"]
    self.pine.poke_bytes(start, struct.pack(
      "<10I", 0x65D, 1, 8 | (8 << 16), 0x14, 32, 0, 2, 0, TEXTURE_BLOCK, 0
    ))
    self.pine.poke_bytes(start + 0x40, struct.pack(
      "<8I", 0x65E, 1, 0, 0, 0x20, 0, 0x13 << 20, (1 << 29) | (CLUT_BLOCK << 5)
    ))

  def build_character(self, character_id: int, elements: list[int]) -> None:
    """A character entity: its walk blend with a channel per element (plus
    one the walk does not cover and one with flag bits), two model parts
    sharing a projection buffer, and two children"""
    pine = self.pine
    walk = WALKS[character_id]
    pine.poke32(ENTITY + 0xC, walk.vtable)
    pine.poke32(ENTITY + 0x50, 139)
    pine.poke32(ENTITY + 0x54, JOINTS)
    pine.poke32(ENTITY + walk.blend, BLEND)
    rows = [(e << 20) | character_id for e in elements] + [
      (250 << 20) | character_id, (1 << 28) | (elements[0] << 20)
    ]
    pine.poke32(BLEND + 0x5C, len(rows))
    pine.poke32(BLEND + 0x60, TABLE)
    for i, word in enumerate(rows):
      controller = CONTROLLERS + 0x30 * i
      pine.poke32(TABLE + 8*i, word)
      pine.poke32(TABLE + 8*i + 4, controller)
      pine.poke32(controller + 0x20, SOURCES + 0x20 * i)
      pine.poke32(controller + 0x24, SOURCES + 0x20 * i + 0x10)
    pine.poke32(ENTITY + 0xB8, 2)
    pine.poke32(ENTITY + 0xBC, RECORDS)
    pine.poke32(ENTITY + 0xC0, PARTS)
    pine.poke32(ENTITY + 0xC4, BOUNDS)
    # A main chain: one ref tag to the projection buffer, then an end tag
    pine.poke_bytes(CHAIN, struct.pack("<IIII", 3 << 28 | 2, REF, 0, 0))
    pine.poke_bytes(CHAIN + 16, struct.pack("<IIII", 7 << 28, 0, 0, 0))
    pine.poke_bytes(
      REF, bytes(16) + struct.pack("<I", 0x4B00_1234) + bytes(12)
    )
    for i in range(2):
      pine.poke_bytes(PARTS + PART_SIZE*i, struct.pack(
        "<10I", 0x3000 + i, JOINTS + 0x100*(10 + i), 0, 0x0282_4820, CHAIN,
        CHAIN - MATERIAL_BASE, 0, 0, SUB_OBJECT if i else 0, 0
      ))
      pine.poke_bytes(RECORDS + 0x14*i, struct.pack("<5I", 4, 0, 0, 0, i))
      pine.poke_bytes(BOUNDS + 0x18*i, bytes([i]) * 0x18)
    pine.poke32(ENTITY + 0x64, CHILDREN)
    pine.poke32(CHILDREN + 0x18, 316)
    pine.poke32(CHILDREN + 0x24, CHILDREN + 0x100)
    pine.poke32(CHILDREN + 0x100 + 0x18, 999)
    pine.poke32(CHILDREN + 0x100 + 0x24, 0)
    self.interface.clear_cache()

  def sources(self, i: int) -> tuple[int, int]:
    controller = CONTROLLERS + 0x30 * i
    return (
      self.pine.peek32(controller + 0x20), self.pine.peek32(controller + 0x24)
    )

  def eye_entries(self) -> list[tuple[int, ...]]:
    parts = self.pine.peek32(ENTITY + 0xC0)
    count = self.pine.peek32(ENTITY + 0xB8)
    return [
      struct.unpack(
        "<10I", self.pine.peek_bytes(parts + PART_SIZE*i, PART_SIZE)
      )
      for i in range(count)
    ]


class TestKeys(unittest.TestCase):
  def test_closes_the_loop(self) -> None:
    poses = [(float(k), 0.0, -float(k)) for k in range(4)]
    data = keys(poses, 2.0, False)
    self.assertEqual(len(data), 5 * 0x20)
    unpacked = [struct.unpack_from("<3ff3ff", data, 0x20*k) for k in range(5)]
    self.assertEqual([k[3] for k in unpacked], [0.0, 0.5, 1.0, 1.5, 2.0])
    self.assertEqual(unpacked[4][:3], unpacked[0][:3])
    self.assertEqual(unpacked[1][4:7], (2.0, 0.0, -2.0))

  def test_rotation_wraps_whole_turns(self) -> None:
    step = 2 * math.pi / 4
    poses = [(k * step, 0.0, 0.0) for k in range(4)]
    data = keys(poses, 1.0, True)
    last = struct.unpack_from("<3ff3ff", data, 0x20*4)
    self.assertAlmostEqual(last[0], 2 * math.pi, places=5)
    self.assertAlmostEqual(last[4], 4 * step, places=5)


class TestHypnosisInstaller(HypnosisTestBase):
  def test_character_of(self) -> None:
    self.build_character(SLY, [82])
    self.assertEqual(self.installer.character_of(ENTITY), SLY)
    self.assertIsNone(self.installer.character_of(0))
    self.pine.poke32(ENTITY + 0xC, 0x12345678)
    self.interface.clear_cache()
    self.assertIsNone(self.installer.character_of(ENTITY))
    self.assertFalse(self.installer.apply(ENTITY))

  def test_apply_builds_the_map_and_switches_on(self) -> None:
    channels = WALKS[SLY].channels
    elements = sorted(channels)[:3]
    self.build_character(SLY, elements)
    self.assertTrue(self.interface.apply_hypnosis())
    pine = self.pine
    state = self.addr["hypnosis state"]

    # The overlay: the object's words and its animation data relocated
    self.assertEqual(self.called(OBJECT), [[0x7E, 0, 0xFEE0, 0xFFFFFFFF]])
    self.assertEqual(self.called(0), [[OBJECT, 0, 0, 0]])
    cluster_base = pine.peek32(OBJECT + 0x54)
    self.assertGreaterEqual(cluster_base, HEAP)
    words = struct.unpack("<31I", pine.peek_bytes(OBJECT + 0x50, 0x7C))
    for i, (raw, word) in enumerate(zip(OVERLAY_WORDS, words)):
      if i == 2:
        continue  # the state, moved on by the overlay-on call
      if OVERLAY_CLUSTER[0] <= raw < OVERLAY_CLUSTER[1]:
        self.assertEqual(word, raw - OVERLAY_CLUSTER[0] + cluster_base)
      elif raw == OVERLAY_OBJECT:
        self.assertEqual(word, OBJECT)
      else:
        self.assertEqual(word, raw)
    cluster = decode(OVERLAY)
    first = struct.unpack_from("<I", cluster, 0)[0]
    self.assertEqual(pine.peek32(cluster_base), first)
    self.assertEqual(pine.peek32(state + STATE_OVERLAY), OBJECT)
    self.assertEqual(pine.peek32(OBJECT + 0x58), 3)
    thresholds = struct.unpack("<fff", pine.peek_bytes(state + 0x14, 12))
    for threshold, clip in zip(thresholds, (0.6, 2.0, 0.3)):
      self.assertAlmostEqual(threshold, clip - 0.025, places=6)

    # The sound: bank loaded from a claimed buffer, the voice played
    self.assertEqual(len(self.called(BANK_HANDLE)), 1)
    self.assertEqual(pine.peek32(state + STATE_BANK), BANK_HANDLE)
    self.assertEqual(pine.peek32(state + STATE_PARAMS), BANK_HANDLE)
    self.assertEqual(pine.peek32(state + STATE_PARAMS + 0x28), 3)
    self.assertEqual(pine.peek32(state + STATE_VOICE), VOICE)

    # The walk: every covered channel's sources swapped for built ones
    for i in range(len(elements)):
      for source in self.sources(i):
        self.assertGreaterEqual(source, HEAP)
        kind, n, key_pointer, _ = struct.unpack(
          "<4I", pine.peek_bytes(source, 16)
        )
        self.assertEqual(kind, KEYED_CONTROLLER)
        self.assertEqual(n, PHASES + 1)
        self.assertGreaterEqual(key_pointer, HEAP)
    self.assertEqual(self.sources(3), (SOURCES + 0x60, SOURCES + 0x70))
    self.assertEqual(self.sources(4), (SOURCES + 0x80, SOURCES + 0x90))

    # The eyes: appended, shown, bound to the resident texture
    entries = self.eye_entries()
    self.assertEqual(len(entries), 4)
    self.assertEqual([e[0] for e in entries[:2]], [0x3000, 0x3001])
    self.assertEqual([e[0] for e in entries[2:]], [p.part_id for p in EYES])
    for part, entry in zip(EYES, entries[2:]):
      self.assertEqual(entry[1], JOINTS + 0x100 * part.joint)
      self.assertEqual(entry[3], part.flags)
      self.assertEqual(entry[8], SUB_OBJECT)
      self.assertEqual((entry[4] - entry[5]) & 0xFFFFFFFF, MATERIAL_BASE)
    tags = struct.unpack("<IIII", pine.peek_bytes(entries[2][4], 16))
    ref0 = tags[1]
    self.assertGreaterEqual(ref0, HEAP)
    buffer = pine.peek_bytes(ref0, 0x200)
    self.assertIn(struct.pack("<I", 0x4B00_1234), buffer)
    low, high = struct.unpack_from("<2I", buffer, 0xA4)
    self.assertEqual(low & 0x3FFF, TEXTURE_BLOCK)
    self.assertEqual((high >> 5) & 0x3FFF, CLUT_BLOCK)
    self.assertTrue(pine.peek32(ENTITY + 0xD4) & DRAW_IN_FRONT)
    self.assertTrue(pine.peek32(CHILDREN + 0xD4) & DRAW_IN_FRONT)
    self.assertEqual(pine.peek32(CHILDREN + 0x100 + 0xD4), 0)

    # The cave hook armed
    self.assertEqual(pine.peek32(state + STATE_PACE_ON), 1)
    self.assertEqual(pine.peek32(state + STATE_MASK), PAD_MASK)

  def test_remove_restores_everything(self) -> None:
    elements = sorted(WALKS[SLY].channels)[:2]
    self.build_character(SLY, elements)
    self.assertTrue(self.installer.apply(ENTITY))
    self.interface.end_hypnosis()
    pine = self.pine
    state = self.addr["hypnosis state"]
    self.assertEqual(self.sources(0), (SOURCES, SOURCES + 0x10))
    self.assertEqual(self.sources(1), (SOURCES + 0x20, SOURCES + 0x30))
    for entry in self.eye_entries()[2:]:
      self.assertEqual(entry[3] & HIDDEN_FLAG, HIDDEN_FLAG)
    self.assertEqual(pine.peek32(ENTITY + 0xD4) & DRAW_IN_FRONT, 0)
    self.assertEqual(pine.peek32(CHILDREN + 0xD4) & DRAW_IN_FRONT, 0)
    self.assertEqual(pine.peek32(state + STATE_PACE_ON), 0)
    self.assertEqual(pine.peek32(state + STATE_MASK), 0)
    self.assertEqual(pine.peek32(OBJECT + 0x58), 4)
    self.assertEqual(self.called(1)[-1], [VOICE, 0, 0, 0])
    self.assertEqual(pine.peek32(state + STATE_VOICE), 0)
    self.assertEqual(self.called(UNLOADED), [[BANK_HANDLE, 0, 0, 0]])
    self.assertEqual(pine.peek32(state + STATE_BANK), 0)
    self.assertIsNone(self.installer.active)
    self.interface.end_hypnosis()
    self.assertEqual(len(self.called(4)), 1)

  def test_apply_again_reuses_the_build(self) -> None:
    self.build_character(SLY, sorted(WALKS[SLY].channels)[:1])
    self.assertTrue(self.installer.apply(ENTITY))
    bottom = self.pine.peek32(self.addr["heap bottom"])
    calls = len(self.calls)
    self.assertTrue(self.installer.apply(ENTITY))
    self.assertEqual(self.pine.peek32(self.addr["heap bottom"]), bottom)
    self.assertEqual(len(self.calls), calls)
    self.installer.remove()
    self.assertTrue(self.installer.apply(ENTITY))
    self.assertEqual(self.pine.peek32(self.addr["heap bottom"]), bottom)
    self.assertEqual(len(self.eye_entries()), 4)
    self.assertEqual(len(self.called(OBJECT)), 1)
    self.assertEqual(len(self.called(3)), 2)

  def test_reset_rebuilds_the_map_but_keeps_the_bank(self) -> None:
    self.build_character(SLY, sorted(WALKS[SLY].channels)[:1])
    self.assertTrue(self.installer.apply(ENTITY))
    self.installer.reset()
    self.assertIsNone(self.installer.active)
    self.assertEqual(
      self.pine.peek32(self.addr["hypnosis state"] + STATE_BANK), BANK_HANDLE
    )
    self.pine.poke32(ENTITY + 0xB8, 2)
    self.pine.poke32(ENTITY + 0xC0, PARTS)
    self.interface.clear_cache()
    self.assertTrue(self.installer.apply(ENTITY))
    self.assertEqual(len(self.called(OBJECT)), 2)
    self.assertEqual(len(self.called(BANK_HANDLE)), 1)

  def test_busy_bank_load_retries_with_the_same_buffer(self) -> None:
    self.build_character(SLY, sorted(WALKS[SLY].channels)[:1])
    attempts = []

    def busy_then_loaded(args: list[int]) -> int:
      attempts.append(args[0])
      return BANK_BUSY if len(attempts) == 1 else BANK_HANDLE

    self.pine.cave_functions[CAVE_HYPNOSIS_BANK_LOAD] = busy_then_loaded
    bank = self.addr["hypnosis state"] + STATE_BANK
    self.assertFalse(self.installer.apply(ENTITY))
    self.assertEqual(self.pine.peek32(bank), 0)
    self.assertTrue(self.installer.apply(ENTITY))
    self.assertEqual(attempts[0], attempts[1])
    self.assertEqual(self.pine.peek32(bank), BANK_HANDLE)

  def test_bank_left_by_an_earlier_client_is_reused(self) -> None:
    self.build_character(SLY, sorted(WALKS[SLY].channels)[:1])
    self.pine.poke32(self.addr["hypnosis state"] + STATE_BANK, BANK_HANDLE)
    self.assertTrue(self.installer.apply(ENTITY))
    self.assertEqual(self.called(BANK_HANDLE), [])
    play = self.addr["hypnosis state"] + STATE_PARAMS
    self.assertEqual(self.pine.peek32(play), BANK_HANDLE)

  def test_each_trap_loads_and_unloads_the_bank(self) -> None:
    self.build_character(SLY, sorted(WALKS[SLY].channels)[:1])
    for _ in range(2):
      self.assertTrue(self.installer.apply(ENTITY))
      self.installer.remove()
    self.assertEqual(len(self.called(BANK_HANDLE)), 2)
    self.assertEqual(len(self.called(UNLOADED)), 2)

  def test_refused_bank_means_no_sound(self) -> None:
    self.build_character(SLY, sorted(WALKS[SLY].channels)[:1])
    self.pine.cave_functions[CAVE_HYPNOSIS_BANK_LOAD] = self.serve(0xFFFFFFFF)
    with self.assertLogs("Sly2Test", "WARNING"):
      self.assertTrue(self.installer.apply(ENTITY))
    self.installer.remove()
    self.assertTrue(self.installer.apply(ENTITY))
    self.assertEqual(len(self.called(0xFFFFFFFF)), 1)
    self.assertEqual(self.called(SOUND_PLAY), [])
    self.assertEqual(self.called(UNLOADED), [])

  def test_bentley_offsets_flags_and_constants(self) -> None:
    walk = WALKS[BENTLEY]
    self.build_character(BENTLEY, [BENTLEY_EYE_SCALE, walk.rotations[0]])
    self.assertTrue(self.installer.apply(ENTITY))
    pine = self.pine
    for source in self.sources(0):
      kind, *scale = struct.unpack("<Ifff", pine.peek_bytes(source, 16))
      self.assertEqual(kind, CONSTANT_CONTROLLER)
      for value, expected in zip(scale, (1.1, 0.35, 1.1)):
        self.assertAlmostEqual(value, expected, places=6)
    for element, offset in walk.offsets.items():
      self.assertEqual(
        struct.unpack(
          "<3f", pine.peek_bytes(JOINTS + 0x100*element + 0x30, 12)
        ),
        offset
      )
    for part, entry in zip(EYES, self.eye_entries()[2:]):
      self.assertEqual(entry[1], JOINTS + 0x100 * walk.eye_joints[part.joint])
      assert walk.eye_flags is not None
      self.assertEqual(entry[3], walk.eye_flags | (part.flags & 0xFF))
      self.assertEqual(entry[8], 0)
    self.assertEqual(pine.peek32(CHILDREN + 0xD4), 0)
    self.installer.remove()
    for element in walk.offsets:
      self.assertEqual(
        pine.peek_bytes(JOINTS + 0x100*element + 0x30, 12), bytes(12)
      )

  def test_existing_eye_parts_are_reused(self) -> None:
    self.build_character(SLY, sorted(WALKS[SLY].channels)[:1])
    self.pine.poke32(PARTS, EYES[0].part_id)
    self.pine.poke32(PARTS + PART_SIZE, EYES[1].part_id)
    self.pine.poke32(PARTS + 0xC, 0x0282_4820 | HIDDEN_FLAG)
    self.interface.clear_cache()
    self.assertTrue(self.installer.apply(ENTITY))
    entries = self.eye_entries()
    self.assertEqual(len(entries), 2)
    self.assertEqual(entries[0][3] & HIDDEN_FLAG, 0)

  def test_clean_undoes_a_stranded_trap(self) -> None:
    self.build_character(SLY, sorted(WALKS[SLY].channels)[:1])
    self.assertTrue(self.installer.apply(ENTITY))
    self.interface.hypnosis_installer = type(self.installer)(
      self.interface, self.interface.logger
    )
    self.interface.clear_cache()
    self.interface.reset_hypnosis()
    state = self.addr["hypnosis state"]
    self.assertEqual(self.called(1)[-1], [VOICE, 0, 0, 0])
    self.assertEqual(self.called(UNLOADED), [[BANK_HANDLE, 0, 0, 0]])
    self.assertEqual(self.pine.peek32(state + STATE_VOICE), 0)
    self.assertEqual(self.pine.peek32(state + STATE_BANK), 0)
    self.assertEqual(self.pine.peek32(ENTITY + 0xD4) & DRAW_IN_FRONT, 0)
    self.assertEqual(self.pine.peek32(CHILDREN + 0xD4) & DRAW_IN_FRONT, 0)
    for entry in self.eye_entries()[2:]:
      self.assertEqual(entry[3] & HIDDEN_FLAG, HIDDEN_FLAG)
    self.pine.clear_writes()
    self.interface.clear_cache()
    self.interface.reset_hypnosis()
    self.assertEqual(self.pine.writes, [])

  def test_apply_switches_characters(self) -> None:
    self.build_character(SLY, sorted(WALKS[SLY].channels)[:1])
    self.assertTrue(self.installer.apply(ENTITY))
    other = ENTITY + 0x10000
    self.pine.poke32(other + 0xC, 0x1234)
    self.interface.clear_cache()
    self.assertFalse(self.installer.apply(other))
    self.assertIsNone(self.installer.active)
    self.assertEqual(self.sources(0), (SOURCES, SOURCES + 0x10))
