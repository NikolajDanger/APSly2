"""Module for installing pickpocket loot models into a map that doesn't
have them already."""

import struct
import time
from logging import Logger
from typing import TYPE_CHECKING, NamedTuple

from .data.Constants import CAVE_HEAP_ALLOC
from .data.LootModels import CLUTS, LOOT_MODELS, TEXTURES, LootModel, decode

if TYPE_CHECKING:
  from .Sly2Interface import Sly2Interface

PART_SIZE = 0x28
RECORD_SIZE = 0x14
BOUNDS_SIZE = 0x18
TYPE_ROW_SIZE = 0x2C
TEXTURE_RECORD_SIZE = 0x28
CLUT_RECORD_SIZE = 0x20
OUTLINE_FLAGS = 0x49
HIDDEN_FLAG = 0x800
POOL_CAPACITY = 64
VRAM_BLOCKS = 0x4000
VRAM_PAGE = 0x80
# The game's texture loader folds a block that reaches the end of VRAM back
# to block 0, which renders as garbage, so the last page is never free.
USABLE_VRAM = VRAM_BLOCKS - VRAM_PAGE
TEXTURE_VRAM_START = 0x1800
ALLOCATOR_SIZE = 0x40
CLAIM_TIMEOUT = 0.5
GLOBALS = (
  "texture table count", "texture table", "clut table count", "clut table",
  "texture registry", "clut registry", "pending textures", "pending cluts"
)


class Pool(NamedTuple):
  managers: list[int]
  lists: list[int]
  parts: int
  part_ids: set[int]
  records: int
  bounds: int
  matrices: list[int]
  flags_base: int
  material_base: int
  projection: bytes
  bounds_textured: bytes
  bounds_outline: bytes


class Group(NamedTuple):
  run: tuple[int, int]
  tex_ids: list[int]
  clut_ids: list[int]


class GroupCall(NamedTuple):
  allocator: int
  table: int
  clut_table: int
  registry: int
  tex_ids: list[int]
  clut_ids: list[int]


class Upload:
  # An upload takes one call to the game's texture loader per VRAM run, and
  # the cave runs one call per frame, so poll issues them one at a time. The
  # TEX0 patches need every texture's final block, so they wait for the last.
  def __init__(
    self, calls: list[GroupCall],
    patches: list[tuple[int, int, int, int]],
    records: dict[str, dict[int, tuple[int, ...]]],
    restore: list[tuple[int, int]]
  ) -> None:
    self.calls = calls
    self.patches = patches
    self.records = records
    self.restore = restore
    self.index = 0
    self.count = 0
    self.tex: dict[int, tuple[int, ...]] = {}
    self.clut: dict[int, tuple[int, ...]] = {}


def align(value: int, to: int = 16) -> int:
  return (value + to - 1) & ~(to - 1)


def model_size(model: LootModel) -> int:
  return sum(
    align(part.main + part.second) + sum(align(n) for n in part.refs)
    for part in model.parts
  )


def group_size(group: Group) -> int:
  table_size = len(group.tex_ids) * TEXTURE_RECORD_SIZE
  clut_table_size = len(group.clut_ids) * CLUT_RECORD_SIZE
  slots = align(4 * (len(group.tex_ids) + len(group.clut_ids) + 1))
  pixels = sum(
    align(len(decode(TEXTURES[i][1]))) for i in group.tex_ids
  ) + sum(align(len(decode(CLUTS[i][1]))) for i in group.clut_ids)
  return (
    ALLOCATOR_SIZE + align(table_size) + align(clut_table_size) + slots +
    pixels
  )


def dma_tags(chain: bytes) -> list[tuple[int, int, int, int]]:
  tags = []
  offset = 0
  while offset + 16 <= len(chain):
    low, high = struct.unpack_from("<II", chain, offset)
    qwc, tag_id, address = low & 0xFFFF, (low >> 28) & 7, high & 0x7FFFFFFF
    tags.append((offset, tag_id, qwc, address))
    if tag_id in (0, 6, 7):
      break
    offset += 16 + (qwc * 16 if tag_id == 1 else 0)
  return tags


def projection_block(buffer: bytes) -> tuple[int, bytes] | None:
  for offset in range(0, len(buffer) - 12, 4):
    word = struct.unpack_from("<I", buffer, offset)[0]
    if (word >> 16) == 0x4B00:
      return word & 0xFFFF, buffer[offset:offset + 16]
  return None


def rebase_projection(
  buffer: bytes, source: tuple[int, bytes], target: tuple[int, bytes]
) -> bytes:
  data = bytearray(buffer.replace(source[1], target[1]))
  offsets = {source[0] + k: target[0] + k for k in (0, 0x1000, 0x2000)}
  for offset in range(0, len(data), 4):
    word = struct.unpack_from("<I", data, offset)[0]
    if (word >> 16) == 0x4B00 and (word & 0xFFFF) in offsets:
      struct.pack_into(
        "<I", data, offset, 0x4B000000 | offsets[word & 0xFFFF]
      )
  return bytes(data)


def tex0_offsets(buffer: bytes) -> list[int]:
  # Pattern for finding the texture info of the drawn model.
  return [
    offset for offset in range(0, len(buffer) - 32, 4)
    if struct.unpack_from("<IIII", buffer, offset + 8) == (6, 0, 0x61, 0) and
    struct.unpack_from("<I", buffer, offset + 24)[0] == 0x14
  ]


def rebase_destinations(
  chain: bytes, source: int, target: int, span: int
) -> bytes:
  data = bytearray(chain)
  for offset in range(0, len(data), 4):
    word = struct.unpack_from("<I", data, offset)[0]
    if source <= word < source + span:
      struct.pack_into("<I", data, offset, target + (word - source))
  return bytes(data)


def texture_blocks(words: tuple[int, ...]) -> int:
  return words[3] >> 16


def clut_blocks(words: tuple[int, ...]) -> int:
  return words[2] >> 16


class LootInstaller:
  def __init__(self, interface: "Sly2Interface", logger: Logger) -> None:
    self.interface = interface
    self.logger = logger
    self.pending: Upload | None = None
    self.claimed: int | None = None
    self.claim_end = 0

  @property
  def addresses(self) -> dict:
    return self.interface.addresses

  # =====================================================
  # Memory Helpers
  # =====================================================

  def read32(self, address: int) -> int:
    return self.interface._read32(address)

  def read_many(self, addresses: list[int]) -> list[int]:
    return self.interface._batch_read32(addresses)

  def read_bytes(self, address: int, n: int) -> bytes:
    return self.interface._read_bytes(address, n)

  def write_bytes(self, address: int, data: bytes) -> None:
    self.interface._write_bytes(address, data)

  def write_many(self, operations: list[tuple[int, int]]) -> None:
    self.interface._batch_write32(operations)

  def claim(self, size: int) -> bool:
    """Claims one block for the whole install from the level heap, through
    the cave: the game allocates from the same pointer on its own thread, so
    bumping it from here can hand out memory a live object was just given
    (see CAVE_HEAP_ALLOC)."""
    interface = self.interface
    slot = self.addresses["cave call"]
    interface.invalidate(slot + 0x18, 4)
    count = interface.call_count()
    if not interface.call_function(CAVE_HEAP_ALLOC, [align(size)]):
      return False
    deadline = time.monotonic() + CLAIM_TIMEOUT
    while True:
      interface.invalidate(slot + 0x18, 4)
      if interface.call_count() != count:
        break
      if time.monotonic() > deadline:
        self.logger.warning(
          "The cave never serviced the heap claim; loot models not installed"
        )
        return False
      time.sleep(0.002)
    interface.invalidate(slot + 0x14, 4)
    self.claimed = self.read32(slot + 0x14)
    self.claim_end = self.claimed + align(size)
    return True

  def allocate(self, size: int) -> int:
    assert self.claimed is not None
    address = self.claimed
    self.claimed = address + align(size)
    assert self.claimed <= self.claim_end
    return address

  # =====================================================
  # The Pool
  # =====================================================

  def managers(self) -> list[int]:
    first = self.read32(self.addresses["loot pool"])
    last = self.read32(self.addresses["loot pool last"])
    out = [first]
    while out[-1] != last and len(out) < 16:
      out.append(self.read32(out[-1] + 0x1C))
    return out

  def read_pool(self) -> Pool | None:
    managers = self.managers()
    template = managers[0]
    count, records, bounds = self.read_many(
      [template + 0xB8, template + 0xBC, template + 0xC4]
    )
    if count == 0:
      return None
    lists = self.read_many([m + 0xC0 for m in managers])
    matrices = self.read_many([lst + 4 for lst in lists])
    entries = self.read_bytes(lists[0], count * PART_SIZE)
    textured = outline = None
    part_ids = set()
    for i in range(count):
      words = struct.unpack_from("<10I", entries, i * PART_SIZE)
      part_ids.add(words[0])
      if words[3] == OUTLINE_FLAGS:
        outline = outline if outline is not None else i
      elif words[5] and textured is None:
        textured = i
    if textured is None or outline is None:
      return None
    words = struct.unpack_from("<10I", entries, textured * PART_SIZE)
    chain = self.read_bytes(words[4], 16)
    _, tag_id, qwc, buffer = dma_tags(chain)[0]
    projection = projection_block(
      self.read_bytes(buffer, min(qwc * 16, 0x100))
    )
    if tag_id not in (3, 4) or projection is None:
      return None
    return Pool(
      managers, lists, count, part_ids, records, bounds, matrices,
      words[3] & ~0xFF, (words[4] - words[5]) & 0xFFFFFFFF, projection[1],
      self.read_bytes(bounds + textured * BOUNDS_SIZE, BOUNDS_SIZE),
      self.read_bytes(bounds + outline * BOUNDS_SIZE, BOUNDS_SIZE)
    )

  def type_rows(self, template: int) -> dict[int, int]:
    """Returns the global table of the 'part ID's for every piece of loot,
    which tells the game what loot geometry to load."""
    table, n = self.read_many([template + 0x240, template + 0x23C])
    raw = self.read_bytes(table, n * TYPE_ROW_SIZE)
    return dict(
      struct.unpack_from("<I28xI", raw, i * TYPE_ROW_SIZE) for i in range(n)
    )

  def grow_size(self, pool: Pool) -> int:
    size = POOL_CAPACITY * PART_SIZE
    if (
      pool.records == pool.lists[0] + size * len(pool.managers) and
      pool.bounds == pool.records + POOL_CAPACITY * RECORD_SIZE
    ):
      return 0
    return (
      size * len(pool.managers) + POOL_CAPACITY * (RECORD_SIZE + BOUNDS_SIZE)
    )

  def grow_pool(self, pool: Pool) -> Pool:
    # The pool is moved to free memory, because the array only has room for
    # the vanilla values.
    size = POOL_CAPACITY * PART_SIZE
    lists = pool.lists
    total = self.grow_size(pool)
    if total == 0:
      return pool
    block = self.allocate(total)
    records = block + size * len(pool.managers)
    bounds = records + POOL_CAPACITY * RECORD_SIZE
    operations = []
    for i, (manager, lst) in enumerate(zip(pool.managers, lists)):
      new = block + i * size
      self.write_bytes(new, self.read_bytes(lst, pool.parts * PART_SIZE))
      operations += [
        (manager + 0xC0, new), (manager + 0xBC, records),
        (manager + 0xC4, bounds)
      ]
    self.write_bytes(
      records, self.read_bytes(pool.records, pool.parts * RECORD_SIZE)
    )
    self.write_bytes(
      bounds, self.read_bytes(pool.bounds, pool.parts * BOUNDS_SIZE)
    )
    self.write_many(operations)
    return pool._replace(
      lists=[block + i * size for i in range(len(pool.managers))],
      records=records, bounds=bounds
    )

  # =====================================================
  # Textures
  # =====================================================

  def resident_records(self) -> dict[str, dict[int, tuple[int, ...]]]:
    start, end = self.addresses["texture records"]
    memory = self.read_bytes(start, end - start)
    found: dict[str, dict[int, tuple[int, ...]]] = {"tex": {}, "clut": {}}
    sizes = {1 << k for k in range(3, 11)}
    for offset in range(0, len(memory) - TEXTURE_RECORD_SIZE, 4):
      flag = struct.unpack_from("<I", memory, offset + 4)[0]
      if (flag & 0xFF) != 1 or flag > 0xFFFF:
        continue
      words = struct.unpack_from("<10I", memory, offset)
      if (
        words[7] and (words[7] >> 29) == 1 and words[5] == 0 and
        (words[6] & 0xFFFFF) == 0 and (words[6] >> 20) in (0x13, 0x14) and
        0 < words[4] <= 0x40
      ):
        found["clut"].setdefault(words[0], words[:8])
      elif (
        (words[2] & 0xFFFF) in sizes and (words[2] >> 16) in sizes and
        words[7] == 0 and words[4] and words[6] == (words[4] + 15) // 16
      ):
        found["tex"].setdefault(words[0], words)
    return found

  def free_vram(
    self, records: dict[str, dict[int, tuple[int, ...]]]
  ) -> list[tuple[int, int]]:
    used = bytearray(VRAM_BLOCKS)
    for words in records["tex"].values():
      start = words[8] & 0x3FFF
      used[start:start + texture_blocks(words)] = b"\1" * texture_blocks(words)
    for words in records["clut"].values():
      start = (words[7] >> 5) & 0x3FFF
      used[start:start + clut_blocks(words)] = b"\1" * clut_blocks(words)
    runs = []
    start = None
    for block in range(TEXTURE_VRAM_START, USABLE_VRAM + 1):
      free = block < USABLE_VRAM and not used[block]
      if free and start is None:
        start = block
      elif not free and start is not None:
        runs.append((start, block - start))
        start = None
    return sorted(runs, key=lambda run: -run[1])

  def used_blocks(
    self, records: dict[str, dict[int, tuple[int, ...]]]
  ) -> int:
    used = bytearray(VRAM_BLOCKS)
    for words in records["tex"].values():
      start = words[8] & 0x3FFF
      used[start:start + texture_blocks(words)] = b"\1" * texture_blocks(words)
    for words in records["clut"].values():
      start = (words[7] >> 5) & 0x3FFF
      used[start:start + clut_blocks(words)] = b"\1" * clut_blocks(words)
    return sum(used)

  # =====================================================
  # Install
  # =====================================================

  def install(self, loot_ids: list[int]) -> list[int]:
    if self.pending is not None or not self.interface.cave_live():
      return []
    pool = self.read_pool()
    if pool is None:
      return []
    rows = self.type_rows(pool.managers[0])
    wanted = [
      loot_id for loot_id in loot_ids
      if loot_id in LOOT_MODELS and loot_id in rows and
      rows[loot_id] not in pool.part_ids
    ]
    if not wanted:
      return []
    needed_parts = sum(len(LOOT_MODELS[loot_id].parts) for loot_id in wanted)
    while wanted and pool.parts + needed_parts > POOL_CAPACITY:
      needed_parts -= len(LOOT_MODELS[wanted.pop()].parts)
    if not wanted:
      self.logger.warning("Loot pool full; no room for foreign loot models")
      return []
    records = self.resident_records()
    uploads = self.plan_uploads(wanted, records)
    if uploads is None:
      return []
    wanted, groups = uploads
    total = (
      self.grow_size(pool) +
      sum(model_size(LOOT_MODELS[loot_id]) for loot_id in wanted) +
      sum(group_size(group) for group in groups)
    )
    if not self.claim(total):
      return []
    try:
      pool = self.grow_pool(pool)
      patches = []
      installed = []
      for loot_id in wanted:
        model = LOOT_MODELS[loot_id]
        parts, part_patches = self.install_model(pool, model)
        pool = pool._replace(parts=parts)
        patches += part_patches
        installed.append(loot_id)
      uploaded = sum(len(g.tex_ids) for g in groups)
      self.bind_textures(patches, records, groups)
    finally:
      self.claimed = None
    self.logger.debug(
      f"Installed loot models {[hex(i) for i in installed]}"
      + (f", uploading {uploaded} texture(s)" if uploaded else "")
      + f" ({self.used_blocks(records)} VRAM blocks in use)"
    )
    return installed

  def plan_uploads(
    self, wanted: list[int], records: dict[str, dict[int, tuple[int, ...]]]
  ) -> tuple[list[int], list[Group]] | None:
    tex_ids: list[int] = []
    clut_ids: list[int] = []
    groups: list[Group] = []
    kept = []
    for loot_id in wanted:
      new_tex = []
      new_clut = []
      for part in LOOT_MODELS[loot_id].parts:
        for tex_id, clut_id in part.textures.values():
          if tex_id not in records["tex"] and tex_id not in tex_ids + new_tex:
            new_tex.append(tex_id)
          if (
            clut_id not in records["clut"] and
            clut_id not in clut_ids + new_clut
          ):
            new_clut.append(clut_id)
      if (
        any(i not in TEXTURES for i in new_tex) or
        any(i not in CLUTS for i in new_clut)
      ):
        self.logger.warning(f"No texture data for loot {loot_id:#x}")
        continue
      packed = self.plan_groups(tex_ids + new_tex, clut_ids + new_clut, records)
      if packed is None:
        self.logger.warning(
          f"No VRAM for the textures of loot {loot_id:#x}; left invisible"
        )
        continue
      tex_ids += new_tex
      clut_ids += new_clut
      groups = packed
      kept.append(loot_id)
    if not kept:
      return None
    return kept, groups

  def plan_groups(
    self, tex_ids: list[int], clut_ids: list[int],
    records: dict[str, dict[int, tuple[int, ...]]]
  ) -> list[Group] | None:
    # Biggest first, one loader call per free run.
    bins: list[tuple[tuple[int, int], list[int], list[int]]] = [
      (run, [], []) for run in self.free_vram(records)
    ]
    for tex_id in sorted(
      tex_ids, key=lambda t: -texture_blocks(TEXTURES[t][0])
    ):
      for run, gtex, gclut in bins:
        if self.run_fits(run, gclut, gtex + [tex_id]):
          gtex.append(tex_id)
          break
      else:
        return None
    for clut_id in clut_ids:
      for run, gtex, gclut in bins:
        if self.run_fits(run, gclut + [clut_id], gtex):
          gclut.append(clut_id)
          break
      else:
        return None
    return [
      Group(run, gtex, gclut) for run, gtex, gclut in bins if gtex or gclut
    ]

  def run_fits(
    self, run: tuple[int, int], clut_ids: list[int], tex_ids: list[int]
  ) -> bool:
    # Mirrors the game's texture loader: cluts first, then textures in table
    # order, each snapped to the next 0x80-block page if it would straddle one.
    end = run[0] + run[1]
    top = run[0]
    sizes = [clut_blocks(CLUTS[c][0]) for c in clut_ids] + [
      texture_blocks(TEXTURES[t][0]) for t in tex_ids
    ]
    for size in sizes:
      boundary = (top // VRAM_PAGE + 1) * VRAM_PAGE
      if boundary < top + size:
        top = boundary
      if top + size > end:
        return False
      top += size
    return True

  def install_model(
    self, pool: Pool, model: LootModel
  ) -> tuple[int, list[tuple[int, int, int, int]]]:
    data = decode(model.data)
    pieces = []
    cursor = 0
    for part in model.parts:
      main = data[cursor:cursor + part.main]
      cursor += part.main
      refs = []
      for n in part.refs:
        refs.append(data[cursor:cursor + n])
        cursor += n
      pieces.append((main, refs, data[cursor:cursor + part.second]))
      cursor += part.second
    source_projection = next(
      projection_block(refs[0]) for _, refs, _ in pieces if refs
    )
    target_projection = projection_block(pool.projection)
    assert source_projection and target_projection
    block = self.allocate(model_size(model))
    address = block
    patches = []
    entries = []
    for part, (main, raw_refs, raw_second) in zip(model.parts, pieces):
      buffers = []
      for raw in raw_refs:
        buffer = rebase_projection(raw, source_projection, target_projection)
        self.write_bytes(address, buffer)
        buffers.append(address)
        address += align(len(raw))
      second = rebase_destinations(
        raw_second, model.material_base, pool.material_base, part.main
      )
      chain = bytearray(main)
      refs = iter(buffers)
      for offset, tag_id, _, _ in dma_tags(main):
        if tag_id in (3, 4):
          struct.pack_into("<I", chain, offset + 4, next(refs))
      self.write_bytes(address, bytes(chain) + second)
      for (ref, offset), (tex_id, clut_id) in part.textures.items():
        patches.append((buffers[ref], offset, tex_id, clut_id))
      flags = (
        OUTLINE_FLAGS if part.flags == OUTLINE_FLAGS
        else pool.flags_base | (part.flags & 0xFF)
      ) & ~HIDDEN_FLAG
      material = (
        (address - pool.material_base) & 0xFFFFFFFF if part.refs else 0
      )
      record = list(part.record)
      record[2] = address + part.main if part.second else 0
      entries.append(
        (part.part_id, flags, address, material, record, bool(part.refs))
      )
      address += align(part.main + part.second)
    operations = []
    for manager, lst, matrix in zip(pool.managers, pool.lists, pool.matrices):
      self.write_bytes(lst + pool.parts * PART_SIZE, b"".join(
        struct.pack("<10I", part_id, matrix, 0, flags, dl, material, 0, 0, 0, 0)
        for part_id, flags, dl, material, _, _ in entries
      ))
      operations.append((manager + 0xB8, pool.parts + len(entries)))
    self.write_bytes(pool.records + pool.parts * RECORD_SIZE, b"".join(
      struct.pack("<5I", *record) for _, _, _, _, record, _ in entries
    ))
    self.write_bytes(pool.bounds + pool.parts * BOUNDS_SIZE, b"".join(
      pool.bounds_textured if textured else pool.bounds_outline
      for *_, textured in entries
    ))
    self.write_many(operations)
    return pool.parts + len(entries), patches

  def bind_textures(
    self, patches: list[tuple[int, int, int, int]],
    records: dict[str, dict[int, tuple[int, ...]]], groups: list[Group]
  ) -> None:
    now = [
      p for p in patches
      if p[2] in records["tex"] and p[3] in records["clut"]
    ]
    self.patch_tex0(now, records["tex"], records["clut"])
    later = [p for p in patches if p not in now]
    if not later or not groups:
      return
    calls = [self.prepare_group(group) for group in groups]
    globals_ = [self.addresses[name] for name in GLOBALS]
    restore = list(zip(globals_, self.read_many(globals_)))
    self.pending = Upload(calls, later, records, restore)
    self.issue_group(calls[0])

  def prepare_group(self, group: Group) -> GroupCall:
    tex_ids, clut_ids = group.tex_ids, group.clut_ids
    table_size = len(tex_ids) * TEXTURE_RECORD_SIZE
    clut_table_size = len(clut_ids) * CLUT_RECORD_SIZE
    slots = align(4 * (len(tex_ids) + len(clut_ids) + 1))
    block = self.allocate(group_size(group))
    table = block + ALLOCATOR_SIZE
    clut_table = table + align(table_size)
    slot_base = clut_table + align(clut_table_size)
    address = slot_base + slots
    # Cap the allocator at the run's end rather than the end of VRAM, so an
    # overrun stops the loader instead of folding to block 0.
    self.write_bytes(
      block, struct.pack(
        "<3I", TEXTURE_VRAM_START, group.run[0], group.run[0] + group.run[1]
      ) + bytes(ALLOCATOR_SIZE - 12)
    )
    self.write_bytes(slot_base, bytes(slots))
    rows = b""
    for n, tex_id in enumerate(tex_ids, 1):
      words, data = TEXTURES[tex_id]
      pixels_data = decode(data)
      self.write_bytes(address, pixels_data)
      row = list(words)
      row[0], row[5] = n, address
      rows += struct.pack("<10I", *row)
      address += align(len(pixels_data))
    self.write_bytes(table, rows)
    rows = b""
    for n, clut_id in enumerate(clut_ids, len(tex_ids) + 1):
      words, data = CLUTS[clut_id]
      clut_data = decode(data)
      self.write_bytes(address, clut_data)
      row = list(words)
      row[0], row[3] = n, address
      rows += struct.pack("<8I", *row)
      address += align(len(clut_data))
    self.write_bytes(clut_table, rows)
    return GroupCall(
      block, table, clut_table, slot_base - 4, list(tex_ids), list(clut_ids)
    )

  def issue_group(self, call: GroupCall) -> None:
    assert self.pending is not None
    globals_ = [self.addresses[name] for name in GLOBALS]
    self.write_many(list(zip(globals_, [
      len(call.tex_ids), call.table, len(call.clut_ids), call.clut_table,
      call.registry, call.registry, len(call.tex_ids), len(call.clut_ids)
    ])))
    self.pending.count = self.interface.call_count()
    self.interface.call_function(self.addresses["texture loader"], [
      call.allocator
    ])

  def patch_tex0(
    self, patches: list[tuple[int, int, int, int]],
    tex: dict[int, tuple[int, ...]], clut: dict[int, tuple[int, ...]]
  ) -> None:
    for buffer, offset, tex_id, clut_id in patches:
      low, high = struct.unpack("<2I", self.read_bytes(buffer + offset, 8))
      tbp = tex[tex_id][8] & 0x3FFF
      cbp = (clut[clut_id][7] >> 5) & 0x3FFF
      self.write_bytes(buffer + offset, struct.pack(
        "<2I", (low & ~0x3FFF) | tbp, (high & ~(0x3FFF << 5)) | (cbp << 5)
      ))

  def poll(self) -> bool:
    """Returns true if the texture upload is underway"""
    if self.pending is None:
      return False
    upload = self.pending
    if self.interface.call_count() == upload.count:
      return True
    call = upload.calls[upload.index]
    # The call can complete within the tick that issued it, leaving the
    # template rows in the tick cache.
    self.interface.invalidate(
      call.table, len(call.tex_ids) * TEXTURE_RECORD_SIZE
    )
    self.interface.invalidate(
      call.clut_table, len(call.clut_ids) * CLUT_RECORD_SIZE
    )
    for k, tex_id in enumerate(call.tex_ids):
      upload.tex[tex_id] = struct.unpack("<10I", self.read_bytes(
        call.table + k * TEXTURE_RECORD_SIZE, TEXTURE_RECORD_SIZE
      ))
    for k, clut_id in enumerate(call.clut_ids):
      upload.clut[clut_id] = struct.unpack("<8I", self.read_bytes(
        call.clut_table + k * CLUT_RECORD_SIZE, CLUT_RECORD_SIZE
      ))
    upload.index += 1
    if upload.index < len(upload.calls):
      self.issue_group(upload.calls[upload.index])
      return True
    self.pending = None
    self.write_many(upload.restore)
    tex = {**upload.records["tex"], **upload.tex}
    clut = {**upload.records["clut"], **upload.clut}
    wrapped = {i for i, w in upload.tex.items() if (w[8] & 0x3FFF) == 0}
    if wrapped:
      self.logger.warning(
        f"Loot texture(s) {[hex(i) for i in wrapped]} landed on VRAM block 0; "
        "leaving them unbound"
      )
    self.patch_tex0(
      [p for p in upload.patches if p[2] not in wrapped], tex, clut
    )
    self.logger.debug(
      f"Loot textures placed at VRAM blocks "
      f"{[hex(w[8] & 0x3FFF) for w in upload.tex.values()]}"
    )
    return False

  def reset(self) -> None:
    self.pending = None
