"""Deterministic skeleton renders.

Renders exist to be LOOKED at, and to be looked at they must show what
the numbers found: the frame with the worst pop, the foot that slid, the
joint that went through the floor. So every frame draws the skeleton
plus the evidence — COM, support, floor, and a marker on the flagged
joint.

Software rasterizer via Pillow: no GPU, no OpenGL, byte-identical for
identical input.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

BG = (247, 247, 245)
INK = (46, 48, 51)
BONE = (92, 108, 124)
ACCENT = (183, 86, 62)
COM_C = (46, 110, 88)
GRID = (219, 219, 214)


_FOLD = {ord(a): b for a, b in [("—", "-"), ("–", "-"),
                                  ("·", "-"), ("…", "...")]}


def _ascii(text: str) -> str:
    """PIL's default bitmap font has no em-dash: fold to ASCII so burned
    labels can never show tofu boxes (found on the first track render)."""
    return str(text).translate(_FOLD)


def _font(size: int = 13):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _project(pts: np.ndarray, up: str, view: str) -> np.ndarray:
    """World mm -> 2D drawing coords (x right, y up), orthographic."""
    k = {"x": 0, "y": 1, "z": 2}[up.lower()]
    h = [i for i in (0, 1, 2) if i != k]
    if view == "front":
        return np.stack([pts[..., h[0]], pts[..., k]], axis=-1)
    if view == "side":
        return np.stack([pts[..., h[1]], pts[..., k]], axis=-1)
    if view == "top":
        return np.stack([pts[..., h[0]], pts[..., h[1]]], axis=-1)
    raise ValueError(f"unknown view {view!r}")


def render_frames(clip, pos: np.ndarray, com: np.ndarray, out_dir: Path,
                  frames: list[int], up: str, floor_mm: float,
                  view: str = "side", size: int = 640,
                  marks: dict[int, list[int]] | None = None) -> list[str]:
    """One PNG per requested frame. `marks` maps frame -> joint indices
    to circle in red (the evidence for a finding)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    marks = marks or {}

    # Scale is fixed for the whole clip (so poses stay comparable frame to
    # frame) but the camera TRACKS the character horizontally. Framing on
    # the clip's full travel instead would size every frame to the walk's
    # 1.8 m of ground covered and leave the skeleton a few pixels tall.
    all2d = _project(pos, up, view)
    per_frame_span = (all2d.max(axis=1) - all2d.min(axis=1)).max()
    span = float(max(per_frame_span, 1.0)) * 1.25
    vlo = float(all2d[..., 1].min())
    vhi = float(all2d[..., 1].max())
    cy_fixed = (vlo + vhi) / 2.0                 # vertical framing is shared
    pad = size * 0.08

    bones = [(i, clip.joints.index(j.parent))
             for i, j in enumerate(clip.joints) if j.parent is not None]
    written = []
    f13, f11 = _font(13), _font(11)

    for f in frames:
        img = Image.new("RGB", (size, size), BG)
        d = ImageDraw.Draw(img)

        p2 = _project(pos[f], up, view)
        cx = float((p2[:, 0].min() + p2[:, 0].max()) / 2.0)   # track the body
        cy = cy_fixed

        def to_px(p, cx=cx, cy=cy):
            s = (size - 2 * pad) / span
            return (pad + (p[0] - cx) * s + (size - 2 * pad) / 2,
                    size - (pad + (p[1] - cy) * s + (size - 2 * pad) / 2))

        # floor line (in the two vertical views)
        if view in ("front", "side"):
            y = to_px((cx, floor_mm))[1]
            d.line([(0, y), (size, y)], fill=GRID, width=2)
            d.text((6, y + 4), "floor", fill=GRID, font=f11)
        for a, b in bones:
            d.line([to_px(p2[a]), to_px(p2[b])], fill=BONE, width=3)
        for i in range(len(p2)):
            x, y = to_px(p2[i])
            d.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], fill=INK)

        # COM + its ground projection: the balance evidence
        c2 = _project(com[f:f + 1], up, view)[0]
        x, y = to_px(c2)
        d.ellipse([x - 5, y - 5, x + 5, y + 5], outline=COM_C, width=2)
        d.line([(x, y), (x, to_px((c2[0], floor_mm))[1])], fill=COM_C,
               width=1)

        for i in marks.get(f, []):
            x, y = to_px(p2[i])
            d.ellipse([x - 9, y - 9, x + 9, y + 9], outline=ACCENT, width=2)
            d.text((x + 12, y - 7), clip.joints[i].name, fill=ACCENT,
                   font=f11)

        d.text((10, 8), _ascii(f"{clip.source}  frame "
                               f"{f}/{clip.n_frames - 1}   "
                               f"t={f * clip.frame_time:.3f}s"),
               fill=INK, font=f13)
        d.text((10, 24), f"{view} view  ·  COM (green)  ·  mm  ·  "
                         f"{clip.fps:.1f} fps", fill=BONE, font=f11)

        name = f"frame_{f:04d}.png"
        img.save(out_dir / name)
        written.append(name)
    return written


def render_flight_arc(clip, pos: np.ndarray, com: np.ndarray,
                      flight: dict, out_path: Path, up: str,
                      floor_mm: float, g_mm_s2: float = 9810.0,
                      view: str = "side", size: int = 900) -> None:
    """THE picture for a jump: ghosted poses across the flight, the
    measured COM arc drawn solid, and the arc physics WOULD draw (same
    apex, 1 g) dashed beside it. A floaty flight and its fix stop being
    numbers and become two visibly different curves.

    Ghosts fade with time; the COM arc carries the gravity ratio as a
    burned-in label. Deterministic."""
    a, b = flight["frames"]
    n = b - a + 1
    picks = [a + round(i * (n - 1) / 6) for i in range(7)]

    all2d = _project(pos[a:b + 1], up, view)
    lo = all2d.reshape(-1, 2).min(axis=0)
    hi = all2d.reshape(-1, 2).max(axis=0)
    span = float(max(hi[0] - lo[0], hi[1] - lo[1], 1.0)) * 1.30
    cx = float((lo[0] + hi[0]) / 2)
    cy = float((lo[1] + hi[1]) / 2)
    pad = size * 0.07

    def to_px(p):
        s = (size - 2 * pad) / span
        return (pad + (p[0] - cx) * s + (size - 2 * pad) / 2,
                size - (pad + (p[1] - cy) * s + (size - 2 * pad) / 2))

    img = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(img)

    y_floor = to_px((cx, floor_mm))[1]
    d.line([(0, y_floor), (size, y_floor)], fill=GRID, width=2)
    d.text((6, y_floor + 4), "floor", fill=GRID, font=_font(11))

    bones = [(i, clip.joints.index(j.parent))
             for i, j in enumerate(clip.joints) if j.parent is not None]
    for gi, f in enumerate(picks):
        t = gi / max(len(picks) - 1, 1)
        shade = tuple(int(BG[k] + (BONE[k] - BG[k]) * (0.25 + 0.75 * t))
                      for k in range(3))
        p2 = _project(pos[f], up, view)
        for i, j in bones:
            d.line([to_px(p2[i]), to_px(p2[j])], fill=shade, width=3)

    # the measured COM arc, with a dot per frame: time made visible
    c2 = _project(com[a:b + 1], up, view)
    d.line([to_px(p) for p in c2], fill=ACCENT, width=3)
    for p in c2:
        x, y = to_px(p)
        d.ellipse([x - 2.5, y - 2.5, x + 2.5, y + 2.5], fill=ACCENT)

    # The arc physics would draw. In space both parabolas have the same
    # shape — floatiness lives in TIME — so the honest reference keeps
    # the takeoff velocity and the apex and lands where 1 g says:
    # T_phys/T_actual = sqrt(g_ratio), i.e. the reference arc is
    # sqrt(ratio) as wide. For a physical flight the two coincide.
    h0 = float(c2[0, 1])
    apex = float(c2[:, 1].max()) - h0
    x0, x1 = float(c2[0, 0]), float(c2[-1, 0])
    ratio = max(float(flight.get("gravity_ratio") or 1.0), 1e-3)
    x1_ref = x0 + (x1 - x0) * math.sqrt(ratio)
    ref = []
    for i in range(41):
        s = i / 40.0
        ref.append((x0 + (x1_ref - x0) * s,
                    h0 + 4.0 * apex * s * (1.0 - s)))
    for i in range(0, 40, 2):                      # dashed
        d.line([to_px(ref[i]), to_px(ref[i + 1])], fill=COM_C, width=3)
    xe, ye = to_px(ref[-1])
    d.ellipse([xe - 4, ye - 4, xe + 4, ye + 4], outline=COM_C, width=2)

    ratio = flight.get("gravity_ratio")
    d.text((10, 8), _ascii(f"{clip.source} - flight, frames {a}..{b} "
                           f"({flight['duration_s']}s)"),
           fill=INK, font=_font(14))
    d.text((10, 26), _ascii(
        f"measured COM arc (red): {ratio}x gravity   -   "
        f"1 g reference shape (green, dashed)   -   "
        f"apex +{flight['apex_rise_mm']} mm"),
        fill=BONE, font=_font(12))
    img.save(out_path)


def render_track(values: np.ndarray, out_path: Path, title: str,
                 ylabel: str, dt: float, marks: list[int] | None = None,
                 size: tuple[int, int] = (900, 260)) -> None:
    """A single-track plot (speed, height, jerk) with the flagged frames
    marked — a graph is how a time series is read, so draw one."""
    W, H = size
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    pad_l, pad_b, pad_t = 64, 30, 28
    plot_w, plot_h = W - pad_l - 16, H - pad_b - pad_t

    v = np.asarray(values, float)
    vmax = float(np.nanmax(v)) if v.size and np.isfinite(v).any() else 1.0
    vmax = vmax if vmax > 0 else 1.0
    n = len(v)

    def px(i, val):
        return (pad_l + plot_w * (i / max(n - 1, 1)),
                pad_t + plot_h * (1.0 - val / vmax))

    d.rectangle([pad_l, pad_t, pad_l + plot_w, pad_t + plot_h], outline=GRID)
    for frac in (0.0, 0.5, 1.0):
        y = pad_t + plot_h * (1 - frac)
        d.line([(pad_l, y), (pad_l + plot_w, y)], fill=GRID)
        d.text((6, y - 6), f"{vmax * frac:,.0f}", fill=BONE, font=_font(11))

    d.line([px(i, v[i]) for i in range(n)], fill=BONE, width=2)
    for f in (marks or []):
        if 0 <= f < n:
            x, y = px(f, v[f])
            d.line([(x, pad_t), (x, pad_t + plot_h)], fill=ACCENT)
            d.ellipse([x - 4, y - 4, x + 4, y + 4], outline=ACCENT, width=2)

    d.text((pad_l, 6), _ascii(title), fill=INK, font=_font(13))
    d.text((pad_l + plot_w - 110, pad_t + plot_h + 8),
           f"frames 0..{n - 1}  ({n * dt:.2f}s)", fill=BONE, font=_font(11))
    d.text((6, pad_t + plot_h + 8), ylabel, fill=BONE, font=_font(11))
    img.save(out_path)
