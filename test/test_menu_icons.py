import struct
import unittest

from ..data.Constants import (
  CAVE_HOOK_ORIG,
  GLYPH_SET,
  MENU_ICON_CHARS,
  MENU_ICON_CHOOSER,
  MENU_ICON_ELEMS,
  MENU_ICON_FIFTH_ELEMS,
  MENU_ICON_FOURTH_ELEMS,
  MENU_ICON_GLYPHS,
  MENU_ICON_GROUP,
  MENU_ICON_GROUPS,
  MENU_ICON_PACKETS,
  MENU_ICON_TABLE,
  MENU_ICON_VANILLA_PACKETS,
)
from ..data.MenuIcons import THEMES, decode
from ..MenuIcons import MenuIconInstaller
from .client_base import InterfaceTestBase

VANILLA_BASE = 0x3E21A0            # [GLYPH_SET+0x54] before relocation
VANILLA_GROUPS = 0x3E5D60          # [GLYPH_SET+0x84] before relocation
PROTO_ELEMS = 0x500000
PROTO_NODE = 0x510000
PROTO_POOL = 0x520000
PROTO_BUFFER = 0x530000


class TestMenuIconData(unittest.TestCase):
  def test_every_theme_and_class_present(self) -> None:
    for theme in (1, 2, 3):
      for cls in ("progression", "useful", "trap", "filler", "unknown"):
        self.assertIn(cls, THEMES[theme])

  def test_packets_decode_and_are_well_formed(self) -> None:
    for theme in (1, 2, 3):
      for cls, icon in THEMES[theme].items():
        for blob in (icon.fill, icon.sil):
          packet = decode(blob)
          # DMA tag then a 16-byte aligned body.
          self.assertEqual(struct.unpack_from("<I", packet, 0)[0] >> 24, 0x10)
          self.assertEqual(len(packet) % 16, 0)
          # Fits inside the 0x400 staging stride.
          self.assertLessEqual(len(packet), 0x400)


class MenuIconTestBase(InterfaceTestBase):
  def _installer(self) -> MenuIconInstaller:
    return self.interface.menu_icon_installer

  def _install_cave(self) -> None:
    self.pine.poke32(self.addr["cave hook"], CAVE_HOOK_ORIG)
    self.interface.install_cave()

  def _prime_glyphs(self) -> None:
    """Writing a small glyph set to memory for testing."""
    self.pine.poke32(GLYPH_SET + 0x50, 0x64)
    self.pine.poke32(GLYPH_SET + 0x54, VANILLA_BASE)
    self.pine.poke32(GLYPH_SET + 0x80, 30)
    self.pine.poke32(GLYPH_SET + 0x84, VANILLA_GROUPS)
    proto = VANILLA_GROUPS + 25 * 0x30
    self.pine.poke16(proto + 2, 6)                 # pool_n
    self.pine.poke32(proto + 4, PROTO_ELEMS)
    self.pine.poke32(proto + 8, PROTO_POOL)
    self.pine.poke32(PROTO_POOL + 0, 2)            # flag (2 sub-buffers)
    self.pine.poke32(PROTO_POOL + 4, PROTO_BUFFER)
    self.pine.poke32(PROTO_ELEMS + 4, PROTO_NODE)
    # the row-icon group (29) == MENU_ICON_GROUP, with a few elements
    self.pine.poke16(MENU_ICON_GROUP, 9)
    self.pine.poke32(MENU_ICON_GROUP + 4, PROTO_ELEMS)
    # Sly's node pointer for _copy_node
    self.pine.poke32(MENU_ICON_ELEMS + 0x18 + 4, PROTO_NODE)


class TestMenuIconStructure(MenuIconTestBase):
  def test_install_relocates_and_appends(self) -> None:
    self._prime_glyphs()
    self.assertFalse(self._installer().installed())
    self._installer().install_structure()
    self.assertTrue(self._installer().installed())
    self.assertEqual(
      self.pine.peek32(GLYPH_SET + 0x54), MENU_ICON_TABLE + 0x24
    )
    # two appended groups (filler + unknown)
    self.assertEqual(self.pine.peek32(GLYPH_SET + 0x80), 32)
    self.assertEqual(self.pine.peek32(GLYPH_SET + 0x84), MENU_ICON_GROUPS)
    # the appended element ids
    self.assertEqual(
      self.pine.peek32(MENU_ICON_FOURTH_ELEMS + 9 * 0x18 + 0x14), 0x45E
    )
    self.assertEqual(
      self.pine.peek32(MENU_ICON_FIFTH_ELEMS + 10 * 0x18 + 0x14), 0x45F
    )
    # the appended filler row glyph points at its fill staging packet
    fill = MENU_ICON_PACKETS["filler"][0]
    self.assertEqual(self.pine.peek32(MENU_ICON_TABLE + 0x66 * 0x40), fill)

  def test_install_is_idempotent(self) -> None:
    self._prime_glyphs()
    self._installer().install_structure()
    self.pine.clear_writes()
    self._installer().install_structure()
    self.assertEqual(self.pine.writes, [])


class TestMenuIconTheme(MenuIconTestBase):
  def _slot(self, glyph: int) -> int:
    return VANILLA_BASE - 0x24 + glyph * 0x40

  def test_apply_theme_writes_packets_and_repoints(self) -> None:
    self.pine.poke32(GLYPH_SET + 0x54, VANILLA_BASE)
    self.interface.apply_thiefnet_theme(2)
    for cls, (fill_glyph, sil_glyph) in MENU_ICON_GLYPHS.items():
      fill_address, sil_address = MENU_ICON_PACKETS[cls]
      self.assertEqual(self.pine.peek32(self._slot(fill_glyph)), fill_address)
      self.assertEqual(self.pine.peek32(self._slot(sil_glyph)), sil_address)
      self.assertEqual(
        self.pine.peek_bytes(fill_address, len(decode(THEMES[2][cls].fill))),
        decode(THEMES[2][cls].fill)
      )

  def test_theme_zero_restores_vanilla_packets(self) -> None:
    self.pine.poke32(GLYPH_SET + 0x54, VANILLA_BASE)
    self.interface.apply_thiefnet_theme(0)
    for glyph, packet in MENU_ICON_VANILLA_PACKETS.items():
      self.assertEqual(self.pine.peek32(self._slot(glyph)), packet)


class TestMenuIconChooser(MenuIconTestBase):
  def test_chooser_routes_through_cave(self) -> None:
    self._install_cave()
    for site, _, original in MENU_ICON_CHOOSER:
      self.pine.poke32(site, original)
    self.interface.clear_cache()
    self.pine.clear_writes()
    self._installer().install_chooser()
    slot = self.addr["cave patches"]
    sites = {
      self.pine.peek32(slot + 8 * i) for i in range(len(MENU_ICON_CHOOSER))
    }
    for site, _, original in MENU_ICON_CHOOSER:
      self.assertIn(site, sites)
      # PINE never writes the instruction directly; the cave does.
      self.assertEqual(self.pine.peek32(site), original)
      self.assertFalse(self.pine.written(site))

  def test_chooser_skipped_without_cave(self) -> None:
    self.pine.clear_writes()
    self._installer().install_chooser()
    self.assertEqual(self.pine.writes, [])


class TestMenuIconRowChars(MenuIconTestBase):
  def _char(self, i: int) -> int:
    return self.pine.peek32(self.addr["thiefnet costs"][i] - 4)

  def test_set_row_chars_by_class(self) -> None:
    classes = ["progression", "useful", "trap", "filler"] * 6
    self._installer().set_row_chars(classes)
    for i, cls in enumerate(classes):
      self.assertEqual(self._char(i), MENU_ICON_CHARS[cls])

  def test_theme_zero_restores_saved_vanilla_chars(self) -> None:
    for i in range(24):
      self.pine.poke32(self.addr["thiefnet costs"][i] - 4, 7 + (i % 3))
    self._installer().save_vanilla_chars()
    self._installer().set_row_chars(["filler"] * 24)
    self._installer().set_row_chars(None)
    for i in range(24):
      self.assertEqual(self._char(i), 7 + (i % 3))


if __name__ == "__main__":
  unittest.main()
