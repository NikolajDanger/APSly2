import struct
import unittest

from ..pcsx2_interface.pine import Pine

OK = bytes([0])


class RecordingPine(Pine):
  """Records the requests that would go over the socket and answers each
  with the queued reply (or a bare IPC_OK)."""

  def __init__(self) -> None:
    super().__init__()
    self.requests: list[bytes] = []
    self.replies: list[bytes] = []

  def _send_request(self, request: bytes) -> bytes:
    self.requests.append(request)
    payload = self.replies.pop(0) if self.replies else b""
    body = OK + payload
    return Pine.to_bytes(len(body) + 4, 4) + body


def header(command: int, address: int, size: int) -> bytes:
  return (
    size.to_bytes(4, "little") + bytes([command]) +
    address.to_bytes(4, "little")
  )


class TestPineRequests(unittest.TestCase):
  def setUp(self) -> None:
    self.pine = RecordingPine()
    self.cmd = Pine.IPCCommand

  def test_write_float_carries_payload(self) -> None:
    self.pine.write_float(0x200000, 1.5)
    self.assertEqual(
      self.pine.requests,
      [header(self.cmd.WRITE32, 0x200000, 13) + struct.pack("<f", 1.5)]
    )

  def test_write_ints(self) -> None:
    self.pine.write_int8(0x200000, 0xAB)
    self.pine.write_int16(0x200000, 0xBEEF)
    self.pine.write_int32(0x200000, 0x11223344)
    self.assertEqual(self.pine.requests, [
      header(self.cmd.WRITE8, 0x200000, 10) + b"\xab",
      header(self.cmd.WRITE16, 0x200000, 11) + b"\xef\xbe",
      header(self.cmd.WRITE32, 0x200000, 13) + b"\x44\x33\x22\x11",
    ])

  def test_write_bytes_batches_largest_sizes(self) -> None:
    self.pine.write_bytes(0x200000, bytes(range(11)))
    body = (
      bytes([self.cmd.WRITE64]) + (0x200000).to_bytes(4, "little") +
      bytes(range(8)) +
      bytes([self.cmd.WRITE16]) + (0x200008).to_bytes(4, "little") +
      bytes([8, 9]) +
      bytes([self.cmd.WRITE8]) + (0x20000A).to_bytes(4, "little") +
      bytes([10])
    )
    self.assertEqual(
      self.pine.requests, [(len(body) + 4).to_bytes(4, "little") + body]
    )

  def test_read_bytes_batches_largest_sizes(self) -> None:
    self.pine.replies = [bytes(range(11))]
    self.assertEqual(self.pine.read_bytes(0x200000, 11), bytes(range(11)))
    body = (
      bytes([self.cmd.READ64]) + (0x200000).to_bytes(4, "little") +
      bytes([self.cmd.READ16]) + (0x200008).to_bytes(4, "little") +
      bytes([self.cmd.READ8]) + (0x20000A).to_bytes(4, "little")
    )
    self.assertEqual(
      self.pine.requests, [(len(body) + 4).to_bytes(4, "little") + body]
    )

  def test_reads_decode_little_endian(self) -> None:
    self.pine.replies = [b"\x44\x33\x22\x11", b"\xff"]
    self.assertEqual(self.pine.read_int32(0x200000), 0x11223344)
    self.assertEqual(self.pine.read_int8(0x200000), 0xFF)
    self.assertEqual(self.pine.requests, [
      header(self.cmd.READ32, 0x200000, 9),
      header(self.cmd.READ8, 0x200000, 9),
    ])

  def test_batch_read(self) -> None:
    self.pine.replies = [b"\x01\x00\x00\x00\x02\x00"]
    values = self.pine.batch_read(
      [(Pine.DataSize.INT32, 0x200000), (Pine.DataSize.INT16, 0x200010)]
    )
    self.assertEqual(values, [1, 2])
    body = (
      bytes([self.cmd.READ32]) + (0x200000).to_bytes(4, "little") +
      bytes([self.cmd.READ16]) + (0x200010).to_bytes(4, "little")
    )
    self.assertEqual(
      self.pine.requests, [(len(body) + 4).to_bytes(4, "little") + body]
    )
    self.assertEqual(self.pine.batch_read([]), [])

  def test_batch_write(self) -> None:
    self.pine.batch_write_int32([(0x200000, 7)])
    self.pine.batch_write_float([(0x200004, 0.5)])
    self.pine.batch_write([])
    expected = []
    for address, data in [
      (0x200000, (7).to_bytes(4, "little")),
      (0x200004, struct.pack("<f", 0.5))
    ]:
      body = bytes([self.cmd.WRITE32]) + address.to_bytes(4, "little") + data
      expected.append((len(body) + 4).to_bytes(4, "little") + body)
    self.assertEqual(self.pine.requests, expected)

  def test_game_id(self) -> None:
    self.pine.replies = [(11).to_bytes(4, "little") + b"SCUS-97316\0"]
    self.assertEqual(self.pine.get_game_id(), "SCUS-97316")
    self.assertEqual(
      self.pine.requests, [(5).to_bytes(4, "little") + bytes([self.cmd.ID])]
    )

  def test_state_commands(self) -> None:
    self.pine.save_state(9)
    self.pine.load_state(9)
    self.assertEqual(self.pine.requests, [
      (6).to_bytes(4, "little") + bytes([self.cmd.SAVE_STATE, 9]),
      (6).to_bytes(4, "little") + bytes([self.cmd.LOAD_STATE, 9]),
    ])
    with self.assertRaises(ValueError):
      self.pine.load_state(256)
