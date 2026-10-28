"""ThiefNet five-digit costs (ep1 ThiefNet). The cost cells only fit four
digits, so the cave lays out each visible cell for the cost it shows: wider,
squeezed and moved left for a cost over 9999, vanilla otherwise. These assert
the cells' draw items and transforms over the live game (the ThiefNet is
already open, showing items 0, 8 and 16); the look is confirmed by eye."""

import struct
import time
from typing import Callable

from ..data.Constants import (
  MENU_ICON_CAVE,
  MENU_ICON_TABLE,
  THIEFNET_COST_LAYOUT_VANILLA,
  THIEFNET_COST_LAYOUT_WIDE,
)
from .harness import E2ETestBase

DRAW_ITEM = 0x3E30A0
LIVE = 0x3E7990
TEMPLATE = 0x3E8E60
RELOCATED_DRAW_ITEM = MENU_ICON_TABLE + 0x24 + DRAW_ITEM - 0x3E21A0
COSTS = {0: 80000, 8: 500, 16: 12345}


class TestThiefnetCosts(E2ETestBase):
  state = "ep1_thiefnet"
  episode = 1
  map_id = 2

  def setUp(self) -> None:
    super().setUp()
    self.interface.install_cave()
    self._wait(self.interface.cave_live)
    for item, cost in COSTS.items():
      self.interface.set_thiefnet_cost(item, cost)

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

  def _float(self, address: int) -> float:
    return struct.unpack("<f", self.pine.read_bytes(address, 4))[0]

  def _layout(self, cell: int) -> tuple[float, float, float]:
    return (
      self._float(DRAW_ITEM + cell*0x80 + 0x24),
      self._float(TEMPLATE + cell*0x80),
      self._float(TEMPLATE + cell*0x80 + 0x10)
    )

  def _assert_layout(
    self, cell: int, expected: tuple[float, float, float]
  ) -> None:
    for got, want in zip(self._layout(cell), expected):
      self.assertAlmostEqual(got, want, places=4)

  def _wide_applied(self) -> bool:
    return abs(self._layout(0)[0] - THIEFNET_COST_LAYOUT_WIDE[0]) < 1e-3

  def test_cells_follow_their_costs(self) -> None:
    self.interface.set_thiefnet_cost_layout(True)
    self.assertTrue(self._wait(self._wide_applied))
    self._assert_layout(0, THIEFNET_COST_LAYOUT_WIDE)
    self._assert_layout(1, THIEFNET_COST_LAYOUT_VANILLA)
    self._assert_layout(2, THIEFNET_COST_LAYOUT_WIDE)

  def test_live_transform_follows(self) -> None:
    self.interface.set_thiefnet_cost_layout(True)
    self.assertTrue(self._wait(
      lambda: abs(
        self._float(LIVE + 0x10) - THIEFNET_COST_LAYOUT_WIDE[2]
      ) < 1e-3
    ))
    self.assertAlmostEqual(
      self._float(LIVE + 0xE0 + 0x10), THIEFNET_COST_LAYOUT_VANILLA[2], 4
    )

  def test_unset_layout_leaves_cells_vanilla(self) -> None:
    self.interface.set_thiefnet_cost_layout(False)
    time.sleep(0.3)
    for cell in range(3):
      self._assert_layout(cell, THIEFNET_COST_LAYOUT_VANILLA)

  def test_relocated_glyph_table_widened(self) -> None:
    installer = self.interface.menu_icon_installer
    self.interface.install_menu_icons()
    self.assertTrue(self._wait(installer.built))
    self.interface.apply_thiefnet_theme(1)
    self.interface.set_thiefnet_row_chars(None)
    self.interface.arm_menu_icons()
    # Stand in for mi_blank, as in e2e_menu_icons: this state is already
    # open, so the wire waits for an animation the cave never saw.
    self.pine.write_int32(MENU_ICON_CAVE + 12, 1)
    self.assertTrue(self._wait(installer.installed))
    self.interface.set_thiefnet_cost_layout(True)
    self.assertTrue(self._wait(
      lambda: abs(
        self._float(RELOCATED_DRAW_ITEM + 0x24) -
        THIEFNET_COST_LAYOUT_WIDE[0]
      ) < 1e-3
    ))
    self.assertAlmostEqual(
      self._float(RELOCATED_DRAW_ITEM + 0x80 + 0x24),
      THIEFNET_COST_LAYOUT_VANILLA[0], 4
    )
