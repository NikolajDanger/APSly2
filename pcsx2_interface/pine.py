"""
The PINE API.
This is the client side implementation of the PINE protocol.
It allows for a three-way communication between the emulated game, the
emulator and an external tool, using the external tool as a relay for all
communication. It is a socket based IPC that is _very_ fast.

If you want to draw comparisons you can think of this as an equivalent of the
BizHawk LUA API, although with the logic out of the core and in an external
tool. While BizHawk would run a lua script at each frame in the core of the
emulator we opt instead to keep the entire logic out of the emulator to make it
more easily extensible, more portable, require less code and be more
performant.
"""
import os
import struct
from enum import IntEnum
from platform import system
import socket


DEFAULT_SLOT = 28011


class PineConnectionError(ConnectionError):
  """The PINE socket could not be opened."""


class DuplicateConnectionError(PineConnectionError):
  """The socket opened but PCSX2 did not answer, which is what happens when
  another PINE client already holds the slot."""


class Pine:
  """
  Exposes PS2 memory within a running instance of the PCSX2 emulator using the
  Pine IPC Protocol.
  """

  """
  Maximum memory used by an IPC message request. Equivalent to 50,000 Write64
  requests.
  """
  MAX_IPC_SIZE: int = 650000

  """
  Maximum memory used by an IPC message reply. Equivalent to 50,000 Read64
  replies.
  """
  MAX_IPC_RETURN_SIZE: int = 450000

  """ Maximum number of commands sent in a batch message. """
  MAX_BATCH_REPLY_COUNT: int = 50000

  class IPCResult(IntEnum):
    """
    IPC result codes. A list of possible result codes the IPC can send back.
    Each one of them is what we call an "opcode" or "tag" and is the first
    byte sent by the IPC to differentiate between results.
    """
    IPC_OK = 0  # IPC command successfully completed.
    IPC_FAIL = 0xFF  # IPC command failed to complete.

  class IPCCommand(IntEnum):
    READ8 = 0
    READ16 = 1
    READ32 = 2
    READ64 = 3
    WRITE8 = 4
    WRITE16 = 5
    WRITE32 = 6
    WRITE64 = 7
    VERSION = 8
    SAVE_STATE = 9
    LOAD_STATE = 0xA
    TITLE = 0xB
    ID = 0xC
    UUID = 0xD
    GAME_VERSION = 0xE
    STATUS = 0xF
    UNIMPLEMENTED = 0xFF

  class DataSize(IntEnum):
    INT8 = 1
    INT16 = 2
    INT32 = 4
    INT64 = 8

  class EmuStatus(IntEnum):
    RUNNING = 0
    PAUSED = 1
    SHUTDOWN = 2

  _READ_COMMAND = {
    DataSize.INT8: IPCCommand.READ8,
    DataSize.INT16: IPCCommand.READ16,
    DataSize.INT32: IPCCommand.READ32,
    DataSize.INT64: IPCCommand.READ64,
  }

  _WRITE_COMMAND = {
    DataSize.INT8: IPCCommand.WRITE8,
    DataSize.INT16: IPCCommand.WRITE16,
    DataSize.INT32: IPCCommand.WRITE32,
    DataSize.INT64: IPCCommand.WRITE64,
  }

  def __init__(self, slot: int = DEFAULT_SLOT) -> None:
    self._slot: int = DEFAULT_SLOT
    self.set_slot(slot)
    self._sock: socket.socket = socket.socket()
    self._sock_state: bool = False

  def set_slot(self, slot: int) -> None:
    if not 0 < slot <= 65536:
      raise ValueError("Provided slot number is outside valid range")
    self._slot = slot

  @staticmethod
  def is_wsl() -> bool:
    if system() != "Linux":
      return False
    try:
      with open("/proc/sys/kernel/osrelease", "r") as f:
        return "microsoft" in f.read().lower()
    except OSError:
      return False

  def _socket_address(self) -> tuple[int, str | tuple[str, int]]:
    if self._slot == DEFAULT_SLOT:
      file_name = "pcsx2.sock"
    else:
      file_name = f"pcsx2.sock.{self._slot}"

    if system() == "Windows" or self.is_wsl():
      return socket.AF_INET, ("127.0.0.1", self._slot)
    if system() == "Darwin":
      base = os.environ.get("TMPDIR", "/tmp")
      return socket.AF_UNIX, os.path.join(base, file_name)

    base = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    path = os.path.join(base, file_name)
    # Connecting to a unix socket needs write permission on it; a Flatpak
    # PCSX2 keeps its socket under its own sandboxed runtime dir instead.
    if system() == "Linux" and not os.access(path, os.W_OK):
      path = os.path.join(
        base, ".flatpak/net.pcsx2.PCSX2/xdg-run", file_name
      )
    return socket.AF_UNIX, path

  def _init_socket(self) -> bool:
    family, address = self._socket_address()
    try:
      self._sock = socket.socket(family, socket.SOCK_STREAM)
      self._sock.settimeout(5.0)
      self._sock.connect(address)
    except OSError:
      self._close()
      return False

    self._sock_state = True
    return True

  def _close(self) -> None:
    self._sock.close()
    self._sock_state = False

  def connect(self) -> None:
    if self._sock_state:
      return
    if not self._init_socket():
      raise PineConnectionError("Could not open the PINE socket.")
    # A socket to a slot held by another client opens fine but never gets
    # an answer, so probe once before reporting the connection as up.
    try:
      self.get_emu_status()
    except OSError:
      self._close()
      raise DuplicateConnectionError(
        "PCSX2 did not answer; is another PINE client connected on this slot?"
      )

  def disconnect(self) -> None:
    if self._sock_state:
      self._close()

  def is_connected(self) -> bool:
    return self._sock_state

  def read_int8(self, address: int) -> int:
    return self._read(self.DataSize.INT8, address)

  def read_int16(self, address: int) -> int:
    return self._read(self.DataSize.INT16, address)

  def read_int32(self, address: int) -> int:
    return self._read(self.DataSize.INT32, address)

  def read_int64(self, address: int) -> int:
    return self._read(self.DataSize.INT64, address)

  def _read(self, size: DataSize, address: int) -> int:
    request = self._create_request(self._READ_COMMAND[size], address, 9)
    return self.from_bytes(self._send_request(request)[-size:])

  def read_bytes(self, address: int, length: int) -> bytes:
    # One request with a 5-byte read command per 8 bytes (an opcode and an
    # address), plus a 4/2/1-byte tail. The commands are filled in column by
    # column, which takes the same few slice assignments however many there
    # are, and the reply is exactly the bytes asked for, in order.
    read64 = self._READ_COMMAND[self.DataSize.INT64]
    n8 = length >> 3
    body = bytearray(5 * n8)
    if n8:
      body[0::5] = bytes([read64]) * n8
      addrs = struct.pack("<%dI" % n8, *range(address, address + (n8 << 3), 8))
      for k in range(4):
        body[1 + k::5] = addrs[k::4]
    offset = n8 << 3
    for size in (self.DataSize.INT32, self.DataSize.INT16, self.DataSize.INT8):
      if length - offset >= size:
        body += struct.pack(
          "<BI", self._READ_COMMAND[size], address + offset
        )
        offset += size
    response = self._send_request(
      struct.pack("<I", len(body) + 4) + bytes(body)
    )
    return response[5:5 + length]

  def read_string(self, address: int, max_length: int) -> str:
    data = self.read_bytes(address, max_length)
    return data.split(b'\x00', 1)[0].decode("ascii")

  def write_int8(self, address: int, value: int) -> None:
    self._write(self.DataSize.INT8, address, value.to_bytes(1, "little"))

  def write_int16(self, address: int, value: int) -> None:
    self._write(self.DataSize.INT16, address, value.to_bytes(2, "little"))

  def write_int32(self, address: int, value: int) -> None:
    self._write(self.DataSize.INT32, address, value.to_bytes(4, "little"))

  def write_int64(self, address: int, value: int) -> None:
    self._write(self.DataSize.INT64, address, value.to_bytes(8, "little"))

  def write_float(self, address: int, value: float) -> None:
    self._write(self.DataSize.INT32, address, struct.pack("<f", value))

  def _write(self, size: DataSize, address: int, data: bytes) -> None:
    request = self._create_request(
      self._WRITE_COMMAND[size], address, 9 + size
    )
    self._send_request(request + data)

  def write_bytes(self, address: int, data: bytes) -> None:
    # As read_bytes, but each command is 13 bytes, carrying its 8 data bytes
    # after the address. Those get filled in column by column too.
    write64 = self._WRITE_COMMAND[self.DataSize.INT64]
    length = len(data)
    n8 = length >> 3
    body = bytearray(13 * n8)
    if n8:
      body[0::13] = bytes([write64]) * n8
      addrs = struct.pack("<%dI" % n8, *range(address, address + (n8 << 3), 8))
      for k in range(4):
        body[1 + k::13] = addrs[k::4]
      head = data[:n8 << 3]
      for k in range(8):
        body[5 + k::13] = head[k::8]
    offset = n8 << 3
    for size in (self.DataSize.INT32, self.DataSize.INT16, self.DataSize.INT8):
      if length - offset >= size:
        body += struct.pack(
          "<BI", self._WRITE_COMMAND[size], address + offset
        ) + data[offset:offset + size]
        offset += size
    self._send_request(struct.pack("<I", len(body) + 4) + bytes(body))

  def write_string(self, address: int, value: str) -> None:
    self.write_bytes(address, value.encode("ascii") + b'\x00')

  @classmethod
  def _chunks(cls, address: int, length: int) -> list[tuple[DataSize, int]]:
    # As many 8-byte chunks as fit, then a 4/2/1-byte tail. One
    # comprehension, since a bulk transfer is tens of thousands of chunks.
    n8 = length >> 3
    chunks = [(cls.DataSize.INT64, address + (i << 3)) for i in range(n8)]
    offset = n8 << 3
    for size in (cls.DataSize.INT32, cls.DataSize.INT16, cls.DataSize.INT8):
      if length - offset >= size:
        chunks.append((size, address + offset))
        offset += size
    return chunks

  def batch_read(self, reads: list[tuple[DataSize, int]]) -> list[int]:
    """Read several values of mixed sizes in a single request. Much faster
    than individual reads."""
    if not reads:
      return []

    body = b''
    for size, address in reads:
      body += self.to_bytes(self._READ_COMMAND[size], 1)
      body += self.to_bytes(address, 4)
    response = self._send_request(self.to_bytes(len(body) + 4, 4) + body)

    results = []
    offset = 5
    for size, _ in reads:
      results.append(self.from_bytes(response[offset:offset + size]))
      offset += size
    return results

  def batch_write(self, writes: list[tuple[DataSize, int, bytes]]) -> None:
    """Write several values of mixed sizes in a single request. Each entry
    is (size, address, little-endian data of that size)."""
    if not writes:
      return

    body = b''
    for size, address, data in writes:
      body += self.to_bytes(self._WRITE_COMMAND[size], 1)
      body += self.to_bytes(address, 4)
      body += data
    self._send_request(self.to_bytes(len(body) + 4, 4) + body)

  def batch_read_int8(self, addresses: list[int]) -> list[int]:
    return self.batch_read([(self.DataSize.INT8, a) for a in addresses])

  def batch_read_int16(self, addresses: list[int]) -> list[int]:
    return self.batch_read([(self.DataSize.INT16, a) for a in addresses])

  def batch_read_int32(self, addresses: list[int]) -> list[int]:
    return self.batch_read([(self.DataSize.INT32, a) for a in addresses])

  def batch_write_int32(self, operations: list[tuple[int, int]]) -> None:
    self.batch_write([
      (self.DataSize.INT32, address, value.to_bytes(4, "little"))
      for address, value in operations
    ])

  def batch_write_float(self, operations: list[tuple[int, float]]) -> None:
    self.batch_write([
      (self.DataSize.INT32, address, struct.pack("<f", value))
      for address, value in operations
    ])

  def get_game_id(self) -> str:
    request = self.to_bytes(5, 4) + self.to_bytes(self.IPCCommand.ID, 1)
    try:
      response = self._send_request(request)
    except ConnectionError:
      return ""
    return response[9:-1].decode("ascii")

  def save_state(self, slot: int) -> None:
    self._send_request(self._state_request(self.IPCCommand.SAVE_STATE, slot))

  def load_state(self, slot: int) -> None:
    self._send_request(self._state_request(self.IPCCommand.LOAD_STATE, slot))

  @classmethod
  def _state_request(cls, command: IPCCommand, slot: int) -> bytes:
    if not 0 <= slot <= 255:
      raise ValueError("Savestate slot must be in 0..255")
    return cls.to_bytes(6, 4) + cls.to_bytes(command, 1) + cls.to_bytes(slot, 1)

  def get_emu_status(self) -> EmuStatus:
    request = self.to_bytes(5, 4) + self.to_bytes(self.IPCCommand.STATUS, 1)
    response = self._send_request(request)
    return self.EmuStatus(self.from_bytes(response[-4:]))

  def _send_request(self, request: bytes) -> bytes:
    if not self._sock_state:
      self._init_socket()

    try:
      self._sock.sendall(request)
    except OSError:
      self._close()
      raise ConnectionError("Lost connection to PCSX2.")

    end_length = 4
    result: bytes = b''
    while len(result) < end_length:
      try:
        response = self._sock.recv(4096)
      except TimeoutError:
        raise TimeoutError(
          "Response timed out. "
          "This might be caused by having two PINE connections open on the "
          "same slot"
        )

      if len(response) <= 0:
        result = b''
        break

      result += response

      if end_length == 4 and len(response) >= 4:
        end_length = self.from_bytes(result[0:4])
        if end_length > self.MAX_IPC_SIZE:
          result = b''
          break

    if len(result) == 0:
      raise ConnectionError("Invalid response from PCSX2.")
    if result[4] == self.IPCResult.IPC_FAIL:
      raise ConnectionError("Failure indicated in PCSX2 response.")

    return result

  @classmethod
  def _create_request(
    cls, command: IPCCommand, address: int, size: int = 0
  ) -> bytes:
    ipc = cls.to_bytes(size, 4)
    ipc += cls.to_bytes(command, 1)
    ipc += cls.to_bytes(address, 4)
    return ipc

  @staticmethod
  def to_bytes(value: int, size: int) -> bytes:
    return value.to_bytes(length=size, byteorder="little")

  @staticmethod
  def from_bytes(arr: bytes) -> int:
    return int.from_bytes(arr, byteorder="little")
