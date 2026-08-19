import struct

from ..pcsx2_interface.pine import Pine


class FakePine(Pine):
  """In-memory stand-in for PINE. Untouched memory reads as zero; every write
  is also appended to `writes` as (kind, address, bytes)."""

  def __init__(self, game_id: str = "SCUS-97316") -> None:
    self.game_id = game_id
    self.connected = True
    self.memory: dict[int, int] = {}
    self.writes: list[tuple[str, int, bytes]] = []

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

  def _record(self, kind: str, address: int, data: bytes) -> None:
    self.writes.append((kind, address, data))
    self.poke_bytes(address, data)

  def read_int8(self, address: int) -> int:
    return self.peek8(address)

  def read_int16(self, address: int) -> int:
    return self.peek16(address)

  def read_int32(self, address: int) -> int:
    return self.peek32(address)

  def read_bytes(self, address: int, length: int) -> bytes:
    return self.peek_bytes(address, length)

  def batch_read_int8(self, addresses: list[int]) -> list[int]:
    return [self.peek8(a) for a in addresses]

  def batch_read_int16(self, addresses: list[int]) -> list[int]:
    return [self.peek16(a) for a in addresses]

  def batch_read_int32(self, addresses: list[int]) -> list[int]:
    return [self.peek32(a) for a in addresses]

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
