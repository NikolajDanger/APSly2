"""Received items against the ep1_hub savestate: gadgets land in the
bitfield, Mega Jump gets bound, bottles and the items-received counter are
written, coins pay out through the cave and a notification shows."""

import asyncio
import time

from NetUtils import NetworkItem

from ..data.Constants import MEGA_JUMP_GADGET_ID
from ..data.Items import item_dict
from ..Sly2Client import _handle_game_ready
from ..Sly2Interface import INFOBOX_CLIENT_STRING, PowerUps, Sly2Episode
from .harness import POLL_INTERVAL
from .tick_base import TickTestBase

ITEMS = [
  "Progressive The Black Chateau", "Paraglider", "Trigger Bomb", "Mega Jump",
  "Bottle - The Black Chateau", "Bottle - The Black Chateau", "Coins"
]
# trigger_bomb is bit 7 of byte 0; paraglide and mega_jump are bits 3 and 7
# of byte 3 (fields 20 and 24, offset by the 7 leading pad bits).
GADGET_BYTES = bytes.fromhex("800000880000")


class TestItemsTick(TickTestBase):
  options = {
    "bottle_location_bundle_size": 1, "bottle_item_bundle_size": 5
  }

  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.ctx.items_received.clear()
    self.ctx.items_received.extend(
      NetworkItem(item_dict[name].code, -1, 1) for name in ITEMS
    )

  async def tick(self) -> None:
    await asyncio.wait_for(_handle_game_ready(self.ctx), 15.0)
    self.interface.clear_cache()

  async def test_ticks(self) -> None:
    coins_before = self.interface.get_coins()
    await self.run_ticks()
    addresses = self.interface.addresses

    self.assertEqual(
      self.interface.read_powerups(),
      PowerUps(trigger_bomb=True, paraglide=True, mega_jump=True)
    )
    self.assertEqual(
      self.pine.read_bytes(addresses["gadgets"], 6), GADGET_BYTES
    )
    self.assertIn(MEGA_JUMP_GADGET_ID, self.interface.get_sly_bindings())
    self.assertEqual(self.interface.read_items_received(), len(ITEMS))
    self.assertEqual(self.interface.get_bottles(Sly2Episode(1)), 0)
    self.assertEqual(self.pine.read_int32(addresses["bottle count"]), 2)
    self.assertEqual(self.ctx.all_bottles[Sly2Episode(1)], 2)
    self.assertEqual(
      self.pine.read_string(
        self.pine.read_int32(
          self.pine.read_int32(addresses["string table"]) +
          addresses["text"]["right back"][0]
        ), 32
      ),
      "Bottles Collected: 0"
    )
    self.assertEqual(self.ctx.inventory[item_dict["Paraglider"].code], 1)

    slot_data = self.ctx.slot_data
    assert slot_data is not None
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
      await self.tick()
      if (
        self.ctx.pending_coins == 0 and
        not self.interface.coins_paying_out()
      ):
        break
      time.sleep(POLL_INTERVAL)
    gained = self.interface.get_coins() - coins_before
    self.assertGreaterEqual(gained, slot_data["coins_minimum"])
    self.assertLessEqual(gained, slot_data["coins_maximum"])

    self.assertTrue(
      self.ctx.notification_queue or self.ctx.showing_notification
    )
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
      if self.interface.current_infobox() == INFOBOX_CLIENT_STRING:
        break
      await self.tick()
    self.assertEqual(self.interface.current_infobox(), INFOBOX_CLIENT_STRING)
