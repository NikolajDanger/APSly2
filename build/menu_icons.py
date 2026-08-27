"""Offline generator for data/MenuIcons.py: the ThiefNet icon-theme glyph
packets (Archipelago-logo vector drawings) for every theme and item class.

Pure SVG -> VU packet; no running game needed. Run:

  python -m worlds.Sly2.build.menu_icons emit [output]

Source art: menu_icons_assets/color-icon.svg from the Archipelago asset pack
(CC BY-NC 4.0, Krista Corkos / Christopher Wilson). The SVG and this generator
live under build/ (excluded from the shipped apworld); only the emitted
data/MenuIcons.py ships."""
import base64
import math
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET

VU_WORDS = 192


# =====================================================
# SVG -> vector geometry
# =====================================================

def parse_path(d):
  toks = re.findall(r"[MmLlHhVvCcSsQqTtZz]|-?\d*\.?\d+(?:e-?\d+)?", d)
  i = 0
  subpaths = []
  cur = []
  pos = (0.0, 0.0)
  start = (0.0, 0.0)
  prev_ctrl = None
  cmd = None

  def num():
    nonlocal i
    v = float(toks[i]); i += 1
    return v

  def bez(p0, p1, p2, p3, n=8):
    out = []
    for k in range(1, n + 1):
      t = k / n
      u = 1 - t
      x = u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0]
      y = u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]
      out.append((x, y))
    return out

  while i < len(toks):
    if re.match(r"[A-Za-z]", toks[i]):
      cmd = toks[i]; i += 1
    rel = cmd.islower()
    c = cmd.upper()
    if c == "M":
      x, y = num(), num()
      if rel: x += pos[0]; y += pos[1]
      if cur: subpaths.append(cur)
      cur = [(x, y)]; pos = start = (x, y); prev_ctrl = None
      cmd = "l" if rel else "L"
    elif c == "L":
      x, y = num(), num()
      if rel: x += pos[0]; y += pos[1]
      cur.append((x, y)); pos = (x, y); prev_ctrl = None
    elif c == "H":
      x = num()
      if rel: x += pos[0]
      pos = (x, pos[1]); cur.append(pos); prev_ctrl = None
    elif c == "V":
      y = num()
      if rel: y += pos[1]
      pos = (pos[0], y); cur.append(pos); prev_ctrl = None
    elif c in "CS":
      if c == "C":
        p1 = (num(), num())
        if rel: p1 = (p1[0] + pos[0], p1[1] + pos[1])
      else:
        p1 = (2*pos[0] - prev_ctrl[0], 2*pos[1] - prev_ctrl[1]) \
          if prev_ctrl else pos
      p2 = (num(), num())
      if rel: p2 = (p2[0] + pos[0], p2[1] + pos[1])
      p3 = (num(), num())
      if rel: p3 = (p3[0] + pos[0], p3[1] + pos[1])
      cur.extend(bez(pos, p1, p2, p3)); prev_ctrl = p2; pos = p3
    elif c == "Z":
      if cur: subpaths.append(cur); cur = []
      pos = start; prev_ctrl = None
    else:
      raise ValueError(cmd)
  if cur: subpaths.append(cur)
  return subpaths


def simplify(poly, tol):
  """Douglas-Peucker on a closed ring."""
  def dp(pts):
    if len(pts) < 3: return pts
    a, b = pts[0], pts[-1]
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = math.hypot(dx, dy) or 1e-9
    best, bi = 0, 0
    for k in range(1, len(pts)-1):
      dist = abs(dx*(a[1]-pts[k][1]) - dy*(a[0]-pts[k][0])) / length
      if dist > best: best, bi = dist, k
    if best > tol:
      return dp(pts[:bi+1])[:-1] + dp(pts[bi:])
    return [a, b]
  far = max(range(len(poly)), key=lambda k: math.dist(poly[0], poly[k]))
  return dp(poly[:far+1])[:-1] + dp(poly[far:] + [poly[0]])[:-1]


def area(p):
  return sum(p[i][0]*p[(i+1) % len(p)][1] - p[(i+1) % len(p)][0]*p[i][1]
    for i in range(len(p))) / 2


def cross(o, a, b):
  return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])


def in_tri(p, a, b, c):
  return cross(a, b, p) >= 0 and cross(b, c, p) >= 0 and cross(c, a, p) >= 0


def ear_clip(poly):
  """poly CCW -> list of triangles (index triples)."""
  idx = list(range(len(poly)))
  tris = []
  guard = 0
  while len(idx) > 3 and guard < 10000:
    guard += 1
    n = len(idx)
    for k in range(n):
      i0, i1, i2 = idx[k-1], idx[k], idx[(k+1) % n]
      a, b, c = poly[i0], poly[i1], poly[i2]
      if cross(a, b, c) <= 0: continue
      if any(in_tri(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
        continue
      tris.append((i0, i1, i2)); del idx[k]; break
    else:
      break
  if len(idx) == 3: tris.append(tuple(idx))
  return tris


def hertel_mehlhorn(poly, tris):
  """Merge triangles into convex polygons (as index rings)."""
  polys = [list(t) for t in tris]

  def convex(ring):
    n = len(ring)
    return all(cross(poly[ring[i-1]], poly[ring[i]], poly[ring[(i+1) % n]]) > 0
      for i in range(n))
  changed = True
  while changed:
    changed = False
    for a in range(len(polys)):
      for b in range(a+1, len(polys)):
        pa, pb = polys[a], polys[b]
        shared = [v for v in pa if v in pb]
        if len(shared) != 2: continue
        ia = pa.index(shared[0]); ib = pa.index(shared[1])
        if (ia+1) % len(pa) == ib: u, v = shared[0], shared[1]
        elif (ib+1) % len(pa) == ia: u, v = shared[1], shared[0]
        else: continue
        ar = pa[pa.index(v):] + pa[:pa.index(v)]
        br = pb[pb.index(u):] + pb[:pb.index(u)]
        merged = ar + br[1:-1]
        if convex(merged):
          polys[a] = merged; del polys[b]; changed = True; break
      if changed: break
  return polys


def svg_fans(path, tol_frac=0.012):
  root = ET.parse(path).getroot()
  style = {}
  for st in root.iter("{http://www.w3.org/2000/svg}style"):
    for m in re.finditer(r"\.(\w+)\{fill:#([0-9A-Fa-f]{6});\}", st.text):
      style[m.group(1)] = m.group(2)
  vb = [float(v) for v in root.get("viewBox").split()]
  tol = tol_frac * max(vb[2], vb[3])
  shapes = []
  for el in root.iter("{http://www.w3.org/2000/svg}path"):
    fill = el.get("fill")
    if fill is None:
      fill = "#" + style[el.get("class")]
    for sp in parse_path(el.get("d")):
      sp = simplify(sp, tol)
      if area(sp) < 0: sp = sp[::-1]
      shapes.append((sp, fill))
  return shapes, vb


def decompose(ring):
  tris = ear_clip(ring)
  return [[ring[i] for i in r] for r in hertel_mehlhorn(ring, tris)]


def offset(ring, d):
  n = len(ring)

  def normal(a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]; length = math.hypot(dx, dy) or 1e-9
    return (dy/length, -dx/length)

  def build(sign):
    out = []
    for i in range(n):
      n0 = normal(ring[i-1], ring[i]); n1 = normal(ring[i], ring[(i+1) % n])
      dot = max(-0.3, n0[0]*n1[0] + n0[1]*n1[1])
      mx, my = (n0[0]+n1[0])/(1+dot), (n0[1]+n1[1])/(1+dot)
      out.append((ring[i][0] + sign*d*mx, ring[i][1] + sign*d*my))
    return out
  a, b = build(1), build(-1)
  return a if abs(area(a)) > abs(area(b)) else b


def fans_for(shapes, box_scale, color=None, grow=0.0):
  fans = []
  for ring, fill in shapes:
    r = offset(ring, grow) if grow else ring
    for poly in decompose(r):
      fans.append((poly, abgr(fill) if color is None else color))
  return fans


def fit(shapes, vb, box=1000):
  cx, cy = vb[0] + vb[2]/2, vb[1] + vb[3]/2
  s = 2*box / max(vb[2], vb[3])
  return [([((x-cx)*s, (y-cy)*s) for x, y in poly], fill)
    for poly, fill in shapes]


def abgr(fill, alpha=0x80):
  r, g, b = int(fill[1:3], 16), int(fill[3:5], 16), int(fill[5:7], 16)
  return (alpha << 24) | (b << 16) | (g << 8) | r


def packet(fans):
  n = len(fans); out = b""
  out += struct.pack("<I", 0x30000000) + bytes(16)
  out += struct.pack("<I", 0x6401c007) + struct.pack("<II", n, 0)
  out += struct.pack("<I", 0x01000102)
  d = b"".join(bytes([1, len(v), 0]) for v, _ in fans)
  d += bytes((-len(d)) % 4)
  out += struct.pack("<I", 0x6a00c008 | (n << 16)) + d
  out += struct.pack("<I", 0x6e00c009 | (n << 16)) \
    + b"".join(struct.pack("<I", c) for _, c in fans)
  out += struct.pack("<I", 0x01000101) \
    + struct.pack("<II", 0x20000000, 0x50505050)
  addr = 8 + 2 * n
  for v, _ in fans:
    out += struct.pack("<I", 0x75008000 | (len(v) << 16) | addr) \
      + b"".join(struct.pack("<hh", int(round(x)), int(round(y))) for x, y in v)
    addr += len(v)
  assert addr <= VU_WORDS, addr
  out += struct.pack("<II", 0x20000000, 0x3f3f3f3f) \
    + struct.pack("<I", 0x14000028)
  out += bytes((-len(out)) % 16)
  return struct.pack("<I", 0x10000000 | (len(out) // 16)) + bytes(12) \
    + out + struct.pack("<I", 0x60000000) + bytes(12)


def scale(fans, f):
  return [([(x * f, y * f) for x, y in poly], c) for poly, c in fans]


def shift(fans, dx, dy):
  return [([(x + dx, y + dy) for x, y in v], c) for v, c in fans]


# =====================================================
# Calibration + theme parameters
# =====================================================

HERE = os.path.dirname(__file__)
SVG = os.path.join(HERE, "menu_icons_assets", "color-icon.svg")

# Per-slot scale/offset/grow, measured live against the row grid.
CALIB = {
  "sly": {"fill": 0.6245033112582782, "sil": 0.22188235294117648,
    "sil_dx": -9.056603773584726, "sil_dy": -9.056603773584726,
    "fill_dx": 0, "fill_dy": 0, "grow": 155.47169811320552},
  "ben": {"fill": 0.8498181433800518, "sil": 0.22188235294117648,
    "sil_dx": 0.0, "sil_dy": -9.056603773585437,
    "fill_dx": 0, "fill_dy": 0, "grow": 150.94339622641348},
  "mur": {"fill": 0.793064175835808, "sil": 0.22999999999999998,
    "sil_dx": 0.0, "sil_dy": 0.0,
    "fill_dx": 0, "fill_dy": 0, "grow": 123.77358490565825},
  "fourth": {"fill": 0.2387054132784132, "sil": 0.2214,
    "sil_dx": -18.11320754716732, "sil_dy": -36.226415094341036,
    "fill_dx": 0, "fill_dy": 0, "grow": 78.49056603773143},
}

# Per-slot vertical alignment (box units, +down): each glyph slot has its own
# baked draw height; nudge fill+outline together so all classes sit on the grid.
VALIGN = {"sly": -45, "ben": 73, "mur": 44, "fourth": -30}

FOURTH_GROW = 110       # filler silhouette grow (overrides CALIB)
FIFTH_SCALE = 0.2387    # unknown packet scale
FIFTH_VALIGN = -30      # unknown vertical align
FIFTH_GROW = 70         # unknown black-rim thickness

# Theme palettes. Filler green #73AC65 is shared by themes 2 and 3.
ARROW = "#FFD400"
TRAP = "#E8685A"
FILLER = "#73AC65"
THEME3 = {"sly": "#A85EC0", "ben": "#5E89DB", "mur": "#E8685A",
  "fourth": "#73AC65"}

# progression up-arrow badge, bottom-right. Fill = head + shaft;
# outline = a uniform perpendicular offset of the 7-pt silhouette.
ARROW_SCALE = 1.3
ARROW_CX, ARROW_CY = 430, 430
ARROW_HEAD = [(-260, -40), (0, -360), (260, -40)]
ARROW_SHAFT = [(-120, -40), (120, -40), (120, 300), (-120, 300)]
ARROW_SIL = [(0, -360), (260, -40), (120, -40), (120, 300),
  (-120, 300), (-120, -40), (-260, -40)]
ARROW_OFFSET = 68

BASE = fit(*svg_fans(SVG, 0.012))
CLASS_SLOT = {"progression": "sly", "useful": "ben", "trap": "mur"}


def _inside(pt, poly):
  x, y = pt; c = False; n = len(poly)
  for i in range(n):
    x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % n]
    if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
      c = not c
  return c


def _isect(p0, d0, p1, d1):
  det = d0[0] * -d1[1] + d1[0] * d0[1]
  t = ((p1[0] - p0[0]) * -d1[1] + d1[0] * (p1[1] - p0[1])) / det
  return (p0[0] + t * d0[0], p0[1] + t * d0[1])


def _outline_ring():
  n = len(ARROW_SIL); lines = []
  for i in range(n):
    a = ARROW_SIL[i]; b = ARROW_SIL[(i + 1) % n]
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(dx, dy)
    nx, ny = dy / ln, -dx / ln
    if _inside(((a[0] + b[0]) / 2 + nx, (a[1] + b[1]) / 2 + ny), ARROW_SIL):
      nx, ny = -nx, -ny
    lines.append(((a[0] + nx * ARROW_OFFSET, a[1] + ny * ARROW_OFFSET),
      (dx, dy)))
  return [_isect(lines[i - 1][0], lines[i - 1][1], lines[i][0], lines[i][1])
    for i in range(n)]


def _arrow_tf(pts):
  return [(x * ARROW_SCALE + ARROW_CX, y * ARROW_SCALE + ARROW_CY)
    for x, y in pts]


def arrow_fans():
  yel = abgr(ARROW)
  fill = [(_arrow_tf(ARROW_HEAD), yel), (_arrow_tf(ARROW_SHAFT), yel)]
  outline = [(poly, 0x80000000)
    for poly in decompose(_arrow_tf(_outline_ring()))]
  return fill + outline


def portrait_pair(slot, fill_fans):
  """Fill + silhouette packets for a vanilla character slot (sly/ben/mur)."""
  q = CALIB[slot]; va = VALIGN[slot]
  fill = packet(scale(shift(fill_fans, q["fill_dx"], q["fill_dy"] + va),
    q["fill"]))
  sil_fans = fans_for(BASE, 1, 0x80000000, q["grow"])
  sil = packet(scale(shift(sil_fans, q["sil_dx"], q["sil_dy"] + va), q["sil"]))
  return fill, sil


def filler_pair(color):
  """Fill + silhouette packets for the appended filler slot."""
  q = CALIB["fourth"]; va = VALIGN["fourth"]
  fill_fans = fans_for(BASE, 1) if color is None else fans_for(BASE, 1, color)
  sil_fans = fans_for(BASE, 1, 0x80000000, FOURTH_GROW)
  fill = packet(scale(shift(fill_fans, q["fill_dx"], q["fill_dy"] + va),
    q["fill"]))
  sil = packet(scale(shift(sil_fans, q["fill_dx"], q["fill_dy"] + va),
    q["fill"]))
  return fill, sil


def unknown_pair():
  """Outline-only logo (invisible interior + black rim) for the 5th slot."""
  for tol in (0.012, 0.018, 0.025, 0.032, 0.04, 0.05):
    base = fit(*svg_fans(SVG, tol))
    fill = fans_for(base, 1, 0x00000000)
    outline = fans_for(base, 1, 0x80000000, FIFTH_GROW)
    fans = shift(fill + outline, 0, FIFTH_VALIGN)
    vu = 8 + 2 * len(fans) + sum(len(v) for v, _ in fans)
    if vu <= VU_WORDS:
      fill_packet = packet(scale(fans, FIFTH_SCALE))
      break
  else:
    raise RuntimeError("no tolerance fits the unknown icon")
  mask = fit(*svg_fans(SVG, 0.05))
  invisible = shift(fans_for(mask, 1, 0x00000000), 0, FIFTH_VALIGN)
  return fill_packet, packet(scale(invisible, FIFTH_SCALE))


def _progression_fill(theme):
  if theme == 1: return fans_for(BASE, 1)
  if theme == 2: return arrow_fans() + fans_for(BASE, 1)
  return fans_for(BASE, 1, abgr(THEME3["sly"]))


def _useful_fill(theme):
  if theme == 3: return fans_for(BASE, 1, abgr(THEME3["ben"]))
  return fans_for(BASE, 1)


def _trap_fill(theme):
  if theme == 1: return fans_for(BASE, 1)
  return fans_for(BASE, 1, abgr(TRAP))


def _filler_color(theme):
  if theme == 1: return None
  return abgr(FILLER)


def build_theme(theme):
  """{class -> (fill_bytes, sil_bytes)} for one icon theme (1, 2 or 3)."""
  fills = {"progression": _progression_fill(theme),
    "useful": _useful_fill(theme), "trap": _trap_fill(theme)}
  out = {}
  for cls, slot in CLASS_SLOT.items():
    out[cls] = portrait_pair(slot, fills[cls])
  out["filler"] = filler_pair(_filler_color(theme))
  out["unknown"] = unknown_pair()
  return out


# =====================================================
# Emit data/MenuIcons.py
# =====================================================

THEME_CLASSES = ["progression", "useful", "trap", "filler", "unknown"]

HEADER = [
  '"""Generated by build/menu_icons.py: the ThiefNet icon-theme glyph packets',
  '(Archipelago-logo vector drawings) for each theme and item class, for',
  'MenuIcons. Source art: color-icon.svg from the Archipelago asset pack',
  '(CC BY-NC 4.0, Krista Corkos / Christopher Wilson)."""',
  '',
  'import base64',
  'import zlib',
  'from typing import NamedTuple',
  '',
  '',
  'class ThemeIcon(NamedTuple):',
  '  fill: str',
  '  sil: str',
  '',
  '',
  'def decode(data: str) -> bytes:',
  '  return zlib.decompress(base64.b85decode(data))',
  '',
  '',
  'THEMES: dict[int, dict[str, ThemeIcon]] = {',
]


def encode(data):
  import zlib
  return base64.b85encode(zlib.compress(data, 9)).decode("ascii")


def literal(text, indent):
  width = 76 - indent
  chunks = [text[i:i + width] for i in range(0, len(text), width)]
  pad = " " * indent
  body = "\n".join(f'{pad}"{chunk}"' for chunk in chunks)
  return f"(\n{body}\n{pad[:-2]})"


def emit(output):
  themes = {t: build_theme(t) for t in (1, 2, 3)}
  lines = list(HEADER)
  for t in (1, 2, 3):
    lines.append(f"  {t}: {{")
    for cls in THEME_CLASSES:
      fill, sil = themes[t][cls]
      lines.append(f'    "{cls}": ThemeIcon(')
      lines.append(f"      {literal(encode(fill), 6)},")
      lines.append(f"      {literal(encode(sil), 6)},")
      lines.append("    ),")
    lines.append("  },")
  lines.append("}")
  open(output, "w").write("\n".join(lines) + "\n")
  print(f"wrote {output}: 3 themes x {len(THEME_CLASSES)} classes")


def main(argv):
  command = argv[1] if len(argv) > 1 else ""
  if command != "emit":
    raise SystemExit(__doc__)
  output = (argv[2] if len(argv) > 2
    else os.path.join(HERE, "..", "data", "MenuIcons.py"))
  emit(output)


if __name__ == "__main__":
  main(sys.argv)
