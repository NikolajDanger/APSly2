"""The Hypnosis trap's effect: the Contessa's hypnosis, rebuilt in whatever
map the trap fires in from the episode 5 copies in data/Hypnosis.py. Per
map it creates the screen overlay's state-machine object with a relocated
copy of its animation data, appends Sly's spiral eye parts (hidden) to the
character's model and builds the hypnotized walk as a set of animation
controllers. Switching the trap on loads the hypnosis sound's bank into the
sound driver, swaps the character's walk blend onto the built controllers,
shows the eyes, starts the overlay and the sound, and arms the cave's vjoy
hook (build/cave.s hypno_vjoy), which locks the action
buttons, fixes the walking pace and steps the overlay's clips."""

import math
import struct
import time
from logging import Logger
from typing import TYPE_CHECKING, NamedTuple, Optional

from .data.Constants import (
  CAVE_HEAP_ALLOC,
  CAVE_HYPNOSIS_BANK_LOAD,
  CAVE_HYPNOSIS_VOICE_CB,
)
from .data.Hypnosis import (
  BANK,
  EYE_DATA,
  EYES,
  OVERLAY,
  OVERLAY_CLUSTER,
  OVERLAY_OBJECT,
  OVERLAY_WORDS,
  OVERLAY_WORDS_OFFSET,
  PHASES,
  WALK_VALUES,
  WALKS,
  HypnosisWalk,
  decode,
)
from .LootInstall import (
  BOUNDS_SIZE,
  CLAIM_TIMEOUT,
  HIDDEN_FLAG,
  PART_SIZE,
  RECORD_SIZE,
  align,
  dma_tags,
  projection_block,
  rebase_projection,
  tex0_offsets,
)

if TYPE_CHECKING:
  from .Sly2Interface import Sly2Interface

OVERLAY_CLASS = 0x7E
OVERLAY_OBJECT_ID = 0xFEE0
NEW_OBJECT = 0x0013E3C8      # PloNew(class, 0, object id, -1)
POST_LOAD = 0x002123C8
OVERLAY_ON = 0x002128E8      # (object, -1): the start clip, then the loop
OVERLAY_OFF = 0x002129E8     # (object): the end clip, then idle
SOUND_PLAY = 0x00232320      # (params, callback, callback arg), looping
SOUND_STOP = 0x00232350      # (voice)
SOUND_UNLOAD = 0x002321B8    # (bank)
BANK_BUSY = 0xFFFFFFFE
START_CLIP = 0.6
LOOP_CLIP = 2.0
END_CLIP = 0.3
FRAME = 1 / 60
PACE = 0.45
DEAD_ZONE = 0.2
PAD_MASK = 0xFF
EYE_TEXTURE = 0x65D
EYE_CLUT = 0x65E
KEYED_CONTROLLER = 0x002CA950
CONSTANT_CONTROLLER = 0x002CA9A0
KEY_SIZE = 0x20
ELEMENT_SIZE = 0x100
DRAW_IN_FRONT = 4
# Entity layout: joints, children, model part arrays, the draw-order flags
ENTITY_VTABLE = 0xC
ENTITY_OBJECT_ID = 0x18
ENTITY_FIRST_CHILD = 0x64
ENTITY_NEXT_SIBLING = 0x24
ENTITY_JOINTS = 0x54
ENTITY_DRAW_FLAGS = 0xD4
ENTITY_PART_COUNT = 0xB8
ENTITY_RECORDS = 0xBC
ENTITY_PARTS = 0xC0
ENTITY_BOUNDS = 0xC4
# The cave's state block (ADDRESSES["hypnosis state"])
STATE_PACE = 0x0
STATE_DEAD_ZONE = 0x4
STATE_PACE_ON = 0x8
STATE_MASK = 0xC
STATE_OVERLAY = 0x10
STATE_START_CLIP = 0x14
STATE_LOOP_CLIP = 0x18
STATE_END_CLIP = 0x1C
STATE_PARAMS = 0x20
PARAMS_SIZE = 0x30
STATE_VOICE = 0x70
STATE_BANK = 0x74


class Character(NamedTuple):
  """A character's per-map build: the walk blend controllers' source
  slots with their original and hypnotized sources, the eye part entries,
  the eye joints' offset slots and the children drawn in front"""
  entity: int
  walk: HypnosisWalk
  swaps: list[tuple[int, int, int]]
  eyes: list[int]
  offsets: dict[int, tuple[float, float, float]]
  front: list[int]


def keys(
  values: list[tuple[float, float, float]], duration: float, wraps: bool
) -> bytes:
  """Hermite keys closing the loop over `duration`; a wrapping rotation
  channel ends a whole number of turns from where it started"""
  n = len(values)
  dt = duration / n
  offset = [0.0, 0.0, 0.0]
  if wraps:
    offset = [
      2 * math.pi * round((2 * values[-1][i] - values[-2][i] - values[0][i])
                          / (2 * math.pi))
      for i in range(3)
    ]
  closed = values + [tuple(values[0][i] + offset[i] for i in range(3))]
  out = b""
  for k in range(n + 1):
    before = (
      closed[k - 1] if k > 0
      else tuple(closed[n - 1][i] - offset[i] for i in range(3))
    )
    after = (
      closed[k + 1] if k < n
      else tuple(closed[1][i] + offset[i] for i in range(3))
    )
    tangent = [(after[i] - before[i]) / (2 * dt) for i in range(3)]
    out += struct.pack("<3ff3ff", *closed[k], k * dt, *tangent, 0.0)
  return out


class HypnosisInstaller:
  def __init__(self, interface: "Sly2Interface", logger: Logger) -> None:
    self.interface = interface
    self.logger = logger
    self.bank_refused = False
    self.bank_buffer: Optional[int] = None
    self.overlay: Optional[int] = None
    self.characters: dict[int, Character] = {}
    self.active: Optional[Character] = None

  @property
  def addresses(self) -> dict:
    return self.interface.addresses

  @property
  def state(self) -> int:
    return self.addresses["hypnosis state"]

  # =====================================================
  # Memory Helpers
  # =====================================================

  def read32(self, address: int) -> int:
    return self.interface._read32(address)

  def read_many(self, addresses: list[int]) -> list[int]:
    return self.interface._batch_read32(addresses)

  def read_bytes(self, address: int, n: int) -> bytes:
    return self.interface._read_bytes(address, n)

  def write32(self, address: int, value: int) -> None:
    self.interface._write32(address, value)

  def write_bytes(self, address: int, data: bytes) -> None:
    self.interface._write_bytes(address, data)

  def write_many(self, operations: list[tuple[int, int]]) -> None:
    self.interface._batch_write32(operations)

  def call(self, function: int, arguments: list[int]) -> Optional[int]:
    """Runs a game function through the cave's call slot and returns its
    result, or None if the cave never serviced it"""
    interface = self.interface
    slot = self.addresses["cave call"]
    interface.invalidate(slot + 0x18, 4)
    count = interface.call_count()
    if not interface.call_function(function, arguments):
      return None
    deadline = time.monotonic() + CLAIM_TIMEOUT
    while True:
      interface.invalidate(slot + 0x18, 4)
      if interface.call_count() != count:
        break
      if time.monotonic() > deadline:
        self.logger.warning(
          f"The cave never serviced a call to {function:#x}; "
          "hypnosis not applied"
        )
        return None
      time.sleep(0.002)
    interface.invalidate(slot + 0x14, 4)
    return self.read32(slot + 0x14)

  def claim(self, size: int) -> Optional[int]:
    return self.call(CAVE_HEAP_ALLOC, [align(size)])

  # =====================================================
  # Lifecycle
  # =====================================================

  def reset(self) -> None:
    """Forgets the map's builds (its heap is gone with it)"""
    self.overlay = None
    self.bank_buffer = None
    self.characters = {}
    self.active = None

  def character_of(self, entity: int) -> Optional[int]:
    """The character id of the entity if it is Sly, Bentley or Murray"""
    if not entity:
      return None
    vtable = self.read32(entity + ENTITY_VTABLE)
    return next((c for c, w in WALKS.items() if w.vtable == vtable), None)

  def apply(self, entity: int) -> bool:
    """Switches the hypnosis on for the entity, building what the map
    lacks first; True once it is on"""
    if self.active is not None:
      if self.active.entity == entity:
        return True
      self.remove()
    character_id = self.character_of(entity)
    if character_id is None or not self.interface.cave_live():
      return False
    if not self.setup_overlay() or not self.setup_bank():
      return False
    character = self.characters.get(entity)
    if character is None:
      character = self.setup_character(entity, character_id)
      if character is None:
        return False
      self.characters[entity] = character
    self.switch_on(character)
    return True

  def remove(self) -> None:
    """Switches the hypnosis off if it is on"""
    if self.active is not None:
      self.switch_off(self.active)
      self.active = None

  def clean(self, entity: int) -> None:
    """Undoes what a stopped client may have left: the sound and its bank,
    and on the entity shown eyes, eye offsets and the draw-order bit (set
    only while the hypnosis is on, so a clear one means there is nothing to
    undo)"""
    self.stop_sound()
    self.unload_bank()
    character_id = self.character_of(entity)
    if character_id is None:
      return
    flags = self.read32(entity + ENTITY_DRAW_FLAGS)
    if not flags & DRAW_IN_FRONT:
      return
    walk = WALKS[character_id]
    operations = [(entity + ENTITY_DRAW_FLAGS, flags & ~DRAW_IN_FRONT)]
    for child in self.front_children(entity, walk):
      operations.append(
        (child + ENTITY_DRAW_FLAGS,
         self.read32(child + ENTITY_DRAW_FLAGS) & ~DRAW_IN_FRONT)
      )
    for entry in self.eye_entries(entity):
      operations.append((entry + 0xC, self.read32(entry + 0xC) | HIDDEN_FLAG))
    self.write_many(operations)
    self.write_offsets(self.offset_slots(entity, walk), False)

  # =====================================================
  # Overlay and sound
  # =====================================================

  def setup_overlay(self) -> bool:
    if self.overlay is not None:
      return True
    cluster = decode(OVERLAY)
    start, end = OVERLAY_CLUSTER
    obj = self.call(NEW_OBJECT, [OVERLAY_CLASS, 0, OVERLAY_OBJECT_ID, -1])
    if not obj:
      return False
    base = self.claim(len(cluster))
    if base is None:
      return False

    def relocate(word: int) -> int:
      if start <= word < end:
        return word - start + base
      return obj if word == OVERLAY_OBJECT else word

    words = struct.unpack(f"<{len(cluster) // 4}I", cluster)
    self.write_bytes(
      base, struct.pack(f"<{len(words)}I", *(relocate(w) for w in words))
    )
    self.write_bytes(obj + OVERLAY_WORDS_OFFSET, struct.pack(
      f"<{len(OVERLAY_WORDS)}I", *(relocate(w) for w in OVERLAY_WORDS)
    ))
    if self.call(POST_LOAD, [obj]) is None:
      return False
    self.write_bytes(self.state + STATE_PACE, struct.pack(
      "<ff", PACE, DEAD_ZONE
    ))
    self.write_bytes(self.state + STATE_START_CLIP, struct.pack(
      "<fff", START_CLIP - 1.5 * FRAME, LOOP_CLIP - 1.5 * FRAME,
      END_CLIP - 1.5 * FRAME
    ))
    self.overlay = obj
    self.logger.debug(f"Hypnosis overlay object at {obj:#x}, data at {base:#x}")
    return True

  def setup_bank(self) -> bool:
    """Loads the hypnosis sound's bank into the sound driver for the trap.
    The handle lives in the cave's state block, which outlives the client,
    and the cave unloads it at the next level bank swap if the trap never
    did (build/cave.s hypno_level_unload)."""
    if self.bank_refused or self.loaded_bank():
      return True
    bank = decode(BANK)
    if self.bank_buffer is None:
      self.bank_buffer = self.claim(len(bank))
      if self.bank_buffer is None:
        return False
      self.write_bytes(self.bank_buffer, bank)
    handle = self.call(CAVE_HYPNOSIS_BANK_LOAD, [self.bank_buffer])
    if handle is None or handle == BANK_BUSY:
      return False
    if handle == 0xFFFFFFFF:
      self.logger.warning("The sound driver refused the hypnosis sound bank")
      self.bank_refused = True
      return True
    self.write32(self.state + STATE_BANK, handle)
    self.logger.debug(f"Hypnosis sound bank loaded, handle {handle:#x}")
    return True

  def loaded_bank(self) -> int:
    self.interface.invalidate(self.state + STATE_BANK, 4)
    return self.read32(self.state + STATE_BANK)

  def unload_bank(self) -> None:
    bank = self.loaded_bank()
    if bank:
      self.write32(self.state + STATE_BANK, 0)
      self.call(SOUND_UNLOAD, [bank])
      self.logger.debug(f"Hypnosis sound bank {bank:#x} unloaded")

  def play_sound(self) -> None:
    bank = self.loaded_bank()
    if not bank:
      return
    params = self.state + STATE_PARAMS
    block = bytearray(PARAMS_SIZE)
    struct.pack_into("<I", block, 0, bank)
    struct.pack_into("<I", block, 0x28, 3)
    self.write_bytes(params, bytes(block))
    self.write32(self.state + STATE_VOICE, 0)
    self.call(
      SOUND_PLAY, [params, CAVE_HYPNOSIS_VOICE_CB, self.state + STATE_VOICE]
    )

  def stop_sound(self) -> None:
    self.interface.invalidate(self.state + STATE_VOICE, 4)
    voice = self.read32(self.state + STATE_VOICE)
    if voice:
      self.call(SOUND_STOP, [voice])
      self.write32(self.state + STATE_VOICE, 0)

  # =====================================================
  # The character
  # =====================================================

  def setup_character(
    self, entity: int, character_id: int
  ) -> Optional[Character]:
    walk = WALKS[character_id]
    swaps = self.build_walk(entity, character_id)
    if swaps is None:
      return None
    eyes = self.eye_entries(entity) or self.build_eyes(entity, walk)
    if eyes is None:
      return None
    return Character(
      entity, walk, swaps, eyes, self.offset_slots(entity, walk),
      self.front_children(entity, walk)
    )

  def build_walk(
    self, entity: int, character_id: int
  ) -> Optional[list[tuple[int, int, int]]]:
    """Lays out a keyed or constant controller per walk blend channel and
    source, from the baked poses; returns the blend's source slots with
    their current and new controllers"""
    walk = WALKS[character_id]
    blend = self.read32(entity + walk.blend)
    count = self.read32(blend + 0x5C)
    table = self.read32(blend + 0x60)
    rows = self.read_many([table + 4*i for i in range(2 * count)])
    values = decode(WALK_VALUES[character_id])
    floats = struct.unpack(f"<{len(values) // 4}f", values)
    pieces: list[tuple[int, bytes | tuple[int, int]]] = []
    layout: list[tuple[int, list[int]]] = []
    size = 0

    def add(length: int) -> int:
      nonlocal size
      offset = size
      size = align(size + length)
      return offset

    for i in range(count):
      word, controller = rows[2*i], rows[2*i + 1]
      element = (word >> 20) & 0xFF
      channel = walk.channels.get(element)
      if word >> 28 or channel is None:
        continue
      _, offset, keyed = channel
      sources = []
      for duration in walk.durations:
        if keyed:
          poses = [
            (floats[offset + 3*k], floats[offset + 3*k + 1],
             floats[offset + 3*k + 2])
            for k in range(PHASES)
          ]
          data = keys(poses, duration, element in walk.rotations)
          key_offset = add(len(data))
          pieces.append((key_offset, data))
          header = add(16)
          pieces.append((header, (len(poses) + 1, key_offset)))
          sources.append(header)
        else:
          constant = add(16)
          pieces.append((constant, struct.pack(
            "<Ifff", CONSTANT_CONTROLLER, *floats[offset:offset + 3]
          )))
          sources.append(constant)
      layout.append((controller, sources))
    base = self.claim(size)
    if base is None:
      return None
    blob = bytearray(size)
    for offset, piece in pieces:
      if isinstance(piece, tuple):
        piece = struct.pack(
          "<IIII", KEYED_CONTROLLER, piece[0], base + piece[1], 0
        )
      blob[offset:offset + len(piece)] = piece
    self.write_bytes(base, bytes(blob))
    slots = [c + o for c, _ in layout for o in (0x20, 0x24)]
    current = self.read_many(slots)
    swaps = [
      (slot, old, base + source)
      for (_, sources), k in zip(layout, range(0, len(slots), 2))
      for slot, old, source in zip(slots[k:k + 2], current[k:k + 2], sources)
    ]
    self.logger.debug(
      f"Hypnosis walk for entity {entity:#x}: {len(layout)} channels, "
      f"{size:#x} bytes at {base:#x}"
    )
    return swaps

  def eye_entries(self, entity: int) -> list[int]:
    count = self.read32(entity + ENTITY_PART_COUNT)
    parts = self.read32(entity + ENTITY_PARTS)
    ids = self.read_many([parts + PART_SIZE*i for i in range(count)])
    wanted = {part.part_id for part in EYES}
    return [
      parts + PART_SIZE*i for i, part_id in enumerate(ids) if part_id in wanted
    ]

  def build_eyes(
    self, entity: int, walk: HypnosisWalk
  ) -> Optional[list[int]]:
    """Appends Sly's spiral eye parts, hidden, to the entity's model: the
    part arrays grow by two in claimed heap, the parts' projection and
    texture are rebound to this map's"""
    count, records, parts, bounds, joints = self.read_many([
      entity + ENTITY_PART_COUNT, entity + ENTITY_RECORDS,
      entity + ENTITY_PARTS, entity + ENTITY_BOUNDS, entity + ENTITY_JOINTS
    ])
    entries = [
      struct.unpack("<10I", self.read_bytes(parts + PART_SIZE*i, PART_SIZE))
      for i in range(count)
    ]
    material_base = next(
      ((e[4] - e[5]) & 0xFFFFFFFF for e in entries if e[5]), None
    )
    sub_object = (
      next((e[8] for e in entries if e[8]), 0) if walk.eye_sub_object else 0
    )
    target = None
    for entry in entries:
      tags = dma_tags(self.read_bytes(entry[4], 0x200))
      for _, tag_id, qwc, address in tags:
        if tag_id in (3, 4):
          target = projection_block(self.read_bytes(address, qwc * 16))
          if target:
            break
      if target:
        break
    resident = self.interface.loot_installer.resident_records()
    texture = resident["tex"].get(EYE_TEXTURE)
    clut = resident["clut"].get(EYE_CLUT)
    if material_base is None or target is None or not texture or not clut:
      self.logger.warning(
        "The character's model lacks what the spiral eyes need; "
        "hypnosis without them"
      )
      return []
    data = decode(EYE_DATA)
    cursor = 0
    pieces = []
    for part in EYES:
      main = data[cursor:cursor + part.main]
      cursor += part.main
      refs = []
      for n in part.refs:
        refs.append(data[cursor:cursor + n])
        cursor += n
      pieces.append((main, refs))
    total = count + len(EYES)
    size = (
      align(total * PART_SIZE) + align(total * RECORD_SIZE) +
      align(total * BOUNDS_SIZE) +
      sum(
        align(len(m)) + sum(align(len(r)) for r in refs) for m, refs in pieces
      )
    )
    base = self.claim(size)
    if base is None:
      return None
    new_parts = base
    new_records = new_parts + align(total * PART_SIZE)
    new_bounds = new_records + align(total * RECORD_SIZE)
    address = new_bounds + align(total * BOUNDS_SIZE)
    tbp = texture[8] & 0x3FFF
    cbp = (clut[7] >> 5) & 0x3FFF
    new_entries = b""
    new_record_data = b""
    new_bound_data = b""
    for part, (main, raw_refs) in zip(EYES, pieces):
      source = projection_block(raw_refs[0])
      assert source
      buffers = []
      for k, raw in enumerate(raw_refs):
        buffer = bytearray(rebase_projection(raw, source, target))
        if k == 0:
          for offset in tex0_offsets(raw):
            low, high = struct.unpack_from("<2I", buffer, offset)
            struct.pack_into(
              "<2I", buffer, offset, (low & ~0x3FFF) | tbp,
              (high & ~(0x3FFF << 5)) | (cbp << 5)
            )
        self.write_bytes(address, bytes(buffer))
        buffers.append(address)
        address += align(len(raw))
      chain = bytearray(main)
      refs = iter(buffers)
      for offset, tag_id, _, _ in dma_tags(main):
        if tag_id in (3, 4):
          struct.pack_into("<I", chain, offset + 4, next(refs))
      self.write_bytes(address, bytes(chain))
      flags = (
        part.flags if walk.eye_flags is None
        else walk.eye_flags | (part.flags & 0xFF)
      ) | HIDDEN_FLAG
      new_entries += struct.pack(
        "<10I", part.part_id,
        joints + ELEMENT_SIZE * walk.eye_joints[part.joint], 0, flags,
        address, (address - material_base) & 0xFFFFFFFF, 0, 0, sub_object, 0
      )
      new_record_data += struct.pack("<5I", *part.record)
      new_bound_data += part.bounds
      address += align(len(main))
    self.write_bytes(
      new_parts, self.read_bytes(parts, count * PART_SIZE) + new_entries
    )
    self.write_bytes(
      new_records,
      self.read_bytes(records, count * RECORD_SIZE) + new_record_data
    )
    self.write_bytes(
      new_bounds, self.read_bytes(bounds, count * BOUNDS_SIZE) + new_bound_data
    )
    self.write_many([
      (entity + ENTITY_RECORDS, new_records),
      (entity + ENTITY_PARTS, new_parts),
      (entity + ENTITY_BOUNDS, new_bounds),
      (entity + ENTITY_PART_COUNT, total)
    ])
    self.logger.debug(
      f"Spiral eyes appended to entity {entity:#x} at {base:#x} "
      f"(texture block {tbp:#x}, CLUT block {cbp:#x})"
    )
    return [new_parts + PART_SIZE*i for i in range(count, total)]

  def offset_slots(
    self, entity: int, walk: HypnosisWalk
  ) -> dict[int, tuple[float, float, float]]:
    joints = self.read32(entity + ENTITY_JOINTS)
    return {
      joints + ELEMENT_SIZE*element + 0x30: offset
      for element, offset in walk.offsets.items()
    }

  def front_children(self, entity: int, walk: HypnosisWalk) -> list[int]:
    if not walk.front_children:
      return []
    found = []
    child = self.read32(entity + ENTITY_FIRST_CHILD)
    for _ in range(1000):
      if not child:
        break
      if self.read32(child + ENTITY_OBJECT_ID) in walk.front_children:
        found.append(child)
      child = self.read32(child + ENTITY_NEXT_SIBLING)
    return found

  def write_offsets(
    self, slots: dict[int, tuple[float, float, float]], on: bool
  ) -> None:
    for address, offset in slots.items():
      self.write_bytes(
        address, struct.pack("<3f", *(offset if on else (0.0, 0.0, 0.0)))
      )

  # =====================================================
  # On and off
  # =====================================================

  def switch_on(self, character: Character) -> None:
    operations = [(slot, new) for slot, _, new in character.swaps]
    flags = self.read_many(
      [entry + 0xC for entry in character.eyes] +
      [e + ENTITY_DRAW_FLAGS for e in [character.entity] + character.front]
    )
    for entry, word in zip(character.eyes, flags):
      operations.append((entry + 0xC, word & ~HIDDEN_FLAG))
    for e, word in zip(
      [character.entity] + character.front, flags[len(character.eyes):]
    ):
      operations.append((e + ENTITY_DRAW_FLAGS, word | DRAW_IN_FRONT))
    self.write_many(operations)
    self.write_offsets(character.offsets, True)
    assert self.overlay is not None
    self.call(OVERLAY_ON, [self.overlay, -1])
    self.play_sound()
    self.write_many([
      (self.state + STATE_PACE_ON, 1), (self.state + STATE_MASK, PAD_MASK),
      (self.state + STATE_OVERLAY, self.overlay)
    ])
    self.active = character
    self.logger.debug(f"Hypnosis on for entity {character.entity:#x}")

  def switch_off(self, character: Character) -> None:
    self.write_many([
      (self.state + STATE_PACE_ON, 0), (self.state + STATE_MASK, 0)
    ])
    if self.overlay is not None:
      self.call(OVERLAY_OFF, [self.overlay])
    self.stop_sound()
    self.unload_bank()
    operations = [(slot, old) for slot, old, _ in character.swaps]
    flags = self.read_many(
      [entry + 0xC for entry in character.eyes] +
      [e + ENTITY_DRAW_FLAGS for e in [character.entity] + character.front]
    )
    for entry, word in zip(character.eyes, flags):
      operations.append((entry + 0xC, word | HIDDEN_FLAG))
    for e, word in zip(
      [character.entity] + character.front, flags[len(character.eyes):]
    ):
      operations.append((e + ENTITY_DRAW_FLAGS, word & ~DRAW_IN_FRONT))
    self.write_many(operations)
    self.write_offsets(character.offsets, False)
    self.logger.debug(f"Hypnosis off for entity {character.entity:#x}")
