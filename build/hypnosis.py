"""Builds data/Hypnosis.py, the Hypnosis trap's ported assets, from PCSX2
savestates of SCUS-97316 and the disc image. The Contessa's hypnosis is
episode 5 level data (the screen overlay, its sound, Sly's spiral eyes and
his hypnotized walk), so the trap carries copies that HypnosisInstall
rebuilds in whatever map it fires in. From an Archipelago checkout:

  python -m worlds.Sly2.build.hypnosis FIGHT SLY BENTLEY MURRAY CAPTURE ISO
      [output]

  FIGHT    savestate in the Contessa fight, part 1 (ep 5, map 17): the
           overlay object and its animation data.
  SLY      savestate in the ep 5 hub as Sly: the spiral eye parts and his
           walk blend's channels.
  BENTLEY  savestate in the ep 5 hub as Bentley: his rig and walk blend.
  MURRAY   savestate in the ep 5 hub as Murray: his rig and walk blend.
  CAPTURE  Sly's hypnotized walk as an .npz of per-frame joint arrays `F`
           [frames, joints, 64 words] and clip times `tclip`, sampled
           over PINE in the ep 5 hub (2026-10-22). Bentley's and Murray's
           walks are retargeted from it by aiming their torso and arm
           joints along Sly's and planting their feet from his foot
           offsets.
  ISO      the disc image, for the one-sound bank cut from ep 5's bank.
"""

import base64
import struct
import sys
import zipfile
import zlib
from typing import Iterator

import numpy as np

from worlds.Sly2.build.loot_models import extract_part

ACTIVE_CHARACTER = 0x2DE2F0
CHARACTER_ID = 0x3D4A6C
# The overlay state machine's object in the fight, and the cluster of
# animation data it points into (self-contained but for the game's globals).
OVERLAY_OBJECT = 0x10E4350
OVERLAY_CLUSTER = (0x10E4460, 0x10EBAF0)
OVERLAY_WORDS = (0x50, 0xCC)
EYE_PART_IDS = (0x10BF, 0x10BA)
# The hypnosis sound, which the loop clip's keys play and stop through the
# level bank; the trap plays it from its own bank instead.
HYPNOSIS_SOUND_ID = 0x20C
# Episode 5's sound bank on the disc (its container header), and the
# hypnosis sound's index in it.
BANK_OFFSET = 0x45320000
HYPNOSIS_SOUND = 349
PHASES = 80
ELEMENT_SIZE = 0x100
ROTATION, TRANSLATION = 6, 1
# Walk blend slot on the character and its two sources' clip lengths
# (sneak, walk), per character id.
BLENDS = {
  7: (0x1C34, (4/3, 2/3)),
  8: (0x1604, (4/3, 1/3)),
  9: (0x1544, (4/3, 0.5)),
}


class Dump:
  """EE memory from a savestate"""
  def __init__(self, path: str) -> None:
    self.memory = zipfile.ZipFile(path).read("eeMemory.bin")

  def read_int32(self, address: int) -> int:
    return struct.unpack_from("<I", self.memory, address & 0x1FFFFFF)[0]

  def read_float(self, address: int) -> float:
    return struct.unpack_from("<f", self.memory, address & 0x1FFFFFF)[0]

  def read_bytes(self, address: int, n: int) -> bytes:
    address &= 0x1FFFFFF
    return self.memory[address:address + n]


def encode(data: bytes) -> str:
  return base64.b85encode(zlib.compress(data, 9)).decode("ascii")


def literal(text: str, indent: int) -> str:
  width = 76 - indent
  chunks = [text[i:i + width] for i in range(0, len(text), width)]
  pad = " " * indent
  body = "\n".join(f'{pad}"{chunk}"' for chunk in chunks)
  return f"(\n{body}\n{pad[:-2]})"


# =====================================================
# Overlay and sound
# =====================================================


def overlay(dump: Dump) -> tuple[bytes, list[int]]:
  """The overlay's animation data, with the keys that play and stop the
  hypnosis sound through the level bank disarmed (an event is {type, id};
  a key holds its event count at +0x18 and the events at +0x1c)"""
  start, end = OVERLAY_CLUSTER
  words = [
    dump.read_int32(OVERLAY_OBJECT + offset)
    for offset in range(*OVERLAY_WORDS, 4)
  ]
  cluster = bytearray(dump.read_bytes(start, end - start))
  cluster_words = struct.unpack(f"<{len(cluster) // 4}I", cluster)
  events = [
    4 * i for i in range(len(cluster_words) - 1)
    if cluster_words[i] in (0, 1) and cluster_words[i + 1] == HYPNOSIS_SOUND_ID
  ]
  assert len(events) == 2, events
  for event in events:
    keys = [
      4 * i - 0x1C for i, w in enumerate(cluster_words) if w == start + event
    ]
    assert len(keys) == 1, keys
    assert struct.unpack_from("<I", cluster, keys[0] + 0x18)[0] == 1
    struct.pack_into("<I", cluster, keys[0] + 0x18, 0)
  return bytes(cluster), words


def bank(iso: str) -> bytes:
  """Cuts the hypnosis sound into a bank of its own: the sound's record,
  its grains and the one VAG its tones share, in ep 5's bank format"""
  with open(iso, "rb") as f:
    f.seek(BANK_OFFSET)
    header = struct.unpack("<6I", f.read(0x18))
    assert header[:3] == (3, 2, 0x18), header
    b = f.read(header[4] + header[5] - 0x18)
  w = lambda i: struct.unpack_from("<I", b, i)[0]  # noqa: E731
  grain_table, grain_data = w(0x20), w(0x34)
  vag_chunk = header[4] - 0x18
  record = bytearray(b[0x40 + 12*HYPNOSIS_SOUND:0x40 + 12*HYPNOSIS_SOUND + 12])
  count, first = record[4], struct.unpack_from("<i", record, 8)[0]
  grains = []
  tones = bytearray()
  vags: dict[int, int] = {}
  vag_data = bytearray()
  for g in range(count):
    word, delay = struct.unpack_from("<Ii", b, grain_table + first + 8*g)
    kind, offset = word >> 24, word & 0xFFFFFF
    if kind == 1:
      tone = bytearray(b[grain_data + offset:grain_data + offset + 0x18])
      vag = struct.unpack_from("<I", tone, 0x10)[0]
      if vag not in vags:
        a = vag_chunk + vag
        k = 0
        while not (b[a + 16*k + 1] & 1):
          k += 1
        vags[vag] = len(vag_data)
        vag_data += b[a:a + 16*(k + 1)]
      struct.pack_into("<I", tone, 0x10, vags[vag])
      grains.append(((1 << 24) | len(tones), delay))
      tones += tone
    elif kind == 4:
      grains.append(((4 << 24) | len(tones), delay))
      tones += b[grain_data + offset:grain_data + offset + 0x10]
    else:
      assert offset == 0, (kind, offset)
      grains.append((word, delay))
  struct.pack_into("<i", record, 8, 0)
  first_grain = 0x40 + 12
  tone_data = first_grain + 8*len(grains)
  sblk_len = tone_data + len(tones)
  while (0x18 + sblk_len) % 16:
    sblk_len += 1
  header_block = bytearray(b[0:0x40])
  struct.pack_into("<HH", header_block, 0x14, 0, 1)
  struct.pack_into("<HH", header_block, 0x18, len(grains), len(vags))
  struct.pack_into(
    "<IIIIIII", header_block, 0x1C, 0x40, first_grain, 0x5040, len(vag_data),
    len(vag_data), 0, tone_data
  )
  sblk = (
    bytes(header_block) + bytes(record) +
    b"".join(struct.pack("<Ii", x, d) for x, d in grains) + bytes(tones)
  )
  sblk += b"\0" * (sblk_len - len(sblk))
  container = struct.pack(
    "<6I", 3, 2, 0x18, len(sblk), 0x18 + len(sblk), len(vag_data)
  )
  return container + sblk + bytes(vag_data)


# =====================================================
# Spiral eyes
# =====================================================


def eyes(dump: Dump) -> list[dict]:
  entity = dump.read_int32(ACTIVE_CHARACTER)
  count = dump.read_int32(entity + 0xB8)
  parts = dump.read_int32(entity + 0xC0)
  joints = dump.read_int32(entity + 0x54)
  out = []
  for part_id in EYE_PART_IDS:
    index = next(
      i for i in range(count)
      if dump.read_int32(parts + 0x28*i) == part_id
    )
    part = extract_part(dump, entity, index)  # type: ignore[arg-type]
    part["joint"] = (part["entry"][1] - joints) // ELEMENT_SIZE
    part["bounds"] = dump.read_bytes(
      dump.read_int32(entity + 0xC4) + 0x18*index, 0x18
    ).hex()
    out.append(part)
  return out


# =====================================================
# Walks
# =====================================================


class Rig:
  def __init__(self, dump: Dump) -> None:
    entity = dump.read_int32(ACTIVE_CHARACTER)
    self.entity = entity
    self.character = dump.read_int32(CHARACTER_ID)
    self.vtable = dump.read_int32(entity + 0xC)
    joints = dump.read_int32(entity + 0x54)
    self.n = dump.read_int32(entity + 0x50)
    self.parent = []
    self.L0 = []
    self.t0 = []
    self.kind = []
    for e in range(self.n):
      a = joints + ELEMENT_SIZE*e
      self.L0.append(np.array([
        [dump.read_float(a + 16*r + 4*c) for c in range(3)] for r in range(3)
      ]))
      self.t0.append(
        np.array([dump.read_float(a + 0x30 + 4*c) for c in range(3)])
      )
      p = dump.read_int32(a + 0xA0)
      self.parent.append((p - joints) // ELEMENT_SIZE if p else -1)
      self.kind.append(dump.read_int32(a + 0x94))
    slot, self.durations = BLENDS[self.character]
    blend = dump.read_int32(entity + slot)
    table = dump.read_int32(blend + 0x60)
    self.channels = sorted({
      (word >> 20) & 0xFF
      for word in (
        dump.read_int32(table + 8*i)
        for i in range(dump.read_int32(blend + 0x5C))
      )
      if word >> 28 == 0
    })

  def fk(self, L: list, t: list) -> tuple[list, list]:
    W: list = [None] * self.n
    P: list = [None] * self.n
    for e in range(self.n):
      if e <= 2:
        W[e], P[e] = np.eye(3), np.zeros(3)
        continue
      p = self.parent[e]
      W[e] = L[e] @ W[p]
      P[e] = P[p] + t[e] @ W[p]
    return W, P

  def aim(
    self, L: list, t: list, node: int, children: list, d: np.ndarray
  ) -> None:
    W, P = self.fk(L, t)
    current = np.mean([P[c] for c in children], 0) - P[node]
    Q = swing(current, d)
    L[node] = (W[node] @ Q.T) @ np.linalg.inv(W[self.parent[node]])


def swing(a: np.ndarray, b: np.ndarray) -> np.ndarray:
  a = a / np.linalg.norm(a)
  b = b / np.linalg.norm(b)
  v = np.cross(a, b)
  c = float(a @ b)
  if np.linalg.norm(v) < 1e-9:
    return np.eye(3)
  K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
  return np.eye(3) + K + K @ K * (1 / (1 + c))


def polar(W: np.ndarray) -> np.ndarray:
  u, _, vt = np.linalg.svd(W)
  return u @ vt


def to_euler(L: np.ndarray) -> np.ndarray:
  A = L.T
  y = -np.arcsin(np.clip(A[2, 0], -1, 1))
  x = np.arctan2(A[2, 1], A[2, 2])
  z = np.arctan2(A[1, 0], A[0, 0])
  return np.array([x, y, z])


class Capture:
  """Sly's hypnotized walk, folded into PHASES poses of its 4/3 s loop"""
  def __init__(self, path: str) -> None:
    data = np.load(path)
    self.F = data["F"]
    self.phase = np.round(data["tclip"] * 60).astype(int) % PHASES

  def frames(self, phase: int) -> np.ndarray:
    return self.F[self.phase == phase]

  def positions(self) -> np.ndarray:
    """World joint positions per phase in Sly's body frame (+x forward,
    origin at the root node)"""
    P = self.F[:, :, 28:31]
    W = self.F[:, :, [16, 17, 18, 20, 21, 22, 24, 25, 26]]
    W = W.reshape(len(self.F), -1, 3, 3)
    heading = polar(np.median(W[:, 2], axis=0))
    out = []
    for phase in range(PHASES):
      Pm = np.median(P[self.phase == phase], axis=0)
      out.append((Pm - Pm[1]) @ heading.T)
    return np.array(out)

  def locals(self, rig: Rig) -> dict[int, np.ndarray]:
    """Sly's own channels: each element's local rotation (Euler) or
    translation per phase"""
    values = {}
    for e in rig.channels:
      if rig.kind[e] == ROTATION:
        v = []
        for phase in range(PHASES):
          Ls = self.frames(phase)[:, e][:, [0, 1, 2, 4, 5, 6, 8, 9, 10]]
          v.append(to_euler(polar(Ls.reshape(-1, 3, 3).mean(0))))
        values[e] = np.unwrap(np.array(v), axis=0)
      elif rig.kind[e] == TRANSLATION:
        values[e] = np.array([
          np.median(self.frames(phase)[:, e, 12:15], axis=0)
          for phase in range(PHASES)
        ])
    return values

  def eye_rotations(self) -> dict[int, np.ndarray]:
    """Sly's eye joints' world rotation relative to his head, per phase"""
    def world(f: np.ndarray, e: int) -> np.ndarray:
      return f[e, [16, 17, 18, 20, 21, 22, 24, 25, 26]].reshape(3, 3)
    out: dict[int, list] = {82: [], 88: []}
    for phase in range(PHASES):
      frames = self.frames(phase)
      for e in out:
        Rs = [polar(world(f, e)) @ polar(world(f, 73)).T for f in frames]
        out[e].append(polar(np.mean(Rs, 0)))
    return {e: np.array(v) for e, v in out.items()}


class Retarget:
  """How a character's rig follows Sly's walk: (rotation node, its
  children, Sly joint from, Sly joint to) aims; (ankle translate node, its
  parent, Sly hip, Sly foot) legs with the leg length (None: the ankle's
  own rest offset); whether the stance keeps the rest pose's forward
  offset; head node, the eye rotation nodes with the Sly eye joint each
  follows and the head-frame change of basis; the eye scale nodes."""
  def __init__(
    self, aims: list, legs: list, leg_length: float | None, centered: bool,
    head: int, eyes: dict[int, int], basis: np.ndarray, scales: tuple
  ) -> None:
    self.aims = aims
    self.legs = legs
    self.leg_length = leg_length
    self.centered = centered
    self.head = head
    self.eyes = eyes
    self.basis = basis
    self.scales = scales


# Sly head axes (x up, -y face, z side) -> Bentley head axes (z up, x face,
# y side); Murray's head is x left, y face, z down.
RETARGETS = {
  8: Retarget(
    aims=[
      (19, [25], 39, 59), (26, [55], 61, 63),
      (56, [58, 60, 64, 68, 72], 63, 70), (33, [34], 65, 66),
      (36, [37], 65, 66), (41, [43], 68, 69), (45, [48], 68, 69)
    ],
    legs=[(7, 2, 55, 56), (13, 2, 57, 58)], leg_length=37.5, centered=False,
    head=57, eyes={62: 82, 70: 88},
    basis=np.array([[0, 0, 1], [-1, 0, 0], [0, -1, 0]], float),
    scales=(63, 71)
  ),
  9: Retarget(
    aims=[
      (40, [54], 39, 59), (56, [58], 61, 63), (60, [81], 63, 70),
      (64, [66], 68, 69), (68, [69], 68, 69), (109, [111], 65, 66),
      (113, [116], 65, 66)
    ],
    legs=[(32, 31, 57, 58), (35, 31, 55, 56)], leg_length=None, centered=True,
    head=81, eyes={87: 82, 91: 88},
    basis=np.array([[0, 0, -1], [0, -1, 0], [-1, 0, 0]], float),
    scales=(88, 92)
  ),
}
EYE_SCALE = (1.1, 0.35, 1.1)
# Rest offsets of the channel-free joints the eye parts hang from
# (eyebrows), moving the spirals down onto the eyes.
EYE_OFFSETS = {
  7: {},
  8: {61: (0.0, 0.0, -18.0), 69: (0.0, 0.0, -18.0)},
  9: {86: (0.0, 0.0, 12.0), 90: (0.0, 0.0, 12.0)},
}
# Sly's eye parts on each rig: the draw joint for each of Sly's, the flags
# the rig's own parts carry (None: keep the part's) and whether the part's
# word 8 is copied from one of the rig's entries (Sly's sub-object pointer).
EYE_JOINTS = {
  7: ({82: 82, 88: 88}, None, True),
  8: ({82: 63, 88: 71}, 0x01C0E100, False),
  9: ({82: 88, 88: 92}, 0x07C3E100, False),
}
# Children the overlay must not cover, by object id (Sly's cane).
FRONT_CHILDREN = {7: (316, 317), 8: (), 9: ()}


def solve(rig: Rig, S: np.ndarray, rt: Retarget) -> list[tuple[list, list]]:
  _, P0 = rig.fk(rig.L0, rig.t0)
  ankles = [a for a, _, _, _ in rt.legs]
  wy = np.mean([abs(P0[a][1]) for a in ankles])
  hx = np.mean([P0[a][0] for a in ankles]) if not rt.centered else 0.0
  hz = np.mean([P0[a][2] for a in ankles])
  stance = {a: np.array([hx, np.sign(P0[a][1]) * wy, hz]) for a in ankles}
  lengths = {
    a: rt.leg_length if rt.leg_length else float(np.linalg.norm(rig.t0[a]))
    for a in ankles
  }
  foot_mean = {b: S[:, b].mean(0) for _, _, _, b in rt.legs}
  sly_leg = {
    b: float(np.median(np.linalg.norm(S[:, b] - S[:, a], axis=1)))
    for _, _, a, b in rt.legs
  }
  out = []
  for phase in range(PHASES):
    s = S[phase]
    L = [x.copy() for x in rig.L0]
    t = [x.copy() for x in rig.t0]
    for node, children, a, b in rt.aims:
      rig.aim(L, t, node, children, s[b] - s[a])
    W, P = rig.fk(L, t)
    for ankle, hip, _, b in rt.legs:
      offset = (s[b] - foot_mean[b]) * lengths[ankle] / sly_leg[b]
      t[ankle] = (stance[ankle] + offset - P[hip]) @ np.linalg.inv(W[hip])
    out.append((L, t))
  return out


def apply_eyes(
  rig: Rig, solution: list, rt: Retarget, rel: dict[int, np.ndarray]
) -> None:
  for phase, (L, t) in enumerate(solution):
    W, _ = rig.fk(L, t)
    Wh = polar(W[rt.head])
    for node, sly_eye in rt.eyes.items():
      Wt = rel[sly_eye][phase] @ rt.basis @ Wh
      L[node] = Wt @ np.linalg.inv(W[rig.parent[node]])


def channel_values(rig: Rig, solution: list) -> dict[int, np.ndarray]:
  values = {}
  for e in range(rig.n):
    if rig.kind[e] == ROTATION:
      values[e] = np.unwrap(
        np.array([to_euler(solution[k][0][e]) for k in range(PHASES)]), axis=0
      )
    elif rig.kind[e] == TRANSLATION:
      values[e] = np.array([solution[k][1][e] for k in range(PHASES)])
  return values


def walk(rig: Rig, capture: Capture) -> tuple[dict, list[float], tuple]:
  """The character's walk blend channels: (kind, keyed) per element, the
  float values behind them (PHASES vec3 keyed, one vec3 constant) and
  the eye rotation nodes whose multi-turn angles wrap"""
  if rig.character == 7:
    values = capture.locals(rig)
    keyed = set(values)
    consts: dict[int, tuple] = {}
    rotations: tuple = ()
  else:
    rt = RETARGETS[rig.character]
    solution = solve(rig, capture.positions(), rt)
    apply_eyes(rig, solution, rt, capture.eye_rotations())
    values = channel_values(rig, solution)
    keyed = (
      {node for node, *_ in rt.aims} | {a for a, *_ in rt.legs} | set(rt.eyes)
    )
    consts = {e: EYE_SCALE for e in rt.scales}
    rotations = tuple(sorted(rt.eyes))
  channels = {}
  floats: list[float] = []
  for e in rig.channels:
    if e in consts:
      channels[e] = (rig.kind[e], len(floats), False)
      floats += list(consts[e])
    elif e in values:
      channels[e] = (rig.kind[e], len(floats), e in keyed)
      floats += [
        float(x) for x in (values[e] if e in keyed else values[e][0]).ravel()
      ]
  return channels, floats, rotations


# =====================================================
# Emit
# =====================================================


def walk_lines(rig: Rig, channels: dict, rotations: tuple) -> Iterator[str]:
  slot, durations = BLENDS[rig.character]
  joints, flags, sub_object = EYE_JOINTS[rig.character]
  yield f"  {rig.character}: HypnosisWalk("
  yield f"    {rig.vtable:#x}, {slot:#x}, ({durations[0]!r}, {durations[1]!r}),"
  yield f"    {rotations!r}, {EYE_OFFSETS[rig.character]!r},"
  yield (
    f"    {joints!r}, {flags!r}, {sub_object!r}, "
    f"{FRONT_CHILDREN[rig.character]!r},"
  )
  yield "    {"
  for e, (kind, offset, keyed) in channels.items():
    yield f"      {e}: ({kind}, {offset}, {keyed!r}),"
  yield "    },"


def emit(
  overlay_data: tuple[bytes, list[int]], bank_data: bytes, eye_parts: list,
  walks: list[tuple[Rig, dict, list[float], tuple]], output: str
) -> None:
  cluster, words = overlay_data
  eye_blob = b""
  eye_lines = []
  for part in eye_parts:
    main = bytes.fromhex(part["main"])
    refs = [bytes.fromhex(r) for r in part["refs"]]
    assert not part["second"]
    eye_blob += main + b"".join(refs)
    record = ", ".join(f"{w:#x}" for w in part["record"])
    sizes = ", ".join(str(len(r)) for r in refs)
    eye_lines += [
      "  HypnosisPart(",
      f"    {part['entry'][0]:#x}, {part['joint']}, "
      f"{part['entry'][3] & ~0x800:#x}, ({record}),",
      f"    bytes.fromhex(\"{part['bounds']}\"),",
      f"    {len(main)}, ({sizes}),",
      "  ),"
    ]
  lines = [
    '"""Generated by build/hypnosis.py: the Hypnosis trap\'s ported episode',
    '5 assets (the overlay object, its sound, Sly\'s spiral eyes and the',
    'hypnotized walk per character), for HypnosisInstall."""',
    '',
    'import base64',
    'import zlib',
    'from functools import lru_cache',
    'from typing import NamedTuple',
    '',
    '',
    'class HypnosisPart(NamedTuple):',
    '  part_id: int',
    '  joint: int',
    '  flags: int',
    '  record: tuple[int, ...]',
    '  bounds: bytes',
    '  main: int',
    '  refs: tuple[int, ...]',
    '',
    '',
    'class HypnosisWalk(NamedTuple):',
    '  """A character\'s hypnotized walk: the entity class vtable that',
    '  identifies the character, the walk blend\'s slot on the entity and',
    '  its two sources\' clip lengths; the rotation channels whose',
    '  multi-turn angles close the loop; the rest offsets of the joints',
    '  the eye parts hang from; Sly\'s eye part joints mapped onto this',
    '  rig, the part flags to use (None keeps Sly\'s) and whether the part',
    '  copies a resident entry\'s sub-object word; child object ids drawn',
    '  in front of the overlay; and each channel\'s (kind, offset into',
    '  the values, keyed) with keyed channels holding PHASES vec3 poses',
    '  and the others one constant vec3."""',
    '  vtable: int',
    '  blend: int',
    '  durations: tuple[float, float]',
    '  rotations: tuple[int, ...]',
    '  offsets: dict[int, tuple[float, float, float]]',
    '  eye_joints: dict[int, int]',
    '  eye_flags: int | None',
    '  eye_sub_object: bool',
    '  front_children: tuple[int, ...]',
    '  channels: dict[int, tuple[int, int, bool]]',
    '',
    '',
    '@lru_cache(maxsize=None)',
    'def decode(data: str) -> bytes:',
    '  return zlib.decompress(base64.b85decode(data))',
    '',
    '',
    f'PHASES = {PHASES}',
    f'OVERLAY_OBJECT = {OVERLAY_OBJECT:#x}',
    f'OVERLAY_CLUSTER = ({OVERLAY_CLUSTER[0]:#x}, {OVERLAY_CLUSTER[1]:#x})',
    f'OVERLAY_WORDS_OFFSET = {OVERLAY_WORDS[0]:#x}',
    'OVERLAY_WORDS = (',
    *(f"  {w:#x}," for w in words),
    ')',
    f'OVERLAY = {literal(encode(cluster), 2)}',
    f'BANK = {literal(encode(bank_data), 2)}',
    'EYES = (',
    *eye_lines,
    ')',
    f'EYE_DATA = {literal(encode(eye_blob), 2)}',
    'WALKS: dict[int, HypnosisWalk] = {',
  ]
  for rig, channels, _, rotations in walks:
    lines += list(walk_lines(rig, channels, rotations))
    lines.append("  ),")
  lines.append("}")
  lines.append("WALK_VALUES: dict[int, str] = {")
  for rig, _, floats, _ in walks:
    blob = struct.pack(f"<{len(floats)}f", *floats)
    lines.append(f"  {rig.character}: {literal(encode(blob), 4)},")
  lines.append("}")
  open(output, "w").write("\n".join(lines) + "\n")
  print(
    f"wrote {output}: overlay {len(cluster):#x} B, bank {len(bank_data):#x} B,"
    f" {len(eye_parts)} eye parts, walks "
    + ", ".join(
      f"{rig.character}: {len(channels)} channels / {len(floats) * 4:#x} B"
      for rig, channels, floats, _ in walks
    )
  )


def main(argv: list[str]) -> None:
  if len(argv) < 6:
    print(__doc__)
    sys.exit(1)
  fight, sly, bentley, murray, capture_path, iso = argv[:6]
  output = argv[6] if len(argv) > 6 else "worlds/Sly2/data/Hypnosis.py"
  capture = Capture(capture_path)
  walks = []
  for path in (sly, bentley, murray):
    rig = Rig(Dump(path))
    channels, floats, rotations = walk(rig, capture)
    walks.append((rig, channels, floats, rotations))
  emit(overlay(Dump(fight)), bank(iso), eyes(Dump(sly)), walks, output)


if __name__ == "__main__":
  main(sys.argv[1:])
