"""Lofts (transitions between stacked profiles) and curved-surface text."""

from __future__ import annotations

import math

from ..errors import BadArgumentError, fmt_num
from ..geom import Sketch, Solid, text, union


def loft(profiles, heights, slab: float = 0.02) -> Solid:
    """Smooth transition through CONVEX profiles stacked at given heights —
    funnels, ducts, adapters, tapering columns:

        loft([circle(d=40), ngon(6, d=28), circle(d=16)], [0, 30, 55])

    Each consecutive pair becomes the convex hull between the two sections,
    so profiles must be convex (a star or L-shape would bulge across its
    concavity — solidsight checks and refuses). Profiles may be translated
    sketches (offset lofts are fine)."""
    profiles = list(profiles)
    heights = [float(h) for h in heights]
    if len(profiles) < 2 or len(profiles) != len(heights):
        raise BadArgumentError(
            f"loft() needs matching lists of >= 2 profiles and heights "
            f"(got {len(profiles)} profiles, {len(heights)} heights)")
    if any(b <= a for a, b in zip(heights[:-1], heights[1:])):
        raise BadArgumentError(
            "loft() heights must strictly increase",
            suggestion=f"got {[fmt_num(h) for h in heights]}")
    for i, p in enumerate(profiles):
        if not isinstance(p, Sketch):
            raise BadArgumentError(
                f"loft() profile {i} is a {type(p).__name__}, not a Sketch")
        hull_area = Sketch(p.cross_section.hull(), "hull").area
        if hull_area > p.area * 1.001:
            raise BadArgumentError(
                f"loft() profile {i} is not convex (its convex hull is "
                f"{fmt_num(hull_area)} mm2 vs {fmt_num(p.area)} mm2)",
                suggestion="loft only supports convex sections; split the "
                           "shape into convex lofts and union them, or use "
                           "extrude with twist/scale_top for star-like forms")
    segments = []
    for i in range(len(profiles) - 1):
        # thin slabs centered on each section plane overlap between segments
        a = profiles[i].extrude(slab).translate(0, 0, heights[i] - slab / 2)
        b = (profiles[i + 1].extrude(slab)
             .translate(0, 0, heights[i + 1] - slab / 2))
        segments.append(a.hull_with(b))
    out = union(*segments)
    out.desc = (f"loft({len(profiles)} sections, "
                f"z {fmt_num(heights[0])}..{fmt_num(heights[-1])})")
    return out


def wrapped_text(string: str, d: float, size: float = 10.0,
                 depth: float = 1.0, outward: float = 0.5,
                 font: str | None = None) -> Solid:
    """Text wrapped around a cylinder of diameter d, as a TOOL centered on
    the +X side (text reads left-to-right when viewed from +X, running
    counter-clockwise). Rotate into place with .rotate(z=...) and position
    with .translate(0, 0, z).

        pot = pot - parts.wrapped_text("BASIL", d=90, size=12).translate(0, 0, 60)   # engrave
        pot = pot + parts.wrapped_text("BASIL", d=90, size=12,
                                       depth=0.3, outward=1.5).translate(0, 0, 60)   # emboss

    depth: how far the tool reaches INTO the surface. outward: how far it
    sticks OUT (increase it and shrink depth to emboss). The wrap covers
    arc = text_width / (d/2) radians; text wider than ~2/3 of the
    circumference is refused."""
    if depth <= 0 and outward <= 0:
        raise BadArgumentError("wrapped_text() needs depth or outward > 0")
    r = d / 2.0
    if r <= depth:
        raise BadArgumentError(
            f"wrapped_text() depth {fmt_num(depth)} must be smaller than "
            f"the radius {fmt_num(r)}")
    sk = text(string, size=size, font=font, halign="center", valign="center")
    b = sk.cross_section.bounds()
    width = b[2] - b[0]
    if width > 2 * math.pi * r * 0.66:
        raise BadArgumentError(
            f"wrapped_text() text is {fmt_num(width)} mm wide — more than "
            f"2/3 of the d={fmt_num(d)} circumference",
            suggestion="shorten the text, shrink size, or grow the cylinder")
    flat = sk.extrude(depth + outward)
    # refine so long glyph edges follow the curvature, then wrap:
    # x -> arc angle, extrusion z -> radial depth, y -> height (world Z)
    flat = flat.refine(max(0.8, size / 12))

    def wrap(x, y, z):
        radial = r - depth + z
        a = x / r
        return radial * math.cos(a), radial * math.sin(a), y

    out = flat.warp(wrap)
    out.desc = f"wrapped_text({string!r}, d={fmt_num(d)})"
    return out
