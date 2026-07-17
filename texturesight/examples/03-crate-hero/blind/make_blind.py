#!/usr/bin/env python3
"""Blind one-shot procedural generator: hero sci-fi supply crate.

Outputs (same directory as this script):
  crate_blind.obj + crate_blind.mtl
  crate_albedo.png / crate_normal.png / crate_roughness.png (1024x1024)

Only stdlib + numpy + Pillow. No viewers, no baking, no validation tools.

Geometry: assembly of axis-aligned boxes, most with chamfered edges
(chamfered box = 6 face quads + 12 edge quads + 8 corner tris = 44 tris).
Winding is enforced programmatically (Newell normal vs outward hint).

UVs: hand-allocated atlas of rectangular regions; every face maps into a
named region. Textures are painted from the SAME region table, so the
mesh<->texture correspondence is exact by construction. All chamfer faces
share one bare-metal trim strip, so geometric edges read as worn metal.

Normal map: tangent-space, OpenGL convention (+Y = +V, green up), derived
from a painted height field, gradients computed per region (no seam bleed).
Crate is Y-up, base at y=0, roughly 0.66 x 0.61 x 0.52 m with handles.
"""
import os, zlib
import numpy as np
from PIL import Image, ImageDraw

OUT = os.path.dirname(os.path.abspath(__file__))
TEX = 1024
NSTR = 6.0  # normal-map strength multiplier

# ------------------------------------------------------------------ atlas
class Atlas:
    def __init__(self, size=TEX, gutter=6):
        self.size, self.g = size, gutter
        self.x = gutter
        self.y = gutter
        self.rowh = 0
        self.regions = {}

    def new_row(self):
        self.y += self.rowh + self.g
        self.x = self.g
        self.rowh = 0

    def place(self, name, w, h):
        assert self.x + w <= self.size - self.g, ('atlas overflow x', name)
        assert self.y + h <= self.size - self.g, ('atlas overflow y', name)
        self.regions[name] = (self.x, self.y, self.x + w, self.y + h)
        self.x += w + self.g
        self.rowh = max(self.rowh, h)

A = Atlas()
A.place('panel_px', 324, 236)   # right side panel (hazard band)
A.place('panel_nx', 324, 236)   # left side panel (barcode)
A.place('core_top', 160, 160)
A.place('skirt_bottom', 160, 160)
A.new_row()
A.place('panel_pz', 324, 236)   # front panel (digits 04)
A.place('panel_nz', 324, 236)   # back panel (chevrons)
A.place('rim_top', 220, 220)
A.place('core_bottom', 120, 120)
A.new_row()
A.place('lid_top', 320, 320)
A.place('post_sides', 44, 320)
A.place('bevel_strip', 48, 320)
A.place('handle_posts', 64, 48)
A.place('post_caps', 64, 64)
A.place('latch_front', 52, 68)
A.place('hidden', 64, 64)
A.place('handle_bar', 220, 40)
A.new_row()
A.place('rim_sides', 330, 28)   # hazard stripes
A.place('skirt_sides', 330, 24)
A.place('lid_sides', 300, 22)

# --------------------------------------------------------------- geometry
faces = []

def add_face(vs, outward, region, axsg=None, part='crate'):
    vs = [np.asarray(v, float) for v in vs]
    n = np.zeros(3)
    for i in range(len(vs)):
        p, q = vs[i], vs[(i + 1) % len(vs)]
        n[0] += (p[1] - q[1]) * (p[2] + q[2])
        n[1] += (p[2] - q[2]) * (p[0] + q[0])
        n[2] += (p[0] - q[0]) * (p[1] + q[1])
    if np.dot(n, outward) < 0:
        vs = vs[::-1]
        n = -n
    faces.append({'vs': vs, 'n': n / np.linalg.norm(n),
                  'region': region, 'axsg': axsg, 'part': part})

AXN = ('x', 'y', 'z')

def box(c, h, regmap, b=0.0, part='crate'):
    """Axis-aligned box, chamfered if b > 0."""
    c = np.asarray(c, float)
    h = np.asarray(h, float)
    for i in range(3):
        for s in (1, -1):
            j, k = [a for a in range(3) if a != i]
            quad = []
            for sj, sk in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                v = c.copy()
                v[i] += s * h[i]
                v[j] += sj * (h[j] - b)
                v[k] += sk * (h[k] - b)
                quad.append(v)
            out = np.zeros(3)
            out[i] = s
            add_face(quad, out, regmap[(AXN[i], s)], (AXN[i], s), part)
    if b > 0:
        for i, j in ((0, 1), (0, 2), (1, 2)):
            k = 3 - i - j
            for si in (1, -1):
                for sj in (1, -1):
                    quad = []
                    for fi, fj, sk in ((1, 0, -1), (0, 1, -1), (0, 1, 1), (1, 0, 1)):
                        v = c.copy()
                        v[i] += si * (h[i] if fi else h[i] - b)
                        v[j] += sj * (h[j] if fj else h[j] - b)
                        v[k] += sk * (h[k] - b)
                        quad.append(v)
                    out = np.zeros(3)
                    out[i] = si
                    out[j] = sj
                    add_face(quad, out, 'bevel_strip', None, part)
        for sx in (1, -1):
            for sy in (1, -1):
                for sz in (1, -1):
                    tri = [
                        c + np.array([sx * h[0], sy * (h[1] - b), sz * (h[2] - b)]),
                        c + np.array([sx * (h[0] - b), sy * h[1], sz * (h[2] - b)]),
                        c + np.array([sx * (h[0] - b), sy * (h[1] - b), sz * h[2]]),
                    ]
                    add_face(tri, np.array([sx, sy, sz], float),
                             'bevel_strip', None, part)

def RM(every=None, sides=None, top=None, bottom=None,
       px=None, nx=None, pz=None, nz=None):
    d = {('x', 1): px or sides or every,
         ('x', -1): nx or sides or every,
         ('z', 1): pz or sides or every,
         ('z', -1): nz or sides or every,
         ('y', 1): top or every,
         ('y', -1): bottom or every}
    for v in d.values():
        assert v is not None
    return d

# core body (recessed panel surfaces), y 0.04..0.44
box((0, 0.24, 0), (0.275, 0.20, 0.275),
    RM(px='panel_px', nx='panel_nx', pz='panel_pz', nz='panel_nz',
       top='core_top', bottom='core_bottom'), b=0.012, part='body')
# 4 corner reinforcement posts, y 0.03..0.46, out to +-0.30
for sx in (1, -1):
    for sz in (1, -1):
        box((0.265 * sx, 0.245, 0.265 * sz), (0.035, 0.215, 0.035),
            RM(sides='post_sides', top='post_caps', bottom='post_caps'),
            b=0.008, part='post')
# bottom skirt, y 0..0.05
box((0, 0.025, 0), (0.30, 0.025, 0.30),
    RM(sides='skirt_sides', top='hidden', bottom='skirt_bottom'),
    b=0.008, part='skirt')
# lid rim, y 0.45..0.50, slight overhang to +-0.305
box((0, 0.475, 0), (0.305, 0.025, 0.305),
    RM(sides='rim_sides', top='rim_top', bottom='hidden'),
    b=0.010, part='lid_rim')
# lid top plate, y 0.493..0.517
box((0, 0.505, 0), (0.23, 0.012, 0.23),
    RM(sides='lid_sides', top='lid_top', bottom='hidden'),
    b=0.006, part='lid_plate')
# two protruding handles on +-X (2 posts + chamfered bar each)
for sx in (1, -1):
    for zz in (0.09, -0.09):
        box((0.30 * sx, 0.30, zz), (0.025, 0.015, 0.015),
            RM(every='handle_posts'), b=0.0, part='handle')
    box((0.318 * sx, 0.30, 0), (0.013, 0.016, 0.115),
        RM(every='handle_bar'), b=0.005, part='handle')
# two latch plates on the front (+Z), tucked under the rim
for lx in (0.12, -0.12):
    box((lx, 0.415, 0.285), (0.032, 0.045, 0.012),
        RM(pz='latch_front', sides='handle_posts',
           top='handle_posts', bottom='handle_posts'),
        b=0.005, part='latch')

# ------------------------------------------------------------ UV mapping
UDIR = {('x', 1): (0, 0, -1), ('x', -1): (0, 0, 1),
        ('z', 1): (1, 0, 0), ('z', -1): (-1, 0, 0),
        ('y', 1): (1, 0, 0), ('y', -1): (1, 0, 0)}
VDIR = {('x', 1): (0, 1, 0), ('x', -1): (0, 1, 0),
        ('z', 1): (0, 1, 0), ('z', -1): (0, 1, 0),
        ('y', 1): (0, 0, -1), ('y', -1): (0, 0, 1)}
AUTO = {'handle_bar', 'handle_posts', 'post_caps', 'hidden', 'bevel_strip'}

def face_uv(f):
    x0, y0, x1, y1 = A.regions[f['region']]
    vs = f['vs']
    if f['axsg'] is not None:
        U = np.array(UDIR[f['axsg']], float)
        V = np.array(VDIR[f['axsg']], float)
    else:
        best = None
        for i in range(len(vs)):
            e = vs[(i + 1) % len(vs)] - vs[i]
            L = np.linalg.norm(e)
            if best is None or L > best[0]:
                best = (L, e / L)
        U = best[1]
        V = np.cross(f['n'], U)
    us = np.array([np.dot(v, U) for v in vs])
    bs = np.array([np.dot(v, V) for v in vs])
    # match long face axis to long region axis for shared/trim regions
    if f['axsg'] is None or f['region'] in AUTO:
        if ((y1 - y0) > (x1 - x0)) != ((bs.max() - bs.min()) > (us.max() - us.min())):
            us, bs = bs, us
    a = (us - us.min()) / max(us.max() - us.min(), 1e-9)
    b = (bs - bs.min()) / max(bs.max() - bs.min(), 1e-9)
    pad = 2.0
    u = (x0 + pad + a * ((x1 - x0) - 2 * pad)) / TEX
    v = 1.0 - ((y1 - pad) - b * ((y1 - y0) - 2 * pad)) / TEX
    return list(zip(u, v))

def write_obj():
    tris = 0
    with open(os.path.join(OUT, 'crate_blind.obj'), 'w') as o:
        o.write('# Hero sci-fi supply crate -- blind procedural build\n')
        o.write('# textures: crate_albedo.png, crate_normal.png (tangent, OpenGL +Y),'
                ' crate_roughness.png\n')
        o.write('mtllib crate_blind.mtl\n')
        o.write('o crate_hero\n')
        o.write('usemtl crate_mat\n')
        vi = ti = ni = 0
        cur = None
        for f in faces:
            if f['part'] != cur:
                o.write('g %s\n' % f['part'])
                cur = f['part']
            uvs = face_uv(f)
            for v in f['vs']:
                o.write('v %.5f %.5f %.5f\n' % tuple(v))
            for (u, vv) in uvs:
                o.write('vt %.5f %.5f\n' % (u, vv))
            o.write('vn %.4f %.4f %.4f\n' % tuple(f['n']))
            ni += 1
            m = len(f['vs'])
            for t in range(1, m - 1):
                idx = (0, t, t + 1)
                o.write('f ' + ' '.join('%d/%d/%d' % (vi + 1 + q, ti + 1 + q, ni)
                                        for q in idx) + '\n')
                tris += 1
            vi += m
            ti += m
    with open(os.path.join(OUT, 'crate_blind.mtl'), 'w') as o:
        o.write('newmtl crate_mat\n')
        o.write('Ka 1.000 1.000 1.000\nKd 1.000 1.000 1.000\nKs 0.200 0.200 0.200\n')
        o.write('Ns 64\nd 1.0\nillum 2\n')
        o.write('map_Kd crate_albedo.png\n')
        o.write('map_Pr crate_roughness.png\n')
        o.write('map_Bump -bm 1.0 crate_normal.png\n')
        o.write('norm crate_normal.png\n')
        o.write('# crate_normal.png is tangent-space, OpenGL convention (green = +V)\n')
    return tris

# ------------------------------------------------------------- tex utils
def _seed(name):
    return zlib.crc32(name.encode()) & 0xffffffff

def vnoise(h, w, cell, seed):
    rng = np.random.default_rng(seed)
    gh = max(2, int(np.ceil(h / cell)) + 1)
    gw = max(2, int(np.ceil(w / cell)) + 1)
    g = (rng.random((gh, gw)) * 255).astype(np.uint8)
    im = Image.fromarray(g, 'L').resize((w, h), Image.BILINEAR)
    return np.asarray(im, np.float32) / 255.0

def anoise(h, w, cy, cx, seed):
    """Anisotropic value noise (cell sizes per axis) for streaks."""
    rng = np.random.default_rng(seed)
    gh = max(2, int(np.ceil(h / cy)) + 1)
    gw = max(2, int(np.ceil(w / cx)) + 1)
    g = (rng.random((gh, gw)) * 255).astype(np.uint8)
    im = Image.fromarray(g, 'L').resize((w, h), Image.BILINEAR)
    return np.asarray(im, np.float32) / 255.0

def fnoise(h, w, seed, cells=(48, 12, 4), amps=(1.0, 0.5, 0.25)):
    t = np.zeros((h, w), np.float32)
    s = 0.0
    for i, (c, a) in enumerate(zip(cells, amps)):
        t += a * vnoise(h, w, c, seed + i)
        s += a
    return t / s

def _blur1(a, r, axis):
    if r <= 0:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    p = np.pad(a, pad, mode='edge')
    c = np.cumsum(p, axis=axis, dtype=np.float64)
    k = 2 * r + 1
    n = a.shape[axis]
    hi = [slice(None)] * a.ndim
    hi[axis] = slice(k, k + n)
    lo = [slice(None)] * a.ndim
    lo[axis] = slice(0, n)
    return ((c[tuple(hi)] - c[tuple(lo)]) / k).astype(np.float32)

def blur(a, r):
    return _blur1(_blur1(a, r, 0), r, 1)

def lmask(w, h, fn):
    im = Image.new('L', (w, h), 0)
    fn(ImageDraw.Draw(im))
    return np.asarray(im, np.float32) / 255.0

def edge_dist(h, w):
    yy, xx = np.mgrid[0:h, 0:w]
    return np.minimum(np.minimum(xx, w - 1 - xx),
                      np.minimum(yy, h - 1 - yy)).astype(np.float32)

ALB = np.zeros((TEX, TEX, 3), np.float32); ALB[:] = (72, 76, 72)
HGT = np.full((TEX, TEX), 0.5, np.float32)
RGH = np.full((TEX, TEX), 0.60, np.float32)

def comp(dst, color, m):
    dst[:] = dst * (1.0 - m[..., None]) + np.asarray(color, np.float32) * m[..., None]

def comps(dst, val, m):
    dst[:] = dst * (1.0 - m) + val * m

def region(name):
    x0, y0, x1, y1 = A.regions[name]
    w, h = x1 - x0, y1 - y0
    return (ALB[y0:y1, x0:x1], HGT[y0:y1, x0:x1], RGH[y0:y1, x0:x1],
            w, h, _seed(name))

PAINT = (77, 88, 79)
PAINT_LT = (95, 107, 96)
PAINT_DK = (56, 63, 58)
GUN = (62, 68, 66)
METAL = (152, 150, 143)
YEL = (198, 160, 46)
BLK = (40, 40, 42)
ORANGE = (192, 94, 38)
WHITE = (204, 206, 200)
RUBBER = (38, 40, 42)
DARK = (50, 52, 51)

SEG = {'0': 'abcdef', '1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc',
       '5': 'afgcd', '6': 'afgedc', '7': 'abc', '8': 'abcdefg', '9': 'abfgcd'}

def seg_rects(x, y, w, h, t):
    return {'a': (x + t, y, x + w - t, y + t),
            'b': (x + w - t, y + t, x + w, y + h / 2 - t / 2),
            'c': (x + w - t, y + h / 2 + t / 2, x + w, y + h - t),
            'd': (x + t, y + h - t, x + w - t, y + h),
            'e': (x, y + h / 2 + t / 2, x + t, y + h - t),
            'f': (x, y + t, x + t, y + h / 2 - t / 2),
            'g': (x + t, y + h / 2 - t / 2, x + w - t, y + h / 2 + t / 2)}

def draw_digits(d, text, x, y, dw, dh, t, gap):
    for ch in text:
        if ch in SEG:
            rr = seg_rects(x, y, dw, dh, t)
            for s in SEG[ch]:
                d.rectangle(rr[s], fill=255)
        x += dw + gap

def scratches(a, r, hh, w, h, seed, count, strength=0.55):
    def dscr(d):
        rs = np.random.default_rng(seed)
        for _ in range(count):
            px, py = rs.random() * w, rs.random() * h
            ang = rs.random() * np.pi
            L = 10 + rs.random() * 40
            d.line((px, py, px + np.cos(ang) * L, py + np.sin(ang) * L),
                   fill=255, width=1)
    sc = lmask(w, h, dscr)
    comp(a, METAL, sc * strength)
    r[:] = np.where(sc > 0.3, 0.36, r)
    hh -= sc * 0.02

def edge_wear(a, r, hh, w, h, seed, width=11, thresh=0.38, amt=1.0):
    d = edge_dist(h, w)
    n = fnoise(h, w, seed, (24, 8), (1.0, 0.6))
    m = np.clip(1 - d / width, 0, 1) * np.clip((n - thresh) * 2.6, 0, 1) * amt
    comp(a, METAL, m)
    comps(r, 0.32, m)
    hh -= m * 0.03

def grime_bottom(a, r, w, h, seed, amt=0.5):
    yy = np.mgrid[0:h, 0:w][0]
    g = (yy / max(h - 1, 1)) ** 2 * (0.35 + 0.4 * fnoise(h, w, seed, (32, 8), (1, 0.5)))
    g *= amt
    a *= (1 - g[..., None] * 0.6)
    r += g * 0.25

# --------------------------------------------------------------- painters
def paint_panel(name, variant):
    a, hh, r, w, h, sd = region(name)
    yy, xx = np.mgrid[0:h, 0:w]
    n1 = fnoise(h, w, sd)
    a[:] = np.asarray(PAINT, np.float32) * (0.82 + 0.36 * n1[..., None])
    r[:] = 0.58 + (n1 - 0.5) * 0.16
    # recessed frame: darker 14 px border
    inner = lmask(w, h, lambda d: d.rectangle((14, 14, w - 15, h - 15), fill=255))
    comp(a, PAINT_DK, (1 - inner) * 0.7)
    # groove seam ring
    ring = lmask(w, h, lambda d: d.rectangle((16, 16, w - 17, h - 17),
                                             outline=255, width=3))
    ringb = blur(ring, 1)
    comp(a, (30, 32, 30), ringb * 0.8)
    hh -= ringb * 0.22
    r[:] = np.where(ringb > 0.2, 0.68, r)
    # raised inner plate
    plate = lmask(w, h, lambda d: d.rectangle((30, 30, w - 31, h - 31), fill=255))
    hh += blur(plate, 2) * 0.10
    comp(a, PAINT_LT, plate * 0.35)
    # two vertical sub-panel seams
    seams = lmask(w, h, lambda d: (d.line((w // 3, 34, w // 3, h - 35), fill=255, width=2),
                                   d.line((2 * w // 3, 34, 2 * w // 3, h - 35), fill=255, width=2)))
    sb = blur(seams, 1)
    comp(a, (34, 36, 34), sb * 0.6)
    hh -= sb * 0.12
    # rivets
    pts = [(22, 22), (w - 23, 22), (22, h - 23), (w - 23, h - 23),
           (w // 2, 22), (w // 2, h - 23)]
    riv = lmask(w, h, lambda d: [d.ellipse((px - 4, py - 4, px + 4, py + 4), fill=255)
                                 for px, py in pts])
    comp(a, (120, 122, 116), riv * 0.9)
    hh += blur(riv, 1) * 0.28
    r[:] = np.where(riv > 0.3, 0.38, r)
    # markings
    if variant == 'hazard':
        band = ((yy > h * 0.64) & (yy < h * 0.84) &
                (xx > 32) & (xx < w - 32)).astype(np.float32)
        stripe = (((xx + yy) // 14) % 2).astype(np.float32)
        comp(a, YEL, band * (1 - stripe))
        comp(a, BLK, band * stripe)
        r[:] = np.where(band > 0, 0.50 + stripe * 0.06, r)
    elif variant == 'digits':
        dm = lmask(w, h, lambda d: draw_digits(
            d, '04', int(w * 0.56), int(h * 0.28), int(w * 0.13), int(h * 0.36),
            max(3, int(h * 0.045)), int(w * 0.05)))
        comp(a, ORANGE, dm * 0.92)
        r[:] = np.where(dm > 0.3, 0.50, r)
        lb = lmask(w, h, lambda d: (
            d.rectangle((int(w * 0.12), int(h * 0.30), int(w * 0.40), int(h * 0.42)),
                        outline=255, width=2),
            d.rectangle((int(w * 0.12), int(h * 0.52), int(w * 0.30), int(h * 0.58)),
                        fill=255)))
        comp(a, WHITE, lb * 0.85)
    elif variant == 'barcode':
        rngb = np.random.default_rng(sd + 99)
        def dbars(d):
            bx = int(w * 0.14)
            while bx < int(w * 0.55):
                bw = int(rngb.integers(2, 6))
                if rngb.random() > 0.4:
                    d.rectangle((bx, int(h * 0.24), bx + bw, int(h * 0.44)), fill=255)
                bx += bw + int(rngb.integers(2, 5))
            d.rectangle((int(w * 0.14), int(h * 0.50), int(w * 0.44), int(h * 0.55)),
                        fill=255)
        bc = lmask(w, h, dbars)
        comp(a, WHITE, bc * 0.9)
    elif variant == 'chevron':
        def dchev(d):
            cw = int(w * 0.11)
            cy = int(h * 0.5)
            for i in range(3):
                x = int(w * 0.28) + i * int(cw * 1.5)
                d.polygon([(x, cy - 38), (x + cw, cy - 38), (x + cw + 30, cy),
                           (x + cw, cy + 38), (x, cy + 38), (x + 30, cy)], fill=255)
        ch = lmask(w, h, dchev)
        comp(a, WHITE, ch * 0.8)
    scratches(a, r, hh, w, h, sd + 7, 18)
    edge_wear(a, r, hh, w, h, sd + 31)
    grime_bottom(a, r, w, h, sd + 55)


def paint_lid_top():
    a, hh, r, w, h, sd = region('lid_top')
    n1 = fnoise(h, w, sd)
    a[:] = np.asarray(PAINT, np.float32) * (0.84 + 0.34 * n1[..., None])
    r[:] = 0.58 + (n1 - 0.5) * 0.16
    cross = lmask(w, h, lambda d: (d.line((w // 2, 14, w // 2, h - 15), fill=255, width=4),
                                   d.line((14, h // 2, w - 15, h // 2), fill=255, width=4)))
    cb = blur(cross, 1)
    comp(a, (32, 34, 32), cb * 0.7)
    hh -= cb * 0.20
    ring = lmask(w, h, lambda d: d.ellipse((w * 0.22, h * 0.22, w * 0.78, h * 0.78),
                                           outline=255, width=6))
    comp(a, ORANGE, ring * 0.85)
    r[:] = np.where(ring > 0.3, 0.50, r)
    dot = lmask(w, h, lambda d: d.ellipse((w * 0.47, h * 0.47, w * 0.53, h * 0.53), fill=255))
    comp(a, ORANGE, dot * 0.85)
    dm = lmask(w, h, lambda d: draw_digits(
        d, '04', int(w * 0.60), int(h * 0.62), int(w * 0.11), int(h * 0.22),
        max(3, int(h * 0.03)), int(w * 0.04)))
    comp(a, WHITE, dm * 0.9)
    vents = lmask(w, h, lambda d: [d.rectangle((int(w * 0.10), int(h * (0.12 + 0.05 * i)),
                                                int(w * 0.30), int(h * (0.14 + 0.05 * i))),
                                               fill=255) for i in range(3)])
    comp(a, (40, 44, 42), vents * 0.8)
    hh -= blur(vents, 1) * 0.10
    pts = [(20, 20), (w - 21, 20), (20, h - 21), (w - 21, h - 21)]
    bolts = lmask(w, h, lambda d: [d.ellipse((px - 6, py - 6, px + 6, py + 6), fill=255)
                                   for px, py in pts])
    comp(a, (126, 128, 122), bolts * 0.9)
    hh += blur(bolts, 1) * 0.30
    r[:] = np.where(bolts > 0.3, 0.38, r)
    scratches(a, r, hh, w, h, sd + 7, 30)
    edge_wear(a, r, hh, w, h, sd + 31, width=13)
    blot = np.clip((fnoise(h, w, sd + 77, (64, 16), (1, 0.5)) - 0.60) * 4, 0, 1)
    a *= (1 - blot[..., None] * 0.22)
    r += blot * 0.15


def paint_rim_top():
    a, hh, r, w, h, sd = region('rim_top')
    n1 = fnoise(h, w, sd)
    a[:] = np.asarray(PAINT_DK, np.float32) * (0.9 + 0.3 * n1[..., None])
    r[:] = 0.55 + (n1 - 0.5) * 0.14
    pts = [(16, 16), (w - 17, 16), (16, h - 17), (w - 17, h - 17),
           (w // 2, 16), (w // 2, h - 17), (16, h // 2), (w - 17, h // 2)]
    bolts = lmask(w, h, lambda d: [d.ellipse((px - 5, py - 5, px + 5, py + 5), fill=255)
                                   for px, py in pts])
    comp(a, (126, 128, 122), bolts * 0.9)
    hh += blur(bolts, 1) * 0.28
    r[:] = np.where(bolts > 0.3, 0.38, r)
    sq = lmask(w, h, lambda d: d.rectangle((int(w * 0.16), int(h * 0.16),
                                            int(w * 0.84), int(h * 0.84)),
                                           outline=255, width=3))
    sqb = blur(sq, 1)
    comp(a, (30, 32, 30), sqb * 0.7)
    hh -= sqb * 0.18
    scratches(a, r, hh, w, h, sd + 7, 22)
    edge_wear(a, r, hh, w, h, sd + 31, width=10, thresh=0.34)


def paint_hazard_strip():
    a, hh, r, w, h, sd = region('rim_sides')
    yy, xx = np.mgrid[0:h, 0:w]
    stripe = (((xx + yy) // 13) % 2).astype(np.float32)
    comp(a, YEL, (1 - stripe))
    comp(a, BLK, stripe)
    r[:] = 0.50 + stripe * 0.08
    hh += (fnoise(h, w, sd, (12, 4), (1, 0.5)) - 0.5) * 0.03
    spec = np.clip((fnoise(h, w, sd + 3, (10, 3), (1, 0.6)) - 0.68) * 5, 0, 1)
    comp(a, METAL, spec)
    comps(r, 0.32, spec)
    grime_bottom(a, r, w, h, sd + 5, amt=0.4)


def paint_skirt_sides():
    a, hh, r, w, h, sd = region('skirt_sides')
    st = anoise(h, w, 12, 40, sd)
    a[:] = np.asarray((52, 55, 55), np.float32) * (0.8 + 0.5 * st[..., None])
    r[:] = 0.50 + (st - 0.5) * 0.3
    dents = np.clip((fnoise(h, w, sd + 2, (16, 5), (1, 0.6)) - 0.62) * 4, 0, 1)
    hh -= blur(dents, 1) * 0.12
    a *= (1 - dents[..., None] * 0.15)
    edge_wear(a, r, hh, w, h, sd + 31, width=6, thresh=0.30)
    a *= 0.9


def paint_posts():
    a, hh, r, w, h, sd = region('post_sides')
    n1 = fnoise(h, w, sd, (24, 8, 3), (1, 0.5, 0.3))
    a[:] = np.asarray(GUN, np.float32) * (0.85 + 0.3 * n1[..., None])
    r[:] = 0.60 + (n1 - 0.5) * 0.14
    chips = np.clip((fnoise(h, w, sd + 9, (20, 6), (1, 0.7)) - 0.60) * 5, 0, 1)
    comp(a, METAL, chips)
    comps(r, 0.33, chips)
    hh -= blur(chips, 1) * 0.06
    gro = lmask(w, h, lambda d: (d.line((4, int(h * 0.25), w - 5, int(h * 0.25)), fill=255, width=3),
                                 d.line((4, int(h * 0.75), w - 5, int(h * 0.75)), fill=255, width=3)))
    gb = blur(gro, 1)
    comp(a, (30, 32, 30), gb * 0.7)
    hh -= gb * 0.16
    pts = [(w // 2, 20), (w // 2, h - 21)]
    bolts = lmask(w, h, lambda d: [d.ellipse((px - 5, py - 5, px + 5, py + 5), fill=255)
                                   for px, py in pts])
    comp(a, (130, 132, 126), bolts * 0.9)
    hh += blur(bolts, 1) * 0.28
    r[:] = np.where(bolts > 0.3, 0.38, r)
    edge_wear(a, r, hh, w, h, sd + 31, width=7, thresh=0.30)
    grime_bottom(a, r, w, h, sd + 55, amt=0.35)


def paint_metal(name, base=METAL, rough=0.35):
    a, hh, r, w, h, sd = region(name)
    n1 = fnoise(h, w, sd, (16, 5), (1, 0.5))
    a[:] = np.asarray(base, np.float32) * (0.85 + 0.3 * n1[..., None])
    r[:] = rough + (n1 - 0.5) * 0.12
    st = anoise(h, w, 48, 3, sd + 4)
    a *= (0.92 + 0.16 * st[..., None])
    hh += (n1 - 0.5) * 0.02


def paint_dark(name):
    a, hh, r, w, h, sd = region(name)
    n1 = fnoise(h, w, sd, (24, 8), (1, 0.5))
    a[:] = np.asarray(DARK, np.float32) * (0.9 + 0.2 * n1[..., None])
    r[:] = 0.78 + (n1 - 0.5) * 0.08
    hh += (n1 - 0.5) * 0.015


def paint_bar():
    a, hh, r, w, h, sd = region('handle_bar')
    yy, xx = np.mgrid[0:h, 0:w]
    n1 = fnoise(h, w, sd, (12, 4), (1, 0.5))
    a[:] = np.asarray(RUBBER, np.float32) * (0.85 + 0.4 * n1[..., None])
    r[:] = 0.85 + (n1 - 0.5) * 0.08
    kn = (((xx // 4 + yy // 4) % 2)).astype(np.float32)
    hh += (kn - 0.5) * 0.05
    a *= (0.94 + 0.12 * kn[..., None])
    wearm = np.clip((n1 - 0.62) * 4, 0, 1)
    comp(a, (70, 72, 72), wearm * 0.7)
    comps(r, 0.55, wearm)


def paint_latch():
    a, hh, r, w, h, sd = region('latch_front')
    n1 = fnoise(h, w, sd, (12, 4), (1, 0.5))
    a[:] = np.asarray((140, 140, 134), np.float32) * (0.85 + 0.3 * n1[..., None])
    r[:] = 0.33 + (n1 - 0.5) * 0.10
    plate = lmask(w, h, lambda d: d.rectangle((6, 6, w - 7, h - 7), fill=255))
    hh += blur(plate, 2) * 0.14
    ind = lmask(w, h, lambda d: d.rectangle((int(w * 0.3), int(h * 0.12),
                                             int(w * 0.7), int(h * 0.24)), fill=255))
    comp(a, ORANGE, ind * 0.9)
    pts = [(12, h - 14), (w - 13, h - 14)]
    bolts = lmask(w, h, lambda d: [d.ellipse((px - 4, py - 4, px + 4, py + 4), fill=255)
                                   for px, py in pts])
    comp(a, (100, 102, 98), bolts * 0.9)
    hh += blur(bolts, 1) * 0.25
    edge_wear(a, r, hh, w, h, sd + 31, width=5, thresh=0.34)


def paint_lid_sides():
    a, hh, r, w, h, sd = region('lid_sides')
    n1 = fnoise(h, w, sd, (24, 6), (1, 0.5))
    a[:] = np.asarray(PAINT, np.float32) * (0.84 + 0.32 * n1[..., None])
    r[:] = 0.56 + (n1 - 0.5) * 0.14
    scratches(a, r, hh, w, h, sd + 7, 10)
    edge_wear(a, r, hh, w, h, sd + 31, width=6, thresh=0.32)


def paint_bevel():
    a, hh, r, w, h, sd = region('bevel_strip')
    st = anoise(h, w, 64, 3, sd)
    n1 = fnoise(h, w, sd + 1, (16, 4), (1, 0.5))
    a[:] = np.asarray(METAL, np.float32) * (0.82 + 0.3 * (0.5 * st + 0.5 * n1)[..., None])
    r[:] = 0.30 + (n1 - 0.5) * 0.12
    hh += (n1 - 0.5) * 0.02

# ------------------------------------------------------------------ main
def paint_all():
    paint_panel('panel_px', 'hazard')
    paint_panel('panel_nx', 'barcode')
    paint_panel('panel_pz', 'digits')
    paint_panel('panel_nz', 'chevron')
    paint_lid_top()
    paint_rim_top()
    paint_hazard_strip()
    paint_skirt_sides()
    paint_posts()
    paint_metal('post_caps')
    paint_metal('handle_posts')
    paint_bar()
    paint_latch()
    paint_lid_sides()
    paint_bevel()
    paint_dark('core_top')
    paint_dark('core_bottom')
    paint_dark('skirt_bottom')
    paint_dark('hidden')

def build_normal():
    """Tangent-space normal map, OpenGL (+Y = +V). Image y is down but
    v = 1 - y/TEX, so dh/dv = -dh/dy_img, hence ny = +NSTR * dh/dy_img."""
    nrm = np.zeros((TEX, TEX, 3), np.float32)
    nrm[..., 0] = 0.5
    nrm[..., 1] = 0.5
    nrm[..., 2] = 1.0
    for name, (x0, y0, x1, y1) in A.regions.items():
        hsl = HGT[y0:y1, x0:x1]
        gy, gx = np.gradient(hsl)
        nx = -gx * NSTR
        ny = gy * NSTR
        ln = np.sqrt(nx * nx + ny * ny + 1.0)
        nrm[y0:y1, x0:x1, 0] = (nx / ln) * 0.5 + 0.5
        nrm[y0:y1, x0:x1, 1] = (ny / ln) * 0.5 + 0.5
        nrm[y0:y1, x0:x1, 2] = (1.0 / ln) * 0.5 + 0.5
    return nrm

def main():
    tris = write_obj()
    paint_all()
    nrm = build_normal()
    Image.fromarray(np.clip(ALB + 0.5, 0, 255).astype(np.uint8), 'RGB').save(
        os.path.join(OUT, 'crate_albedo.png'))
    Image.fromarray(np.clip(nrm * 255.0 + 0.5, 0, 255).astype(np.uint8), 'RGB').save(
        os.path.join(OUT, 'crate_normal.png'))
    Image.fromarray(np.clip(RGH * 255.0 + 0.5, 0, 255).astype(np.uint8), 'L').save(
        os.path.join(OUT, 'crate_roughness.png'))
    nverts = sum(len(f['vs']) for f in faces)
    cover = sum((x1 - x0) * (y1 - y0)
                for x0, y0, x1, y1 in A.regions.values()) / float(TEX * TEX)
    print('faces (polys):   %d' % len(faces))
    print('triangles:       %d' % tris)
    print('verts written:   %d' % nverts)
    print('uv regions:      %d (intended islands)' % len(A.regions))
    print('atlas coverage:  %.1f%%' % (100 * cover))
    print('outputs: crate_blind.obj, crate_blind.mtl, crate_albedo.png,')
    print('         crate_normal.png (tangent, OpenGL +Y), crate_roughness.png')

if __name__ == '__main__':
    main()
