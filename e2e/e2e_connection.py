from typing import Any

from ..data.Constants import ADDRESSES
from ..pcsx2_interface.pine import Pine
from ..Sly2Interface import in_ee_ram
from .harness import GAME_ID, E2ETestBase


def flatten(value: Any) -> list[int]:
  if isinstance(value, bool):
    return []
  if isinstance(value, int):
    return [value]
  if isinstance(value, dict):
    return [a for v in value.values() for a in flatten(v)]
  if isinstance(value, (list, tuple)):
    return [a for v in value for a in flatten(v)]
  return []


class TestConnection(E2ETestBase):
  def test_game(self) -> None:
    self.assertEqual(self.pine.get_game_id(), GAME_ID)
    self.assertEqual(self.pine.get_emu_status(), Pine.EmuStatus.RUNNING)
    self.assertEqual(self.interface.current_game, GAME_ID)

  def test_addresses_in_ee_ram(self) -> None:
    table = {
      key: value for key, value in ADDRESSES[GAME_ID].items()
      if key not in ("jobs", "text")
    }
    outside = [
      hex(address) for address in flatten(table) if not in_ee_ram(address)
    ]
    self.assertEqual(outside, [])

  def test_price_tables_are_strided(self) -> None:
    for key in ("loot prices", "treasure prices"):
      addresses = list(self.addr[key].values())
      self.assertEqual(len(set(addresses)), len(addresses))
      self.assertEqual(addresses, sorted(addresses))
