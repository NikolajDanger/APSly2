"""Reversible writes against the ep1_hub savestate. Every test that leaves
the game changed reloads the state in tearDown, which also drops the cave."""

import time

from ..data.Constants import CAVE_BLOB, CAVE_HOOK_ENTRY, POWERUP_TEXT
from ..Sly2Interface import INFOBOX_CLIENT_STRING, Sly2Episode
from .harness import POLL_INTERVAL, E2ETestBase


class TestWrites(E2ETestBase):
  state = "ep1_hub"
  episode = 1
  map_id = 2

  def setUp(self) -> None:
    super().setUp()
    self.mutated = True

  def tearDown(self) -> None:
    if self.mutated:
      self.reload()

  def raw32(self, address: int) -> int:
    return self.pine.read_int32(address)

  def wait_until(self, condition: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
      self.interface.clear_cache()
      if getattr(self, condition)():
        return
      time.sleep(POLL_INTERVAL)
    self.fail(f"{condition} not reached within {timeout}s")

  def test_bottles(self) -> None:
    self.interface.set_bottles(7)
    self.assertEqual(self.raw32(self.addr["bottle count"]), 7)
    self.interface.clear_cache()
    self.assertEqual(self.raw32(self.addr["bottle count"]), 7)

  def test_thiefnet_cost(self) -> None:
    self.interface.set_thiefnet_cost(0, 1234)
    self.assertEqual(self.raw32(self.addr["thiefnet costs"][0]), 1234)

  def test_thiefnet_text(self) -> None:
    name, description = list(POWERUP_TEXT.items())[0]
    name_address, description_address = self.addr["text"]["powerups"][0][name]
    self.interface.set_thiefnet(0, ("AP Test", "An e2e description"))
    self.assertEqual(self.pine.read_string(name_address, 32), "AP Test")
    self.assertEqual(
      self.pine.read_string(description_address, 64), "An e2e description"
    )
    self.interface.reset_thiefnet()
    self.assertEqual(self.pine.read_string(name_address, 32), name)
    self.assertEqual(
      self.pine.read_string(description_address, 256), description
    )

  def infobox_closed(self) -> bool:
    return (
      self.interface.current_infobox() != INFOBOX_CLIENT_STRING and
      not self.interface.is_infobox()
    )

  def test_infobox(self) -> None:
    self.assertFalse(self.interface.is_infobox())
    self.assertTrue(self.interface.set_infobox("e2e hello"))
    self.interface.clear_cache()
    self.assertEqual(self.interface.current_infobox(), INFOBOX_CLIENT_STRING)
    self.assertTrue(self.interface.is_infobox())
    time.sleep(1.0)
    self.interface.clear_cache()
    self.interface.disable_infobox()
    self.wait_until("infobox_closed", 5.0)

  def payout_done(self) -> bool:
    return not self.interface.coins_paying_out()

  def test_cave_and_coins(self) -> None:
    before = self.interface.get_coins()
    self.interface.install_cave()
    self.interface.clear_cache()
    self.assertEqual(self.interface.refused_patches, set())
    self.assertTrue(self.interface.cave_live())
    hook = self.addr["cave hook"]
    self.assertEqual(self.raw32(hook), CAVE_HOOK_ENTRY)
    blob = bytes.fromhex(CAVE_BLOB)
    self.assertEqual(self.pine.read_bytes(self.addr["cave"], len(blob)), blob)
    self.assertTrue(self.interface.queue_coins(50, 5))
    self.wait_until("payout_done", 10.0)
    self.assertEqual(self.interface.get_coins(), before + 50)
    self.assertEqual(self.interface.get_bottles(Sly2Episode(1)), 0)
