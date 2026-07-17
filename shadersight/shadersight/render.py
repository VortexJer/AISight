"""Deterministic material preview + the numerical plots that back it.

A sphere render is what a human asks for; the numbers are what an agent
reads. So produce both — the sphere so a person can sanity-check, the
plots (albedo vs angle, the BRDF lobe) so the physics is legible without
eyes. Software shaded, no GPU, byte-identical.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BG = (247, 247, 245)
INK = (46, 48, 51)
GRID = (222, 222, 217)
LINE = (92, 108, 124)
ACCENT = (183, 86, 62)
LIMIT = (150, 60, 60)


def _font(sz=12):
    try:
        return ImageFont.load_default(size=sz)
    except TypeError:
        return ImageFont.load_default()


def render_sphere(mat, path: Path, size: int = 420,
                  light_dir=(0.4, 0.5, 0.75)) -> None:
    """A lit sphere under one directional light + a constant ambient,
    shaded with the material's own BRDF. Tone-mapped and gamma-encoded
    so it reads like a preview, with the values it came from unclamped
    underneath (the report carries the real numbers)."""
    y, x = np.mgrid[0:size, 0:size].astype(float)
    nx = (x - size / 2) / (size / 2 * 0.92)
    ny = -(y - size / 2) / (size / 2 * 0.92)
    r2 = nx * nx + ny * ny
    inside = r2 <= 1.0
    nz = np.sqrt(np.maximum(1.0 - r2, 0.0))

    N = np.stack([nx, ny, nz], axis=-1)
    L = np.array(light_dir, float)
    L /= np.linalg.norm(L)
    V = np.array([0.0, 0.0, 1.0])

    img = np.zeros((size, size, 3))
    pts = np.nonzero(inside)
    n = N[pts]                                       # (M, 3), world = shade
    ndl = np.clip(n @ L, 0.0, 1.0)
    # evaluate the BRDF in the shading frame: rotate so this pixel's N is
    # +Z is overkill for a preview; the sphere IS the frame here since we
    # shade in world with N as the axis. Use the material's eval with
    # wi, wo expressed relative to N via a cheap tangent construction.
    val = np.zeros_like(n)
    for i in range(len(n)):
        wi_local, wo_local = _to_local(n[i], L, V)
        if wi_local[2] > 0 and wo_local[2] > 0:
            f = mat.eval(wi_local, wo_local)[0]
            val[i] = f * wi_local[2]
    ambient = mat.diffuse_albedo / np.pi * 0.15
    col = val * 3.0 + ambient
    col = col / (1.0 + col)                          # Reinhard
    col = np.clip(col, 0, 1) ** (1 / 2.2)
    img[pts] = col

    bg = np.array(BG) / 255.0
    frame = np.where(inside[:, :, None], img, bg)
    Image.fromarray((frame * 255).astype(np.uint8)).save(path)


def _to_local(n, L, V):
    """Express L and V in a tangent frame whose Z is n."""
    up = np.array([0.0, 1.0, 0.0]) if abs(n[1]) < 0.99 else \
        np.array([1.0, 0.0, 0.0])
    t = np.cross(up, n)
    t /= np.linalg.norm(t) + 1e-12
    b = np.cross(n, t)
    M = np.stack([t, b, n], axis=0)                  # world -> local rows
    return M @ L, M @ V


def render_albedo_curve(energy: dict, path: Path,
                        size=(760, 300)) -> None:
    """Directional albedo vs view angle, with the physical ceiling drawn.
    Above the red line, the material emits energy it never received."""
    W, H = size
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    pl, pt = 60, 30
    pw, ph = W - pl - 20, H - pt - 40

    rows = energy["per_view"]
    xs = [r["theta_deg"] for r in rows]
    ys = [r["max_channel"] for r in rows]
    ymax = max(1.15, max(ys) * 1.1)

    def px(t, v):
        return (pl + pw * t / 90.0, pt + ph * (1 - v / ymax))

    d.rectangle([pl, pt, pl + pw, pt + ph], outline=GRID)
    yline = px(0, 1.0)[1]
    d.line([(pl, yline), (pl + pw, yline)], fill=LIMIT, width=2)
    d.text((pl + pw - 118, yline - 15), "energy ceiling = 1.0",
           fill=LIMIT, font=_font(11))
    for frac in (0.0, 0.5, 1.0):
        v = ymax * frac
        yy = pt + ph * (1 - frac)
        d.text((6, yy - 6), f"{v:.2f}", fill=LINE, font=_font(11))

    d.line([px(t, v) for t, v in zip(xs, ys)], fill=LINE, width=2)
    for t, v in zip(xs, ys):
        c = ACCENT if v > 1.001 else LINE
        X, Y = px(t, v)
        d.ellipse([X - 3, Y - 3, X + 3, Y + 3], fill=c)

    d.text((pl, 8), "directional albedo vs view angle "
                    "(above the red line = non-physical)",
           fill=INK, font=_font(13))
    d.text((pl, pt + ph + 12), "view angle (deg from normal)",
           fill=LINE, font=_font(11))
    img.save(path)
