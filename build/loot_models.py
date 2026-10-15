"""Builds data/LootModels.py from a running PCSX2 (SCUS-97316). From an
Archipelago checkout:

  python -m worlds.Sly2.build.loot_models capture EP [workdir]
      on the episode menu; then pick the episode. Polls the texture
      loader's tables through the hub load.
  python -m worlds.Sly2.build.loot_models extract EP [workdir]
      at rest in the hub: the loot pool's parts and the resident
      texture/CLUT records.
  python -m worlds.Sly2.build.loot_models emit [output] [workdir]

Loot sets repeat, so episodes 1, 2, 4 and 8 cover all thirty.
"""

import base64
import json
import os
import struct
import sys
import time
import zlib
from typing import Iterator

from worlds.Sly2.data.Constants import ADDRESSES, LOOT_IDS
from worlds.Sly2.LootInstall import tex0_offsets
from worlds.Sly2.pcsx2_interface.pine import DEFAULT_SLOT, Pine

GAME_ID = "SCUS-97316"
A = ADDRESSES[GAME_ID]
PART_SIZE = 0x28
RECORD_SIZE = 0x14
TYPE_ROW_SIZE = 0x2C
TEXTURE_RECORD_SIZE = 0x28
CLUT_RECORD_SIZE = 0x20
LOOT_NAMES = {loot_id: name for name, loot_id in LOOT_IDS.items()}


def in_ram(address: int) -> bool:
  return 0x100000 <= address < 0x2000000


def read_big(pine: Pine, address: int, n: int) -> bytes:
  return b"".join(
    pine.read_bytes(address + i, min(0x40000, n - i))
    for i in range(0, n, 0x40000)
  )


# =====================================================
# Capture
# =====================================================


def capture(pine: Pine, episode: int, workdir: str, timeout: float) -> dict:
  tables = [
    A["texture table count"], A["texture table"], A["clut table count"],
    A["clut table"], A["loading"]
  ]
  seen: set[tuple] = set()
  out: dict[str, dict] = {"tex": {}, "clut": {}}
  start = time.time()
  loading_seen = False
  last_loading = start
  while time.time() - start < timeout:
    tc, tp, cc, cp, loading = pine.batch_read_int32(tables)
    if loading == 2:
      loading_seen = True
      last_loading = time.time()
    for kind, count, pointer, stride, data_index, qwc_index in (
      ("tex", tc, tp, TEXTURE_RECORD_SIZE, 5, 6),
      ("clut", cc, cp, CLUT_RECORD_SIZE, 3, 4)
    ):
      if not 0 < count <= 4096 or not in_ram(pointer):
        continue
      raw = pine.read_bytes(pointer, count * stride)
      key = (kind, pointer, count, hash(raw))
      if key in seen:
        continue
      seen.add(key)
      for i in range(count):
        words = list(struct.unpack_from(f"<{stride // 4}I", raw, i * stride))
        data_pointer, qwc = words[data_index], words[qwc_index]
        if in_ram(data_pointer) and 0 < qwc < 0x4000:
          data = pine.read_bytes(data_pointer, qwc * 16).hex()
          out[kind].setdefault(str(words[0]), [words, data])
      print(
        f"{time.time() - start:6.1f}s {kind} table x{count}: "
        f"{len(out['tex'])} textures, {len(out['clut'])} CLUTs", flush=True
      )
    if loading_seen and loading != 2 and time.time() - last_loading > 6:
      break
  path = os.path.join(workdir, f"capture_ep{episode}.json")
  json.dump(out, open(path, "w"))
  print(f"wrote {path}")
  return out


# =====================================================
# Extract
# =====================================================


def dma_tags(pine: Pine, chain: int) -> Iterator[tuple[int, int, int, int]]:
  address = chain
  for _ in range(200):
    low, high = struct.unpack("<II", pine.read_bytes(address, 8))
    qwc, tag_id, target = low & 0xFFFF, (low >> 28) & 7, high & 0x7FFFFFFF
    yield address, tag_id, qwc, target
    if tag_id in (0, 6, 7):
      return
    if tag_id == 1:
      address += 16 + qwc * 16
    elif tag_id in (3, 4, 5):
      address += 16
    elif tag_id == 2:
      address = target
    else:
      return


def chain_span(pine: Pine, chain: int) -> tuple[int, list[tuple[int, int]]]:
  tags = list(dma_tags(pine, chain))
  refs = [
    (target, qwc * 16) for _, tag_id, qwc, target in tags if tag_id in (3, 4)
  ]
  return tags[-1][0] + 16 - chain, refs


def extract_part(pine: Pine, template: int, index: int) -> dict:
  entry = pine.read_int32(template + 0xC0) + index * PART_SIZE
  words = struct.unpack("<10I", pine.read_bytes(entry, PART_SIZE))
  record = struct.unpack("<5I", pine.read_bytes(
    pine.read_int32(template + 0xBC) + index * RECORD_SIZE, RECORD_SIZE
  ))
  size, refs = chain_span(pine, words[4])
  part = {
    "entry": list(words), "record": list(record),
    "main": pine.read_bytes(words[4], size).hex(),
    "refs": [pine.read_bytes(address, n).hex() for address, n in refs],
    "second": ""
  }
  if record[2]:
    # The VU preprocess chain must directly follow the main chain.
    assert record[2] == words[4] + size, hex(record[2])
    second_size, _ = chain_span(pine, record[2])
    part["second"] = pine.read_bytes(record[2], second_size).hex()
  return part


def scan_records(pine: Pine) -> dict[str, dict[str, list[int]]]:
  start, end = A["texture records"]
  memory = read_big(pine, start, end - start)
  sizes = {1 << k for k in range(3, 11)}
  bits = {0: 32, 1: 24, 2: 16, 0x13: 8, 0x14: 4, 0x1B: 8, 0x24: 4, 0x2C: 4}
  found: dict[str, dict[str, list[int]]] = {"tex": {}, "clut": {}}
  for offset in range(0, len(memory) - TEXTURE_RECORD_SIZE, 4):
    flag = struct.unpack_from("<I", memory, offset + 4)[0]
    if (flag & 0xFF) != 1 or flag > 0xFFFF:
      continue
    words = list(struct.unpack_from("<10I", memory, offset))
    # Testing if it's a texture record or a CLUT record. Texture records
    # have a zeroed out word 7.
    if (
      words[7] and (words[7] >> 29) == 1 and words[5] == 0 and
      (words[6] & 0xFFFFF) == 0 and (words[6] >> 20) in (0x13, 0x14) and
      0 < words[4] <= 0x40
    ):
      found["clut"].setdefault(str(words[0]), words[:8])
      continue
    width, height = words[2] & 0xFFFF, words[2] >> 16
    bpp = bits.get(words[3] & 0xFF)
    if (
      width in sizes and height in sizes and bpp and words[7] == 0 and
      words[4] == width * height * bpp // 8
    ):
      found["tex"].setdefault(str(words[0]), words)
  return found


def extract(pine: Pine, episode: int, workdir: str) -> dict:
  world, map_id, loading = pine.batch_read_int32(
    [A["world id"], A["map id"], A["loading"]]
  )
  assert world == episode and loading != 2, (world, map_id, loading)
  template = pine.read_int32(A["loot pool"])
  count = pine.read_int32(template + 0xB8)
  parts_list = pine.read_int32(template + 0xC0)
  by_part_id: dict[int, list[int]] = {}
  for index in range(count):
    part_id = pine.read_int32(parts_list + index * PART_SIZE)
    by_part_id.setdefault(part_id, []).append(index)
  table = pine.read_int32(template + 0x240)
  loot: dict[str, list[dict]] = {}
  for row in range(pine.read_int32(template + 0x23C)):
    loot_id, part_id = pine.batch_read_int32(
      [table + row * TYPE_ROW_SIZE, table + row * TYPE_ROW_SIZE + 0x20]
    )
    if part_id in by_part_id:
      loot[str(loot_id)] = [
        extract_part(pine, template, index) for index in by_part_id[part_id]
      ]
      name = LOOT_NAMES.get(loot_id, hex(loot_id))
      print(f"{name}: {len(loot[str(loot_id)])} parts")
  material_base = None
  for parts in loot.values():
    for part in parts:
      if part["entry"][3] != 0x49 and part["entry"][5]:
        material_base = (part["entry"][4] - part["entry"][5]) & 0xFFFFFFFF
  out = {
    "episode": episode, "map": map_id, "material_base": material_base,
    "loot": loot, "records": scan_records(pine)
  }
  path = os.path.join(workdir, f"extract_ep{episode}.json")
  json.dump(out, open(path, "w"))
  print(f"wrote {path}")
  return out


# =====================================================
# Emit
# =====================================================


def bindings(
  part: dict, records: dict
) -> dict[tuple[int, int], tuple[int, int]]:
  by_tbp = {words[8] & 0x3FFF: int(i) for i, words in records["tex"].items()}
  by_cbp = {
    (words[7] >> 5) & 0x3FFF: int(i) for i, words in records["clut"].items()
  }
  out = {}
  for ref, data in enumerate(part["refs"]):
    buffer = bytes.fromhex(data)
    for offset in tex0_offsets(buffer):
      low, high = struct.unpack_from("<2I", buffer, offset)
      out[ref, offset] = (by_tbp[low & 0x3FFF], by_cbp[(high >> 5) & 0x3FFF])
  return out


def projection(part: dict) -> int:
  buffer = bytes.fromhex(part["refs"][0])
  for offset in range(0, len(buffer), 4):
    word = struct.unpack_from("<I", buffer, offset)[0]
    if (word >> 16) == 0x4B00:
      return word & 0xFFFF
  raise ValueError("no projection constant")


def encode(data: bytes) -> str:
  return base64.b85encode(zlib.compress(data, 9)).decode("ascii")


def literal(text: str, indent: int) -> str:
  width = 76 - indent
  chunks = [text[i:i + width] for i in range(0, len(text), width)]
  pad = " " * indent
  body = "\n".join(f'{pad}"{chunk}"' for chunk in chunks)
  return f"(\n{body}\n{pad[:-2]})"


def emit(workdir: str, output: str) -> None:
  extracts = sorted(
    (json.load(open(os.path.join(workdir, name)))
     for name in os.listdir(workdir) if name.startswith("extract_ep")),
    key=lambda e: e["episode"]
  )
  captures: dict[str, dict] = {"tex": {}, "clut": {}}
  for name in os.listdir(workdir):
    if name.startswith("capture_ep"):
      loaded = json.load(open(os.path.join(workdir, name)))
      for kind, entries in loaded.items():
        for i, entry in entries.items():
          captures[kind].setdefault(i, entry)
  models = []
  needed: dict[str, set[int]] = {"tex": set(), "clut": set()}
  for e in extracts:
    for loot_id, parts in e["loot"].items():
      if any(m[0] == int(loot_id) for m in models):
        continue
      blob = b""
      part_lines = []
      for part in parts:
        main = bytes.fromhex(part["main"])
        second = bytes.fromhex(part["second"])
        refs = [bytes.fromhex(r) for r in part["refs"]]
        blob += main + b"".join(refs) + second
        textures = bindings(part, e["records"]) if refs else {}
        for tex_id, clut_id in textures.values():
          needed["tex"].add(tex_id)
          needed["clut"].add(clut_id)
        entry = part["entry"]
        record = ", ".join(
          f"{w:#x}" for w in part["record"][:2] + [0] + part["record"][3:]
        )
        sizes = ", ".join(str(len(r)) for r in refs)
        binding = [
          f"        ({r}, {o:#x}): ({t:#x}, {c:#x}),"
          for (r, o), (t, c) in textures.items()
        ]
        part_lines += [
          "    LootPart(",
          f"      {entry[0]:#x}, {entry[3]:#x}, ({record}),",
          f"      {len(main)}, ({sizes}{',' if len(refs) == 1 else ''}), "
          f"{len(second)},",
          *(["      {"] + binding + ["      }"] if binding else ["      {}"]),
          "    ),"
        ]
      textured = next(p for p in parts if p["refs"])
      models.append((
        int(loot_id), e["episode"], e["material_base"], projection(textured),
        part_lines, encode(blob)
      ))
  models.sort()
  lines = [
    '"""This one\'s pretty fucked, and not really intended to be read by',
    'humans. Generated by build/loot_models.py: the parts, display lists',
    'and textures of every pickpocket loot, for LootInstall."""',
    '',
    'import base64',
    'import zlib',
    'from functools import lru_cache',
    'from typing import NamedTuple',
    '',
    '',
    'class LootPart(NamedTuple):',
    '  part_id: int',
    '  flags: int',
    '  record: tuple[int, ...]',
    '  main: int',
    '  refs: tuple[int, ...]',
    '  second: int',
    '  textures: dict[tuple[int, int], tuple[int, int]]',
    '',
    '',
    'class LootModel(NamedTuple):',
    '  episode: int',
    '  material_base: int',
    '  projection: int',
    '  parts: tuple[LootPart, ...]',
    '  data: str',
    '',
    '',
    '@lru_cache(maxsize=None)',
    'def decode(data: str) -> bytes:',
    '  return zlib.decompress(base64.b85decode(data))',
    '',
    '',
    'LOOT_MODELS: dict[int, LootModel] = {',
  ]
  for loot_id, episode, material_base, proj, part_lines, data in models:
    lines.append(
      f"  {loot_id:#x}: LootModel({episode}, {material_base:#x}, {proj:#x}, ("
    )
    lines += part_lines
    lines.append(f"  ), {literal(data, 4)}),")
  lines.append("}")
  for kind, name in (("tex", "TEXTURES"), ("clut", "CLUTS")):
    lines += ["", f"{name}: dict[int, tuple[tuple[int, ...], str]] = {{"]
    for i in sorted(needed[kind]):
      words, data = captures[kind][str(i)]
      words = list(words)
      words[5 if kind == "tex" else 3] = 0
      half = len(words) // 2
      lines += [
        f"  {i:#x}: (",
        f"    ({', '.join(f'{w:#x}' for w in words[:half])},",
        f"     {', '.join(f'{w:#x}' for w in words[half:])}),",
        f"    {literal(encode(bytes.fromhex(data)), 6)}",
        "  ),"
      ]
    lines.append("}")
  open(output, "w").write("\n".join(lines) + "\n")
  print(
    f"wrote {output}: {len(models)} loot, {len(needed['tex'])} textures, "
    f"{len(needed['clut'])} CLUTs"
  )


def main(argv: list[str]) -> None:
  command = argv[1]
  here = os.path.dirname(__file__)
  workdir = (
    argv[3] if len(argv) > 3 else os.path.join(here, "target", "loot")
  )
  os.makedirs(workdir, exist_ok=True)
  if command == "emit":
    output = (
      argv[2] if len(argv) > 2
      else os.path.join(here, "..", "data", "LootModels.py")
    )
    emit(workdir, output)
    return
  pine = Pine(int(os.environ.get("SLY2_E2E_PINE_SLOT", str(DEFAULT_SLOT))))
  pine.connect()
  episode = int(argv[2])
  if command == "capture":
    capture(pine, episode, workdir, 900)
  elif command == "extract":
    extract(pine, episode, workdir)
  else:
    raise SystemExit(__doc__)


if __name__ == "__main__":
  main(sys.argv)
