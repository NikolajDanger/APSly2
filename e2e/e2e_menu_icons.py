"""ThiefNet icon themes (ep1 ThiefNet). The client relocates the glyph table
and group array, appends two two-channel glyphs (filler + unknown), redirects
the row-icon chooser through the cave, and repoints the row glyphs at the
Archipelago-logo packets per theme. These assert the memory reshaping over the
live game (the ThiefNet is already open in this state, so the icons render
live); visuals are confirmed by eye."""

import time
from typing import Callable

from ..data.Constants import (
  GLYPH_SET,
  MENU_ICON_CHARS,
  MENU_ICON_CHOOSER,
  MENU_ICON_GLYPHS,
  MENU_ICON_GROUPS,
  MENU_ICON_PACKETS,
  MENU_ICON_ROW_GROUP,
  MENU_ICON_TABLE,
  MENU_ICON_VANILLA_PACKETS,
)
from ..data.MenuIcons import THEMES, decode
from .harness import E2ETestBase


class TestMenuIcons(E2ETestBase):
  state = "ep1_thiefnet"
  episode = 1
  map_id = 2

  def setUp(self) -> None:
    super().setUp()
    self.interface.install_cave()
    self._wait(self.interface.cave_live)
    self.interface.install_menu_icons()
    self._wait(self.interface.menu_icon_installer.installed)

  def tearDown(self) -> None:
    self.reload()

  def _wait(self, cond: Callable[[], bool], timeout: float = 6.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      self.interface.clear_cache()
      if cond():
        return True
      time.sleep(0.05)
    return False

  def _slot(self, glyph: int) -> int:
    base = self.pine.read_int32(GLYPH_SET + 0x54)
    return base - 0x24 + glyph * 0x40

  def test_structure_installed(self) -> None:
    self.interface.clear_cache()
    self.assertTrue(self.interface.menu_icon_installer.installed())
    self.assertEqual(
      self.pine.read_int32(GLYPH_SET + 0x54), MENU_ICON_TABLE + 0x24
    )
    self.assertEqual(self.pine.read_int32(GLYPH_SET + 0x84), MENU_ICON_GROUPS)

  def test_appended_elements_present(self) -> None:
    self.interface.clear_cache()
    # Both appended elements land in the live row-icon group's element array.
    group = MENU_ICON_GROUPS + MENU_ICON_ROW_GROUP * 0x30
    count = self.pine.read_int16(group)
    elements = self.pine.read_int32(group + 4)
    self.assertEqual(
      self.pine.read_int32(elements + (count - 2) * 0x18 + 0x14), 0x45E
    )
    self.assertEqual(
      self.pine.read_int32(elements + (count - 1) * 0x18 + 0x14), 0x45F
    )

  def test_chooser_redirected_through_cave(self) -> None:
    # The code patch is applied by the cave a frame after it is queued.
    site, patched, _ = MENU_ICON_CHOOSER[0]
    self.assertTrue(self._wait(
      lambda: self.pine.read_int32(site) == patched
    ))
    self.interface.clear_cache()
    for site, patched, _ in MENU_ICON_CHOOSER:
      self.assertEqual(self.pine.read_int32(site), patched)

  def test_themes_apply(self) -> None:
    for theme in (1, 2, 3):
      self.interface.apply_thiefnet_theme(theme)
      self.interface.clear_cache()
      for cls, (fill_glyph, _) in MENU_ICON_GLYPHS.items():
        fill_address = MENU_ICON_PACKETS[cls][0]
        self.assertEqual(self.pine.read_int32(self._slot(fill_glyph)),
          fill_address)
        expected = decode(THEMES[theme][cls].fill)
        self.assertEqual(
          self.pine.read_bytes(fill_address, len(expected)), expected
        )

  def test_theme_zero_restores_vanilla(self) -> None:
    self.interface.apply_thiefnet_theme(0)
    self.interface.clear_cache()
    for glyph, packet in MENU_ICON_VANILLA_PACKETS.items():
      self.assertEqual(self.pine.read_int32(self._slot(glyph)), packet)

  def test_row_chars_by_class(self) -> None:
    classes = ["progression", "useful", "trap", "filler", "unknown"] + \
      ["progression"] * 19
    self.interface.set_thiefnet_row_chars(classes)
    self.interface.clear_cache()
    costs = self.addr["thiefnet costs"]
    for i, cls in enumerate(classes):
      self.assertEqual(
        self.pine.read_int32(costs[i] - 4), MENU_ICON_CHARS[cls]
      )
