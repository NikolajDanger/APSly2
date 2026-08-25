"""Foreign loot models installed into the ep1_hub savestate: the pool
grows, the geometry lands in the level heap, textures that the map lacks
go through the game's loader and get bound."""

import struct
import time

from ..data.LootModels import LOOT_MODELS
from ..LootInstall import GLOBALS, PART_SIZE, dma_tags
from .harness import E2ETestBase

GOLD_BAR, DIAMOND, BRONZE_MEDAL = 0x46E, 0x472, 0x466
NATIVE_PARTS = 26


class TestLootModels(E2ETestBase):
  state = "ep1_hub"
  episode = 1
  map_id = 2

  def setUp(self) -> None:
    super().setUp()
    self.interface.install_cave()
    time.sleep(0.2)
    self.interface.clear_cache()

  def tearDown(self) -> None:
    self.reload()

  def managers(self) -> list[int]:
    return self.interface.loot_installer.managers()

  def counts(self) -> list[int]:
    return self.pine.batch_read_int32([m + 0xB8 for m in self.managers()])

  def parts(self, index: int) -> list[tuple[int, ...]]:
    lists = self.pine.batch_read_int32([m + 0xC0 for m in self.managers()])
    return [
      struct.unpack(
        "<10I", self.pine.read_bytes(lst + index * PART_SIZE, PART_SIZE)
      )
      for lst in lists
    ]

  def tex0(self, dl: int, offset: int) -> tuple[int, int]:
    buffer = dma_tags(self.pine.read_bytes(dl, 16))[0][3]
    low, high = struct.unpack("<2I", self.pine.read_bytes(buffer + offset, 8))
    return low & 0x3FFF, (high >> 5) & 0x3FFF

  def wait_for_textures(self) -> None:
    for _ in range(60):
      self.interface.clear_cache()
      if not self.interface.poll_loot_textures():
        return
      time.sleep(0.05)
    self.fail("texture upload never completed")

  def test_install(self) -> None:
    rest = self.pine.batch_read_int32([self.addr[name] for name in GLOBALS])
    heap = self.pine.read_int32(self.addr["heap bottom"])
    self.assertEqual(self.counts(), [NATIVE_PARTS] * 4)

    installed = self.interface.install_loot_models(
      [GOLD_BAR, DIAMOND, BRONZE_MEDAL]
    )
    self.assertEqual(installed, [GOLD_BAR, DIAMOND, BRONZE_MEDAL])
    self.wait_for_textures()

    parts = sum(len(LOOT_MODELS[i].parts) for i in installed)
    self.assertEqual(self.counts(), [NATIVE_PARTS + parts] * 4)
    self.assertGreater(self.pine.read_int32(self.addr["heap bottom"]), heap)
    self.assertEqual(
      self.pine.batch_read_int32([self.addr[name] for name in GLOBALS]), rest
    )

    gold_bar = self.parts(NATIVE_PARTS)
    self.assertEqual({p[0] for p in gold_bar}, {0x321B})
    self.assertEqual({p[4] for p in gold_bar}, {gold_bar[0][4]})
    matrices = [p[1] for p in self.parts(0)]
    self.assertEqual([p[1] for p in gold_bar], matrices)
    first, second = (
      self.tex0(gold_bar[0][4], offset) for offset in (0xA4, 0x138)
    )
    self.assertEqual(first[0], second[0])
    self.assertNotEqual(first[1], second[1])

    # The diamond's texture is native to ep1 and gets bound to it.
    diamond = self.parts(NATIVE_PARTS + 2)[0]
    self.assertEqual(diamond[0], 0x320C)
    self.assertEqual(self.tex0(diamond[4], 0xA4), (0x1D75, 0x1D2F))

    self.assertEqual(self.interface.install_loot_models(installed), [])
    self.assertEqual(self.counts(), [NATIVE_PARTS + parts] * 4)
