"""ThiefNet row text color (ep1 ThiefNet). The client redirects the scroll
handler through a cave function that recolors the six on-screen row slots from a
client-written per-item table, repainting them as the list scrolls. These assert
the memory reshaping over the live game (the ThiefNet is already open, showing
three rows here); the colors are confirmed by eye."""

import time
from typing import Callable

from ..data.Constants import (
  CAVE_THIEFNET_COLORS,
  THIEFNET_NAME_COLOR,
  THIEFNET_COLORS_ORIG,
  THIEFNET_COLORS_SITE,
  THIEFNET_TEXT_COLORS,
  THIEFNET_TEXT_VANILLA,
)
from .harness import E2ETestBase

CLASSES = ["progression", "useful", "trap", "filler"] * 6


class TestThiefnetText(E2ETestBase):
  state = "ep1_thiefnet"
  episode = 1
  map_id = 2

  def setUp(self) -> None:
    super().setUp()
    self.interface.install_cave()
    self._wait(self.interface.cave_live)
    self.interface.install_menu_icons()
    self._wait(self.interface.menu_icon_installer.installed)
    self.colors = [THIEFNET_TEXT_COLORS[cls] for cls in CLASSES]

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

  def test_redirect_through_cave(self) -> None:
    self.interface.set_thiefnet_colors(self.colors)
    redirect = 0x0C000000 | (CAVE_THIEFNET_COLORS >> 2)
    self.assertTrue(self._wait(
      lambda: self.pine.read_int32(THIEFNET_COLORS_SITE) == redirect
    ))

  def test_color_table_written(self) -> None:
    self.interface.set_thiefnet_colors(self.colors)
    self.interface.clear_cache()
    table = self.addr["thiefnet color table"]
    for i, color in enumerate(self.colors):
      self.assertEqual(self.pine.read_int32(table + 4*i), color)

  def test_visible_rows_colored(self) -> None:
    self.interface.set_thiefnet_colors(self.colors)
    self.interface.clear_cache()
    slots = THIEFNET_NAME_COLOR
    for i in range(6):
      self.assertEqual(
        self.pine.read_int32(slots + i*0x80), self.colors[i]
      )

  def test_clear_restores(self) -> None:
    self.interface.set_thiefnet_colors(self.colors)
    self._wait(
      lambda: self.pine.read_int32(THIEFNET_COLORS_SITE)
      == (0x0C000000 | (CAVE_THIEFNET_COLORS >> 2))
    )
    self.interface.clear_thiefnet_colors()
    self.assertTrue(self._wait(
      lambda: self.pine.read_int32(THIEFNET_COLORS_SITE) == THIEFNET_COLORS_ORIG
    ))
    self.interface.clear_cache()
    slots = THIEFNET_NAME_COLOR
    for i in range(6):
      self.assertEqual(
        self.pine.read_int32(slots + i*0x80), THIEFNET_TEXT_VANILLA
      )
