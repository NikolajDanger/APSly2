"""Episode 8 with the jump pack on Sly's back (ep8_pack savestate): the pack
entities are unregistered and unlinked, a pedestal closed to Sly is reopened,
and the client's ep-8 tick keeps both applied."""

from NetUtils import NetworkItem

from ..data.Constants import (
  ENTITY_MANAGER_FREE, ENTITY_SLOT, PEDESTAL_USERS, PEDESTAL_VTABLE,
  SLY_BACK_NODE, SLY_USER_BIT
)
from ..data.Items import item_dict
from ..pcsx2_interface.pine import Pine
from ..Sly2Interface import Sly2Interface, in_ee_ram
from .harness import E2ETestBase
from .tick_base import TickTestBase

PACK_CLASS = 0x43D7
PACK_GROUP_CLASS = 0x43D8
PACK_ENTITY_COUNT = 5
ENTITY_CLASS = 0x18


class PackReads:
  pine: Pine
  interface: Sly2Interface

  def back_node(self) -> int:
    sly = self.pine.read_int32(self.interface.addresses["sly pointer"])
    return self.pine.read_int32(sly + SLY_BACK_NODE)

  def pack_entities(self) -> list[int]:
    self.interface.clear_cache()
    return list(self.interface._walk_entity_descendants(self.back_node()))

  def pedestals(self) -> list[int]:
    self.interface.clear_cache()
    return [
      e for e in self.interface._walk_interactables()
      if self.pine.read_int32(e + 0xC) == PEDESTAL_VTABLE
    ]


class TestEp8Pack(PackReads, E2ETestBase):
  state = "ep8_pack"
  episode = 8
  map_id = 38

  def tearDown(self) -> None:
    self.reload()

  def test_pack_present(self) -> None:
    entities = self.pack_entities()
    classes = [self.pine.read_int32(e + ENTITY_CLASS) for e in entities]
    self.assertEqual(len(entities), PACK_ENTITY_COUNT)
    self.assertEqual(classes[:2], [PACK_CLASS, PACK_GROUP_CLASS])
    for entity in entities:
      slot = self.pine.read_int32(entity + ENTITY_SLOT)
      self.assertTrue(in_ee_ram(slot, 8))
      self.assertEqual(self.pine.read_int32(slot + 4), entity)

  def test_hide_mega_jump_pack(self) -> None:
    entities = self.pack_entities()
    slots = [self.pine.read_int32(e + ENTITY_SLOT) for e in entities]
    free = self.interface.addresses["entity manager"] + ENTITY_MANAGER_FREE
    free_before = self.pine.read_int32(free)
    self.interface.hide_mega_jump_pack()
    self.assertEqual(self.pack_entities(), [])
    for slot in slots:
      self.assertEqual(self.pine.batch_read_int32([slot, slot + 4]), [0, 0])
    self.assertEqual(
      self.pine.read_int32(free), free_before + PACK_ENTITY_COUNT
    )
    self.interface.hide_mega_jump_pack()
    self.assertEqual(
      self.pine.read_int32(free), free_before + PACK_ENTITY_COUNT
    )

  def test_allow_sly_treasure_pickup(self) -> None:
    pedestals = self.pedestals()
    self.assertEqual(len(pedestals), 1)
    users = pedestals[0] + PEDESTAL_USERS
    self.pine.write_int32(users, 6)
    self.interface.clear_cache()
    self.interface.allow_sly_treasure_pickup()
    self.assertEqual(self.pine.read_int32(users), 6 | SLY_USER_BIT)


class TestEp8PackTick(PackReads, TickTestBase):
  state = "ep8_pack"
  episode = 8
  map_id = 38
  options = {"episode_8_keys": 4}

  async def test_ticks(self) -> None:
    self.ctx.items_received.append(
      NetworkItem(item_dict["Progressive Anatomy for Disaster"].code, -1, 1)
    )
    pedestal = self.pedestals()[0] + PEDESTAL_USERS
    self.pine.write_int32(pedestal, 6)
    await self.run_ticks()
    self.assertEqual(self.pack_entities(), [])
    self.assertEqual(self.pine.read_int32(pedestal), 6 | SLY_USER_BIT)
    self.assertEqual(self.interface.refused_patches, set())
