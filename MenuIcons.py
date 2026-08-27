"""Module for installing the ThiefNet icon themes. The vanilla portrait icons
are vector drawings; this code repoints them at vector drawings of the
Archipelago logo, colored per item class. The filler and "unknown" classes
have no vanilla slot, so it appends two new glyphs for them. The actual vector
data is in data/MenuIcons.py; this module rewrites the memory."""

import struct
from logging import Logger
from typing import TYPE_CHECKING, Optional

from .data.Constants import (
  GLYPH_SET, GLYPH_TABLE_ALT, MENU_ICON_CHARS, MENU_ICON_CHOOSER,
  MENU_ICON_ELEMS, MENU_ICON_FIFTH_ARENA, MENU_ICON_FIFTH_ELEMS,
  MENU_ICON_FIFTH_NODE, MENU_ICON_FOURTH_ARENA, MENU_ICON_FOURTH_ELEMS,
  MENU_ICON_FOURTH_NODE, MENU_ICON_FREE_TAG, MENU_ICON_GLYPHS,
  MENU_ICON_GROUP, MENU_ICON_GROUPS, MENU_ICON_PACKETS, MENU_ICON_POOL,
  MENU_ICON_PROTO_GROUP, MENU_ICON_TABLE, MENU_ICON_VANILLA_PACKETS,
)
from .data.MenuIcons import THEMES, decode

if TYPE_CHECKING:
  from .Sly2Interface import Sly2Interface

FOURTH_GLYPH = 0x66      # appended filler row glyph (drawers 0x65/0x67/0x68)
FIFTH_GLYPH = 0x6A       # appended "unknown" row glyph (drawers 0x69/0x6b/0x6c)
FOURTH_ELEM = 0x45E      # filler element id (char 15 -> 15 + 0x44f)
FIFTH_ELEM = 0x45F       # unknown element id (char 16 -> 16 + 0x44f)
TABLE_ENTRIES = 0x65     # vanilla glyph-table entry count


class MenuIconInstaller:
  def __init__(self, interface: "Sly2Interface", logger: Logger) -> None:
    self.interface = interface
    self.logger = logger
    self.vanilla_chars: Optional[list[int]] = None

  @property
  def addresses(self) -> dict:
    return self.interface.addresses

  def read32(self, address: int) -> int:
    return self.interface._read32(address)

  def read16(self, address: int) -> int:
    return self.interface._read16(address)

  def read_many(self, addresses: list[int]) -> list[int]:
    return self.interface._batch_read32(addresses)

  def read_bytes(self, address: int, n: int) -> bytes:
    return self.interface._read_bytes(address, n)

  def write32(self, address: int, value: int) -> None:
    self.interface._write32(address, value)

  def write16(self, address: int, value: int) -> None:
    self.interface._write16(address, value)

  def write_bytes(self, address: int, data: bytes) -> None:
    self.interface._write_bytes(address, data)

  def write_many(self, operations: list[tuple[int, int]]) -> None:
    self.interface._batch_write32(operations)

  def _table_base(self) -> int:
    return self.read32(GLYPH_SET + 0x54)

  def _slot(self, glyph: int) -> int:
    """Address of the pointer to this glyph's vector data, in the live
    (relocated) table."""
    return self._table_base() - 0x24 + glyph * 0x40

  def installed(self) -> bool:
    return self._table_base() == MENU_ICON_TABLE + 0x24

  def install_structure(self) -> None:
    """Install the relocated glyph table + group array with the appended
    filler and unknown glyphs. Must run only once per map (guarded above)."""
    if self.installed():
      return
    self._relocate_table()
    self._copy_node(MENU_ICON_FOURTH_NODE, FOURTH_GLYPH)
    self._copy_node(MENU_ICON_FIFTH_NODE, FIFTH_GLYPH)
    # Append both elements before the group array is relocated (which happens
    # inside the first _new_glyph), so the one relocation copies them both in.
    self._append_element(
      MENU_ICON_GROUP, MENU_ICON_FOURTH_ELEMS, MENU_ICON_FOURTH_NODE,
      FOURTH_ELEM
    )
    self._append_element(
      MENU_ICON_GROUP, MENU_ICON_FIFTH_ELEMS, MENU_ICON_FIFTH_NODE, FIFTH_ELEM
    )
    fill, sil = MENU_ICON_PACKETS["filler"]
    self._new_glyph(FOURTH_GLYPH, fill, sil, [MENU_ICON_FOURTH_ARENA])
    fill, sil = MENU_ICON_PACKETS["unknown"]
    self._new_glyph(FIFTH_GLYPH, fill, sil, [MENU_ICON_FIFTH_ARENA])

  def _relocate_table(self) -> None:
    base = self._table_base()
    buffer = self.read_bytes(base - 0x24, TABLE_ENTRIES * 0x40 + 0x24)
    self.write_bytes(MENU_ICON_TABLE, buffer)
    self.write32(GLYPH_SET + 0x50, FOURTH_GLYPH)
    self.write32(GLYPH_SET + 0x54, MENU_ICON_TABLE + 0x24)
    self.write32(GLYPH_TABLE_ALT, MENU_ICON_TABLE + 0x24)

  def _copy_node(self, dest: int, glyph: int) -> None:
    """Copy a character row's node chain to dest, retargeted to draw glyph."""
    source = self.read32(MENU_ICON_ELEMS + 0x18 + 4)
    chain = bytearray(self.read_bytes(source, 0x60))
    for offset in range(0, 0x60, 4):
      word = struct.unpack_from("<I", chain, offset)[0]
      if word == source + 0x20:
        struct.pack_into("<I", chain, offset, dest + 0x20)
      elif word == source + 0x40:
        struct.pack_into("<I", chain, offset, dest + 0x40)
    struct.pack_into("<I", chain, 0x20, glyph)
    self.write_bytes(dest, bytes(chain))

  def _append_element(
    self, group: int, dest: int, node: int, element_id: int
  ) -> None:
    count = self.read16(group)
    array = bytearray(self.read_bytes(self.read32(group + 4), count * 0x18))
    element = bytearray(array[0x18:0x30])
    element[4:8] = struct.pack("<I", node)
    element[0x14:0x18] = struct.pack("<I", element_id)
    self.write_bytes(dest, bytes(array + element))
    self.write32(group + 4, dest)
    self.write16(group, count + 1)

  def _free_template(self, group_address: int, size: int) -> bytes:
    pool = self.read32(group_address + 8)
    count = self.read16(group_address + 2)
    for k in range(count):
      buffer = self.read32(pool + k * 0x18 + 4)
      if all(self.read32(buffer + h * 0x70 + 0x30) == 0
          for h in range(size // 0x70)):
        return self.read_bytes(buffer, size)
    raise RuntimeError(f"no free instance buffer in group {group_address:#x}")

  def _append_group(
    self, proto: int, entries: list[int], scales: list[float],
    arena: list[int]
  ) -> int:
    def alloc(n: int) -> int:
      address = arena[0]
      arena[0] = (address + n + 0xF) & ~0xF
      return address

    count = self.read32(GLYPH_SET + 0x80)
    old = self.read32(GLYPH_SET + 0x84)
    if old != MENU_ICON_GROUPS:
      self.write_bytes(MENU_ICON_GROUPS, self.read_bytes(old, count * 0x30))
    proto_address = self.read32(GLYPH_SET + 0x84) + proto * 0x30
    flag = self.read32(self.read32(proto_address + 8))
    size = flag * 0x70
    template = self._free_template(proto_address, size)
    pool = alloc(MENU_ICON_POOL * 0x18)
    entries_data = b""
    for _ in range(MENU_ICON_POOL):
      buffer = alloc(size)
      self.write_bytes(buffer, template)
      entries_data += struct.pack(
        "<IIIIII", flag, buffer, MENU_ICON_FREE_TAG, 0, 0, 0
      )
    self.write_bytes(pool, entries_data)
    new_group = MENU_ICON_GROUPS + count * 0x30
    source_node = self.read32(self.read32(proto_address + 4) + 4)
    channel = self.read_bytes(source_node + 0x20, 0x40)
    node = alloc(0x20 + len(entries) * 0x40)
    end = node + 0x20 + len(entries) * 0x40
    body = bytearray(struct.pack(
      "<8I", 0, len(entries), end, node + 0x20, end, end, 0, end
    ))
    for glyph, scale in zip(entries, scales):
      entry = bytearray(channel)
      entry[0:4] = struct.pack("<I", glyph)
      entry[0x10:0x14] = struct.pack("<f", scale)
      entry[0x1C:0x20] = struct.pack("<f", scale)
      body += entry
    self.write_bytes(node, bytes(body))
    element = bytearray(self.read_bytes(self.read32(proto_address + 4), 0x18))
    element[4:8] = struct.pack("<I", node)
    element[0x10:0x14] = struct.pack("<I", new_group)
    element_array = alloc(0x18)
    self.write_bytes(element_array, bytes(element))
    group = bytearray(self.read_bytes(proto_address, 0x30))
    group[0:4] = struct.pack("<I", (MENU_ICON_POOL << 16) | 1)
    group[4:8] = struct.pack("<I", element_array)
    group[8:12] = struct.pack("<I", pool)
    self.write_bytes(new_group, bytes(group))
    self.write32(GLYPH_SET + 0x84, MENU_ICON_GROUPS)
    self.write32(GLYPH_SET + 0x80, count + 1)
    return count

  def _new_glyph(
    self, glyph: int, fill: int, sil: int, arena: list[int]
  ) -> None:
    """Build a two-channel appended glyph like the character slots: a row
    glyph whose child group draws [silhouette, icon] channels."""
    sil_drawer, sil_holder, icon_drawer = glyph + 1, glyph + 2, glyph - 1

    def entry(source: int) -> bytearray:
      return bytearray(self.read_bytes(self._slot(source), 0x40))

    holder = entry(0x2F)
    holder[0x24:0x28] = struct.pack("<I", sil_drawer)
    holder[0:4] = bytes(4)
    self.write_bytes(self._slot(sil_drawer), bytes(holder))
    holder = entry(0x30)
    holder[0x24:0x28] = struct.pack("<I", sil_holder)
    holder[0:4] = struct.pack("<I", sil)
    self.write_bytes(self._slot(sil_holder), bytes(holder))
    holder = entry(0x30)
    holder[0x24:0x28] = struct.pack("<I", icon_drawer)
    holder[0:4] = bytes(4)
    self.write_bytes(self._slot(icon_drawer), bytes(holder))
    group = self._append_group(
      MENU_ICON_PROTO_GROUP, [sil_drawer, 0x10000 | icon_drawer],
      [1.0, 1.0], arena
    )
    row = entry(0x31)
    row[0x24:0x28] = struct.pack("<I", glyph)
    row[0:4] = struct.pack("<I", fill)
    row[0x34:0x38] = struct.pack("<I", group)
    self.write_bytes(self._slot(glyph), bytes(row))
    self.write32(
      GLYPH_SET + 0x50, max(self.read32(GLYPH_SET + 0x50), sil_holder)
    )

  def install_chooser(self) -> None:
    if not self.interface.cave_live():
      return
    for site, patched, original in MENU_ICON_CHOOSER:
      self.interface.safe_patch(site, patched, original)

  def apply_theme(self, theme: int) -> None:
    if theme == 0:
      for glyph, packet in MENU_ICON_VANILLA_PACKETS.items():
        self.write32(self._slot(glyph), packet)
      return
    icons = THEMES[theme]
    for cls, (fill_glyph, sil_glyph) in MENU_ICON_GLYPHS.items():
      fill_address, sil_address = MENU_ICON_PACKETS[cls]
      self.write_bytes(fill_address, decode(icons[cls].fill))
      self.write_bytes(sil_address, decode(icons[cls].sil))
      self.write32(self._slot(fill_glyph), fill_address)
      self.write32(self._slot(sil_glyph), sil_address)

  def save_vanilla_chars(self) -> None:
    if self.vanilla_chars is not None:
      return
    costs = self.addresses["thiefnet costs"]
    self.vanilla_chars = self.read_many([costs[i] - 4 for i in range(24)])

  def set_row_chars(self, classes: Optional[list[str]]) -> None:
    """Write each row's char word (item entry +4), which selects its glyph.
    A None list restores the saved vanilla grouping (theme 0)."""
    costs = self.addresses["thiefnet costs"]
    if classes is None:
      chars = self.vanilla_chars or [0] * 24
    else:
      chars = [MENU_ICON_CHARS[cls] for cls in classes]
    self.write_many([(costs[i] - 4, chars[i]) for i in range(24)])
