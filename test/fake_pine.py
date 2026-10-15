import struct

from ..data.Constants import (
  ADDRESSES,
  CAVE_HEAP_ALLOC,
  CAVE_HOOK_ORIG,
  CAVE_HOOK_ORIG_WORD,
)
from ..pcsx2_interface.pine import Pine


class FakePine(Pine):
  """In-memory stand-in for PINE, modeling a booted game. Untouched memory
  reads as zero; every write is also appended to `writes` as (kind, address,
  bytes). `reads` counts single-value reads and `batches` batch requests
  (each one round trip)."""

  def __init__(self, game_id: str = "SCUS-97316") -> None:
    self.game_id = game_id
    self.connected = True
    self.memory: dict[int, int] = {}
    self.writes: list[tuple[str, int, bytes]] = []
    self.reads = 0
    self.batches = 0
    self.serve_cave_calls = True
    if game_id in ADDRESSES:
      self.poke32(CAVE_HOOK_ORIG, CAVE_HOOK_ORIG_WORD)

  def connect(self) -> None:
    self.connected = True

  def disconnect(self) -> None:
    self.connected = False

  def is_connected(self) -> bool:
    return self.connected

  def get_game_id(self) -> str:
    return self.game_id

  def peek_bytes(self, address: int, n: int) -> bytes:
    return bytes(self.memory.get(address + i, 0) for i in range(n))

  def peek8(self, address: int) -> int:
    return self.peek_bytes(address, 1)[0]

  def peek16(self, address: int) -> int:
    return int.from_bytes(self.peek_bytes(address, 2), "little")

  def peek32(self, address: int) -> int:
    return int.from_bytes(self.peek_bytes(address, 4), "little")

  def peek_float(self, address: int) -> float:
    return struct.unpack("<f", self.peek_bytes(address, 4))[0]

  def peek_cstring(self, address: int, max_length: int = 256) -> bytes:
    data = self.peek_bytes(address, max_length)
    return data.split(b"\0", 1)[0]

  def poke_bytes(self, address: int, data: bytes) -> None:
    for i, byte in enumerate(data):
      self.memory[address + i] = byte

  def poke8(self, address: int, value: int) -> None:
    self.poke_bytes(address, value.to_bytes(1, "little"))

  def poke16(self, address: int, value: int) -> None:
    self.poke_bytes(address, value.to_bytes(2, "little"))

  def poke32(self, address: int, value: int) -> None:
    self.poke_bytes(address, (value & 0xFFFF_FFFF).to_bytes(4, "little"))

  def poke_float(self, address: int, value: float) -> None:
    self.poke_bytes(address, struct.pack("<f", value))

  def written(self, address: int) -> bool:
    return any(
      a <= address < a + len(data) for _, a, data in self.writes
    )

  def clear_writes(self) -> None:
    self.writes.clear()

  def clear_counts(self) -> None:
    self.reads = 0
    self.batches = 0
    self.clear_writes()

  def _record(self, kind: str, address: int, data: bytes) -> None:
    self.writes.append((kind, address, data))
    self.poke_bytes(address, data)
    self._service_cave_call(address)

  def _service_cave_call(self, address: int) -> None:
    """Models the cave servicing a heap_alloc call the moment its function
    word is armed, like the game thread would next frame."""
    if not self.serve_cave_calls or self.game_id not in ADDRESSES:
      return
    slot = ADDRESSES[self.game_id]["cave call"]
    if address != slot or self.peek32(slot) != CAVE_HEAP_ALLOC:
      return
    bottom = ADDRESSES[self.game_id]["heap bottom"]
    claim = (self.peek32(bottom) + 15) & ~15
    self.poke32(bottom, claim + self.peek32(slot + 4))
    self.poke32(slot + 0x14, claim)
    self.poke32(slot, 0)
    self.poke32(slot + 0x18, self.peek32(slot + 0x18) + 1)

  def read_int8(self, address: int) -> int:
    self.reads += 1
    return self.peek8(address)

  def read_int16(self, address: int) -> int:
    self.reads += 1
    return self.peek16(address)

  def read_int32(self, address: int) -> int:
    self.reads += 1
    return self.peek32(address)

  def read_bytes(self, address: int, length: int) -> bytes:
    self.reads += 1
    return self.peek_bytes(address, length)

  def batch_read(self, reads: list[tuple[Pine.DataSize, int]]) -> list[int]:
    self.batches += 1
    return [
      int.from_bytes(self.peek_bytes(address, size), "little")
      for size, address in reads
    ]

  def write_int8(self, address: int, value: int) -> None:
    self._record("w8", address, value.to_bytes(1, "little"))

  def write_int16(self, address: int, value: int) -> None:
    self._record("w16", address, value.to_bytes(2, "little"))

  def write_int32(self, address: int, value: int) -> None:
    self._record("w32", address, value.to_bytes(4, "little"))

  def write_float(self, address: int, value: float) -> None:
    self._record("wfloat", address, struct.pack("<f", value))

  def write_bytes(self, address: int, data: bytes) -> None:
    self._record("wbytes", address, data)

  def batch_write_int32(self, operations: list[tuple[int, int]]) -> None:
    for address, value in operations:
      self._record("bw32", address, value.to_bytes(4, "little"))

  def batch_write_float(self, operations: list[tuple[int, float]]) -> None:
    for address, value in operations:
      self._record("bwfloat", address, struct.pack("<f", value))

  def batch_write(
    self, writes: list[tuple[Pine.DataSize, int, bytes]]
  ) -> None:
    for size, address, data in writes:
      self._record(f"bw{size*8}", address, data)
