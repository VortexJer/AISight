"""Lofts (transitions between stacked profiles) and curved-surface text."""

from __future__ import annotations

import math

from ..errors import BadArgumentError, fmt_num
from ..geom import Sketch, Solid, text, union


def loft_sections(sections, stations, axis: str = "x") -> Solid:
    """Ruled loft through closed 2D polylines with the SAME point count —
    the tool for one-piece styled bodies (car bodywork, boat hulls,
    aircraft fuselages) whose cross-sections are NOT convex (a car's
    section is concave at the shoulder where the greenhouse tumbles
    home; hull-based loft() would bloat straight across it).

        body = parts.loft_sections([sec0, sec1, ...], [x0, x1, ...])

    Each section is a list of (u, v) points, all sections the same
    length, corresponding points connect station to station (like the
    wooden stations of a boat buck). With axis="x" a section's (u, v)
    is (y, z): u across the width, v up. Points must be in consistent
    order (start at the same feature, e.g. bottom center, and go the
    same way around) — vertex k of one station welds to vertex k of the
    next, so a mismatched start point twists the body.

    End caps are triangulated exactly (non-convex OK). The result is a
    single watertight solid; carve arches, DLO insets and details out
    of it with booleans afterwards."""
    import numpy as np
    from manifold3d import Manifold, Mesh

    try:
        from manifold3d import triangulate as _triangulate
    except ImportError:
        _triangulate = None

    sections = [list(s) for s in sections]
    stations = [float(v) for v in stations]
    if len(sections) < 2 or len(sections) != len(stations):
        raise BadArgumentError(
            f"loft_sections() needs matching lists of >= 2 sections and "
            f"stations (got {len(sections)} sections, {len(stations)} "
            f"stations)")
    if any(b <= a for a, b in zip(stations[:-1], stations[1:])):
        raise BadArgumentError(
            "loft_sections() stations must strictly increase",
            suggestion=f"got {[fmt_num(v) for v in stations]}")
    n = len(sections[0])
    if n < 3:
        raise BadArgumentError("loft_sections() sections need >= 3 points")
    for i, s in enumerate(sections):
        if len(s) != n:
            raise BadArgumentError(
                f"loft_sections() section {i} has {len(s)} points but "
                f"section 0 has {n} — every station must have the SAME "
                f"point count",
                suggestion="generate all stations from one parametric "
                           "template so corresponding points line up")
    ax = {"x": 0, "y": 1, "z": 2}.get(axis)
    if ax is None:
        raise BadArgumentError(f'loft_sections() axis must be "x", "y" or '
                               f'"z", got {axis!r}')

    # signed area: enforce one consistent winding across stations
    def _area(pts):
        a = 0.0
        for (u0, v0), (u1, v1) in zip(pts, pts[1:] + pts[:1]):
            a += u0 * v1 - u1 * v0
        return a / 2.0

    for i, s in enumerate(sections):
        if abs(_area(s)) < 1e-9:
            raise BadArgumentError(
                f"loft_sections() section {i} has ~zero area")
        if _area(s) < 0:
            sections[i] = s[::-1]

    verts = []
    for st, sec in zip(stations, sections):
        for (u, v) in sec:
            p = [0.0, 0.0, 0.0]
            p[ax] = st
            p[(ax + 1) % 3] = float(u)
            p[(ax + 2) % 3] = float(v)
            verts.append(p)
    faces = []
    for i in range(len(sections) - 1):
        base, nxt = i * n, (i + 1) * n
        for k in range(n):
            k2 = (k + 1) % n
            faces.append([base + k, base + k2, nxt + k])
            faces.append([base + k2, nxt + k2, nxt + k])

    # exact non-convex end caps
    if _triangulate is not None:
        first = _triangulate([np.asarray(sections[0], dtype=np.float64)])
        last = _triangulate([np.asarray(sections[-1], dtype=np.float64)])
    else:                                   # fan fallback (convex-ish caps)
        first = [(0, k + 1, k) for k in range(1, n - 1)]
        last = [(0, k, k + 1) for k in range(1, n - 1)]
    off = (len(sections) - 1) * n
    for a, b, c in np.asarray(first, dtype=np.int64):
        faces.append([int(a), int(c), int(b)])
    for a, b, c in np.asarray(last, dtype=np.int64):
        faces.append([off + int(a), off + int(b), off + int(c)])

    mesh = Mesh(vert_properties=np.asarray(verts, dtype=np.float32),
                tri_verts=np.asarray(faces, dtype=np.uint32))
    m = Manifold(mesh)
    if m.is_empty():
        raise BadArgumentError(
            "loft_sections() produced no solid (status: "
            f"{m.status()})",
            suggestion="check that sections do not self-intersect and "
                       "that corresponding points do not cross between "
                       "stations (same start point, same direction)")
    out = Solid(m, f"loft_sections({len(sections)} stations, "
                   f"{axis} {fmt_num(stations[0])}..{fmt_num(stations[-1])})")
    if out.volume < 0:
        mesh = Mesh(vert_properties=np.asarray(verts, dtype=np.float32),
                    tri_verts=np.asarray(
                        [f[::-1] for f in faces], dtype=np.uint32))
        out = Solid(Manifold(mesh), out.desc)
    return out


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
                suggestion="loft only supports convex sections; for non-convex "
                           "cross-sections with the same point count (car bodies, "
                           "hulls) use parts.loft_sections()")
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
