import struct

from ..data.Constants import CAVE_HOOK_ENTRY
from ..data.LootModels import LOOT_MODELS, decode
from ..LootInstall import (
  BOUNDS_SIZE,
  GLOBALS,
  OUTLINE_FLAGS,
  PART_SIZE,
  POOL_CAPACITY,
  RECORD_SIZE,
  TYPE_ROW_SIZE,
  dma_tags,
  projection_block,
  rebase_destinations,
)
from .client_base import InterfaceTestBase

TEMPLATE = 0x900000
MANAGERS = [TEMPLATE + i * 0x1000 for i in range(4)]
LISTS = [m + 0x400 for m in MANAGERS]
RECORDS = 0x905000
BOUNDS = 0x905400
TYPE_TABLE = 0x906000
NATIVE_DL = 0x910000
NATIVE_BUFFER = 0x911000
MATERIAL_BASE = 0x1F94AA0
HEAP_BOTTOM = 0x1E00000
NATIVE_FLAGS = 0x4020020
NATIVE_PART = 0x3270
GOLD_BAR, DIAMOND, BRONZE_COMB = 0x46E, 0x472, 0x45A
PROJECTION = struct.pack("<4I", 0x4B007A9F, 0x44AA0002, 0x453B8000, 0x4B009A9F)
REST_GLOBALS = [0, 0, 0, 0, 0, 0, 0xD5, 0x1A0]
DIAMOND_TBP, DIAMOND_CBPS = 0x1D75, (0x1D2F, 0x1D2E)


def entry(part_id: int, matrix: int, flags: int, dl: int, off: int) -> bytes:
  return struct.pack("<10I", part_id, matrix, 0, flags, dl, off, 0, 0, 0, 0)


class LootInstallTestBase(InterfaceTestBase):
  def setUp(self) -> None:
    super().setUp()
    pine = self.pine
    pine.poke32(self.addr["loot pool"], MANAGERS[0])
    pine.poke32(self.addr["loot pool last"], MANAGERS[-1])
    pine.poke_bytes(NATIVE_DL, struct.pack(
      "<IIII", (3 << 28) | 0x20, NATIVE_BUFFER, 0, 0
    ) + struct.pack("<IIII", 6 << 28, 0, 0, 0))
    pine.poke_bytes(NATIVE_BUFFER + 0x90, PROJECTION)
    for i, (manager, lst) in enumerate(zip(MANAGERS, LISTS)):
      matrix = 0x920000 + i * 0x100
      if i + 1 < len(MANAGERS):
        pine.poke32(manager + 0x1C, MANAGERS[i + 1])
      pine.poke32(manager + 0xB8, 2)
      pine.poke32(manager + 0xBC, RECORDS)
      pine.poke32(manager + 0xC0, lst)
      pine.poke32(manager + 0xC4, BOUNDS)
      pine.poke_bytes(lst, entry(
        NATIVE_PART, matrix, NATIVE_FLAGS, NATIVE_DL,
        (NATIVE_DL - MATERIAL_BASE) & 0xFFFFFFFF
      ) + entry(NATIVE_PART, matrix, OUTLINE_FLAGS, NATIVE_DL + 0x100, 0))
    pine.poke_bytes(BOUNDS, b"\x11" * BOUNDS_SIZE + b"\x22" * BOUNDS_SIZE)
    pine.poke32(MANAGERS[0] + 0x23C, 3)
    pine.poke32(MANAGERS[0] + 0x240, TYPE_TABLE)
    for i, (loot_id, part_id) in enumerate(
      [(BRONZE_COMB, NATIVE_PART), (GOLD_BAR, 0x321B), (DIAMOND, 0x320C)]
    ):
      pine.poke32(TYPE_TABLE + i * TYPE_ROW_SIZE, loot_id)
      pine.poke32(TYPE_TABLE + i * TYPE_ROW_SIZE + 0x20, part_id)
    pine.poke32(self.addr["heap bottom"], HEAP_BOTTOM)
    for name, value in zip(GLOBALS, REST_GLOBALS):
      pine.poke32(self.addr[name], value)
    # The diamond's texture family is resident; the gold bar's is not.
    records = self.addr["texture records"][0] + 0x1000
    pine.poke_bytes(records, struct.pack(
      "<10I", 0x3502, 0x2A01, 0x100010, 0x10214, 0x80, 0x1F00000, 8, 0,
      0x11400000 | DIAMOND_TBP, 5
    ))
    for k, (clut_id, cbp) in enumerate(
      zip((0x3DF1, 0x3DF0), DIAMOND_CBPS)
    ):
      pine.poke_bytes(records + 0x40 + k * 0x20, struct.pack(
        "<8I", clut_id, 0x2A01, 0x10010, 0x1F00100, 4, 0, 0x1400000,
        (1 << 29) | (cbp << 5)
      ))
    pine.poke32(self.addr["cave hook"], CAVE_HOOK_ENTRY)
    self.interface.clear_cache()

  def counts(self) -> list[int]:
    return [self.pine.peek32(m + 0xB8) for m in MANAGERS]

  def lists(self) -> list[int]:
    return [self.pine.peek32(m + 0xC0) for m in MANAGERS]

  def entries(self, manager: int) -> list[tuple[int, ...]]:
    lst = self.pine.peek32(manager + 0xC0)
    return [
      struct.unpack(
        "<10I", self.pine.peek_bytes(lst + i * PART_SIZE, PART_SIZE)
      )
      for i in range(self.pine.peek32(manager + 0xB8))
    ]

  def first_buffer(self, dl: int) -> int:
    return dma_tags(self.pine.peek_bytes(dl, 16))[0][3]

  def tex0(self, dl: int, offset: int) -> tuple[int, int]:
    low, high = struct.unpack(
      "<2I", self.pine.peek_bytes(self.first_buffer(dl) + offset, 8)
    )
    return low & 0x3FFF, (high >> 5) & 0x3FFF

  def globals_(self) -> list[int]:
    return [self.pine.peek32(self.addr[name]) for name in GLOBALS]


class TestLootInstall(LootInstallTestBase):
  def test_installs_foreign_loot_only(self) -> None:
    installed = self.interface.install_loot_models(
      [BRONZE_COMB, GOLD_BAR, DIAMOND]
    )
    self.assertEqual(installed, [GOLD_BAR, DIAMOND])
    self.assertEqual(self.counts(), [6] * 4)
    for manager, old in zip(MANAGERS, LISTS):
      parts = self.entries(manager)
      self.assertNotEqual(self.pine.peek32(manager + 0xC0), old)
      self.assertEqual(parts[:2], [
        struct.unpack(
          "<10I", self.pine.peek_bytes(old + i * PART_SIZE, PART_SIZE)
        )
        for i in range(2)
      ])
      self.assertEqual(
        [p[0] for p in parts[2:]], [0x321B, 0x321B, 0x320C, 0x320C]
      )
      self.assertTrue(all(p[1] == parts[0][1] for p in parts))
    self.assertEqual(len(set(self.lists())), 4)
    self.assertGreater(self.pine.peek32(self.addr["heap bottom"]), HEAP_BOTTOM)

  def test_flags_records_and_bounds(self) -> None:
    self.interface.install_loot_models([GOLD_BAR])
    template = self.entries(MANAGERS[0])
    textured, outline = template[2], template[3]
    self.assertEqual(textured[3], NATIVE_FLAGS)
    self.assertEqual(outline[3], OUTLINE_FLAGS)
    self.assertEqual(
      textured[5], (textured[4] - MATERIAL_BASE) & 0xFFFFFFFF
    )
    self.assertEqual(outline[5], 0)
    records = self.pine.peek32(MANAGERS[0] + 0xBC)
    bounds = self.pine.peek32(MANAGERS[0] + 0xC4)
    record = struct.unpack(
      "<5I", self.pine.peek_bytes(records + 2 * RECORD_SIZE, RECORD_SIZE)
    )
    model = LOOT_MODELS[GOLD_BAR]
    self.assertEqual(record[2], textured[4] + model.parts[0].main)
    self.assertEqual(record[4], model.parts[0].record[4])
    self.assertEqual(
      self.pine.peek_bytes(bounds + 2 * BOUNDS_SIZE, BOUNDS_SIZE),
      b"\x11" * BOUNDS_SIZE
    )
    self.assertEqual(
      self.pine.peek_bytes(bounds + 3 * BOUNDS_SIZE, BOUNDS_SIZE),
      b"\x22" * BOUNDS_SIZE
    )

  def test_geometry_is_rebased(self) -> None:
    self.interface.install_loot_models([GOLD_BAR])
    dl = self.entries(MANAGERS[0])[2][4]
    buffer = self.first_buffer(dl)
    model = LOOT_MODELS[GOLD_BAR]
    data = decode(model.data)
    source = data[model.parts[0].main:][:model.parts[0].refs[0]]
    installed = self.pine.peek_bytes(buffer, len(source))
    self.assertEqual(projection_block(installed), (0x7A9F, PROJECTION))
    self.assertNotEqual(installed, source)
    self.assertEqual(len(installed), len(source))
    tags = dma_tags(self.pine.peek_bytes(dl, model.parts[0].main))
    self.assertEqual(
      [t[3] for t in tags if t[1] in (3, 4)][0], buffer
    )

  def test_rebase_destinations_span_the_main_chain(self) -> None:
    chain = struct.pack("<4I", 0x1000, 0x13FC, 0x1400, 0x2000)
    self.assertEqual(
      struct.unpack("<4I", rebase_destinations(chain, 0x1000, 0x5000, 0x400)),
      (0x5000, 0x53FC, 0x1400, 0x2000)
    )
    self.assertEqual(
      struct.unpack("<4I", rebase_destinations(chain, 0x1000, 0x5000, 0x800)),
      (0x5000, 0x53FC, 0x5400, 0x2000)
    )

  def test_resident_texture_bound_immediately(self) -> None:
    self.interface.install_loot_models([DIAMOND])
    dl = self.entries(MANAGERS[0])[2][4]
    self.assertEqual(self.tex0(dl, 0xA4), (DIAMOND_TBP, DIAMOND_CBPS[0]))
    self.assertEqual(self.tex0(dl, 0x138), (DIAMOND_TBP, DIAMOND_CBPS[1]))
    self.assertFalse(self.interface.poll_loot_textures())
    self.assertEqual(self.pine.peek32(self.addr["cave call"]), 0)

  def test_missing_texture_goes_through_the_loader(self) -> None:
    self.interface.install_loot_models([GOLD_BAR])
    slot = self.addr["cave call"]
    self.assertEqual(self.pine.peek32(slot), self.addr["texture loader"])
    allocator = self.pine.peek32(slot + 4)
    self.assertEqual(
      struct.unpack("<3I", self.pine.peek_bytes(allocator, 12))[::2],
      (0x1800, 0x4000)
    )
    counts, table, clut_counts, clut_table, *_ = self.globals_()
    self.assertEqual((counts, clut_counts), (1, 2))
    self.assertEqual(self.pine.peek32(table), 1)
    self.assertEqual(self.pine.peek32(clut_table), 2)
    self.assertTrue(self.interface.poll_loot_textures())
    self.assertEqual(self.interface.install_loot_models([DIAMOND]), [])

    # The cave runs the loader: it places the records and bumps the count.
    self.pine.poke32(table + 0x20, 0x55408000 | 0x3F12)
    self.pine.poke32(clut_table + 0x1C, (1 << 29) | (0x3F10 << 5))
    self.pine.poke32(clut_table + 0x20 + 0x1C, (1 << 29) | (0x3F11 << 5))
    self.pine.poke32(slot, 0)
    self.pine.poke32(slot + 0x18, 1)
    self.interface.clear_cache()
    self.assertFalse(self.interface.poll_loot_textures())
    dl = self.entries(MANAGERS[0])[2][4]
    self.assertEqual(self.tex0(dl, 0xA4), (0x3F12, 0x3F10))
    self.assertEqual(self.tex0(dl, 0x138), (0x3F12, 0x3F11))
    self.assertEqual(self.globals_(), REST_GLOBALS)

  def test_second_install_is_a_no_op(self) -> None:
    self.interface.install_loot_models([DIAMOND])
    lists = self.lists()
    self.pine.clear_writes()
    self.assertEqual(self.interface.install_loot_models([DIAMOND]), [])
    self.assertEqual(self.counts(), [4] * 4)
    self.assertEqual(self.lists(), lists)
    self.assertFalse(self.pine.writes)

  def test_pool_capacity(self) -> None:
    self.pine.poke32(MANAGERS[0] + 0xB8, POOL_CAPACITY - 1)
    self.interface.clear_cache()
    self.assertEqual(self.interface.install_loot_models([GOLD_BAR]), [])

  def test_needs_the_cave(self) -> None:
    self.pine.poke32(self.addr["cave hook"], 0)
    self.interface.clear_cache()
    self.assertEqual(self.interface.install_loot_models([GOLD_BAR]), [])
    self.assertEqual(self.counts(), [2] * 4)
