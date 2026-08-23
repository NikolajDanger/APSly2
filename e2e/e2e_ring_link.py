"""Ring link against the ep1_hub savestate: wallet changes go out as one
Bounce, received deltas are applied (clamped at 0) without being echoed,
and a Coins item is shared after its cave payout finishes."""

import asyncio
import time

from NetUtils import NetworkItem

from ..data.Items import item_dict
from ..Sly2Client import _handle_game_ready
from .tick_base import TickTestBase

OTHER_SOURCE = 0xBEEF


class TestRingLinkTick(TickTestBase):
  async def asyncSetUp(self) -> None:
    await super().asyncSetUp()
    self.ctx.ring_link_enabled = True

  async def tick(self) -> None:
    await asyncio.wait_for(_handle_game_ready(self.ctx), 15.0)
    self.interface.clear_cache()

  def bounces(self) -> list[dict]:
    return [
      m["data"] for m in self.ctx.sent_cmds("Bounce")
      if "RingLink" in m["tags"]
    ]

  def receive(self, amount: int) -> None:
    self.ctx.on_package("Bounced", {
      "tags": ["RingLink"],
      "data": {"time": 0, "source": OTHER_SOURCE, "amount": amount}
    })

  async def test_ticks(self) -> None:
    coins = self.interface.addresses["coins"]
    await self.run_ticks()
    self.assertEqual(self.ctx.prev_coins, 18)
    self.assertEqual(self.bounces(), [])

    self.pine.write_int32(coins, 18 + 25)
    await self.tick()
    self.assertEqual(
      [(b["amount"], b["source"]) for b in self.bounces()],
      [(25, self.ctx.ring_link_source)]
    )

    self.receive(-10)
    await self.tick()
    self.assertEqual(self.interface.get_coins(), 33)
    self.assertEqual(self.ctx.pending_ring_link, 0)
    await self.tick()
    self.assertEqual(len(self.bounces()), 1)

    self.receive(-1000)
    await self.tick()
    self.assertEqual(self.interface.get_coins(), 0)
    await self.tick()
    self.assertEqual(len(self.bounces()), 1)

    self.ctx.on_package("Bounced", {
      "tags": ["RingLink"],
      "data": {"time": 0, "source": self.ctx.ring_link_source, "amount": 50}
    })
    await self.tick()
    self.assertEqual(self.interface.get_coins(), 0)

    self.ctx.items_received.append(
      NetworkItem(item_dict["Coins"].code, -1, 1)
    )
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline and len(self.bounces()) < 2:
      await self.tick()
    slot_data = self.ctx.slot_data
    assert slot_data is not None
    self.assertEqual(len(self.bounces()), 2)
    shared = self.bounces()[1]["amount"]
    self.assertGreaterEqual(shared, slot_data["coins_minimum"])
    self.assertLessEqual(shared, slot_data["coins_maximum"])
    self.assertEqual(self.interface.get_coins(), shared)
