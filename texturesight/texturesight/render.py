"""Deterministic UV renders — the evidence for what the report says."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BG = (247, 247, 245)
INK = (46, 48, 51)
GRID = (222, 222, 217)
FLIP = (183, 62, 62)
STRETCH = (206, 138, 46)
ISLAND = [(92, 108, 124), (94, 122, 106), (140, 112, 132), (120, 118, 92),
          (102, 126, 132), (134, 106, 96), (108, 116, 148), (128, 128, 112)]


def _font(size: int = 12):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _setup(size: int, title: str, subtitle: str):
    img = Image.new("RGB", (size, size + 44), BG)
    d = ImageDraw.Draw(img)
    d.text((10, 8), title, fill=INK, font=_font(13))
    d.text((10, 25), subtitle, fill=(120, 124, 128), font=_font(11))
    top = 44
    for k in range(5):                              # the 0..1 square
        v = top + size * k / 4
        d.line([(0, v), (size, v)], fill=GRID)
        h = size * k / 4
        d.line([(h, top), (h, top + size)], fill=GRID)
    return img, d, top


def _tri_px(uv, size, top):
    return [(float(u) * size, top + (1.0 - float(v)) * size) for u, v in uv]


def render_uv_layout(mesh, uv_root: np.ndarray, path: Path,
                     flipped: list[int], stretched: list[int],
                     size: int = 760) -> None:
    """The UV layout, one colour per island, with the defective faces
    filled in. This is the picture a texture artist looks at — so draw
    it, but draw the FINDINGS on it, not just the wireframe."""
    roots = {r: i for i, r in enumerate(sorted(set(uv_root.tolist())))}
    img, d, top = _setup(
        size, f"{mesh.source} - UV layout",
        f"{len(roots)} island(s), {mesh.n_faces} faces  -  "
        f"red = flipped winding, orange = stretched >2:1")
    fl, st = set(flipped), set(stretched)

    for f in range(mesh.n_faces):
        pts = _tri_px(mesh.uvs[mesh.tri_uv[f]], size, top)
        if f in fl:
            d.polygon(pts, fill=FLIP)
        elif f in st:
            d.polygon(pts, fill=STRETCH)
        c = ISLAND[roots[uv_root[f]] % len(ISLAND)]
        d.line(pts + [pts[0]], fill=c, width=1)

    # label each island with its id (the report's island #N) at its
    # centroid — "scale island #4" is useless if nothing says which
    # blob IS island #4
    for r, i in roots.items():
        faces = [f for f in range(mesh.n_faces) if uv_root[f] == r]
        pts = mesh.uvs[mesh.tri_uv[faces]].reshape(-1, 2)
        cx = float(pts[:, 0].mean()) * size
        cy = top + (1.0 - float(pts[:, 1].mean())) * size
        d.text((cx - 8, cy - 7), f"#{i}", fill=INK, font=_font(13))
    img.save(path)


def render_density_map(mesh, density: np.ndarray, path: Path,
                       size: int = 760) -> None:
    """Texel density painted onto the UV layout: dark = starved,
    light = oversampled. Uneven density is invisible on a model and
    obvious here."""
    finite = density[np.isfinite(density) & (density > 0)]
    if finite.size == 0:
        lo = hi = 1.0
    else:
        lo, hi = float(np.percentile(finite, 2)), float(np.percentile(
            finite, 98))
    if hi - lo < 1e-9:
        hi = lo + 1.0
    img, d, top = _setup(
        size, f"{mesh.source} - texel density",
        f"dark = fewer texels/unit ({lo:.0f})  ->  light = more ({hi:.0f})")

    for f in range(mesh.n_faces):
        v = density[f]
        if not np.isfinite(v):
            col = (200, 60, 60)                  # degenerate: not a shade
        else:
            t = float(np.clip((v - lo) / (hi - lo), 0.0, 1.0))
            g = int(40 + 190 * t)
            col = (g, g, int(40 + 190 * t ** 0.8))
        d.polygon(_tri_px(mesh.uvs[mesh.tri_uv[f]], size, top), fill=col)
    img.save(path)
