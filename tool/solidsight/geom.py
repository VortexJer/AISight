"""The solidsight design language: parametric primitives, booleans, transforms.

Wraps the manifold3d geometry kernel. Everything is deterministic: the same
input code always produces the exact same geometry. All units are millimeters,
all angles are degrees.

Conventions (chosen for agents reasoning about parts on a build plate):
- box / cylinder / cone / prism are centered on the XY plane with their base
  resting on Z = 0.
- sphere / torus are centered at the origin.
- Sketches live on the XY plane; extrude() goes up in +Z; revolve() spins the
  sketch around what becomes the Z axis (sketch X = distance from axis,
  sketch Y = height).
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from manifold3d import CrossSection, FillRule, JoinType, Manifold, OpType

from .errors import (BadArgumentError, EmptyGeometryError, fmt_bbox, fmt_num)

# Default number of segments used to approximate circles. Fixed (never
# time- or platform-dependent) so geometry is bit-identical across runs.
DEFAULT_SEGMENTS = 64

_EPS = 1e-9


def _segments(segments: int | None) -> int:
    return DEFAULT_SEGMENTS if segments is None else max(3, int(segments))


def _radius(name: str, r: float | None, d: float | None,
            default: float | None = None) -> float:
    if r is not None and d is not None:
        raise BadArgumentError(
            f"{name}() got both r={fmt_num(r)} and d={fmt_num(d)}",
            suggestion="pass either r (radius) or d (diameter), not both")
    if r is None and d is None:
        if default is not None:
            return default
        raise BadArgumentError(
            f"{name}() needs a size",
            suggestion=f"pass r (radius) or d (diameter), e.g. {name}(d=8)")
    value = float(r) if r is not None else float(d) / 2.0
    if value <= 0:
        raise BadArgumentError(
            f"{name}() radius must be positive, got {fmt_num(value)}",
            suggestion="use a positive r or d")
    return value


def _positive(name: str, **dims: float) -> None:
    for k, v in dims.items():
        if v is None or float(v) <= 0:
            shown = "None" if v is None else fmt_num(v)
            raise BadArgumentError(
                f"{name}() dimension '{k}' must be a positive number, got {shown}",
                suggestion=f"call {name}() with {k} > 0 (units are mm)")


def _short(desc: str, n: int = 70) -> str:
    """Cap composed descriptions so error/warning texts stay readable."""
    return desc if len(desc) <= n else desc[:n - 3] + "..."


def _warn(code: str, message: str, where: str | None = None,
          suggestion: str | None = None) -> None:
    """Record a build warning on the active scene, if any."""
    from . import scene  # lazy: avoid circular import
    ctx = scene.current()
    if ctx is not None:
        ctx.warn(code, message, where=where, suggestion=suggestion)


# --------------------------------------------------------------------------
# Solid
# --------------------------------------------------------------------------

class Solid:
    """An immutable 3D solid. All operations return a new Solid.

    Booleans:   a + b (union)   a - b (difference)   a & b (intersection)
    Transforms: .translate(x,y,z) .rotate(x=,y=,z=) .scale() .mirror("x")
    """

    def __init__(self, manifold: Manifold, desc: str = "solid"):
        self._m = manifold
        self.desc = desc

    # -- inspection --------------------------------------------------------

    @property
    def manifold(self) -> Manifold:
        return self._m

    @property
    def volume(self) -> float:
        return float(self._m.volume())

    @property
    def area(self) -> float:
        return float(self._m.surface_area())

    @property
    def is_empty(self) -> bool:
        return bool(self._m.is_empty())

    @property
    def bbox(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        b = self._m.bounding_box()
        return ((b[0], b[1], b[2]), (b[3], b[4], b[5]))

    @property
    def size(self) -> tuple[float, float, float]:
        lo, hi = self.bbox
        return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])

    @property
    def bbox_center(self) -> tuple[float, float, float]:
        lo, hi = self.bbox
        return ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)

    def __repr__(self) -> str:
        if self.is_empty:
            return f"<Solid {self.desc} EMPTY>"
        return (f"<Solid {self.desc} size={tuple(round(s, 3) for s in self.size)} "
                f"volume={round(self.volume, 3)}mm3>")

    def describe(self, desc: str) -> "Solid":
        """Give this solid a short name for warnings and error messages —
        composed descriptions get long; parts name their results."""
        return Solid(self._m, desc)

    # -- transforms ---------------------------------------------------------

    def translate(self, x: float = 0, y: float = 0, z: float = 0) -> "Solid":
        return Solid(self._m.translate([float(x), float(y), float(z)]), self.desc)

    move = translate  # alias

    def rotate(self, x: float = 0, y: float = 0, z: float = 0) -> "Solid":
        """Euler rotation in degrees, applied in X, then Y, then Z order."""
        return Solid(self._m.rotate([float(x), float(y), float(z)]), self.desc)

    def scale(self, x: float = 1, y: float | None = None,
              z: float | None = None) -> "Solid":
        """scale(2) scales uniformly; scale(1, 2, 1) per axis."""
        if y is None and z is None:
            y = z = x
        y = x if y is None else y
        z = x if z is None else z
        if x == 0 or y == 0 or z == 0:
            raise BadArgumentError(
                f"scale by zero flattens '{self.desc}' into nothing "
                f"(got x={fmt_num(x)}, y={fmt_num(y)}, z={fmt_num(z)})",
                suggestion="use a small positive factor instead of 0")
        return Solid(self._m.scale([float(x), float(y), float(z)]), self.desc)

    def mirror(self, axis: str = "x") -> "Solid":
        """Mirror across the plane perpendicular to the given axis, through
        the origin. axis is one of "x", "y", "z"."""
        normals = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}
        if axis not in normals:
            raise BadArgumentError(
                f"mirror() axis must be 'x', 'y' or 'z', got {axis!r}",
                suggestion='e.g. part.mirror("x") reflects left<->right')
        return Solid(self._m.mirror(normals[axis]), self.desc)

    def aim(self, direction: str) -> "Solid":
        """Re-orient a DOWNWARD-built tool so it works along an axis.
        Cutters from the catalog (parts.hole, ...) are built drilling -Z
        with their entry point at the origin; aim() maps that -Z onto the
        given axis direction, then you translate the entry point onto the
        face:

            block -= parts.hole(d=6, depth=10).aim("-y").translate(0, 20, 8)
            # drills INTO the wall whose outside faces +Y, at (0, 20, 8)

        direction: "+x" "-x" "+y" "-y" "+z" "-z" (the way the tool travels).

        Extrusions grow UP (+Z) — make one a downward tool first:
            pocket = outline.extrude(depth).translate(0, 0, -depth).aim("+x")
        """
        rots = {"-z": (0, 0, 0), "+z": (180, 0, 0),
                "+y": (90, 0, 0), "-y": (-90, 0, 0),
                "+x": (0, -90, 0), "-x": (0, 90, 0)}
        if direction not in rots:
            raise BadArgumentError(
                f"aim() direction must be one of {sorted(rots)}, "
                f"got {direction!r}",
                suggestion='e.g. .aim("-y") to drill into a +Y-facing wall')
        rx, ry, rz = rots[direction]
        return self.rotate(rx, ry, rz)

    def centered(self) -> "Solid":
        """Move so the bounding-box center sits at the origin."""
        c = self.bbox_center
        return self.translate(-c[0], -c[1], -c[2])

    def on_ground(self) -> "Solid":
        """Move straight down/up so the lowest point rests on Z = 0."""
        lo, _ = self.bbox
        return self.translate(0, 0, -lo[2])

    # -- booleans ------------------------------------------------------------

    def __add__(self, other: "Solid") -> "Solid":
        _check_solid("union", other)
        result = Solid(self._m + other._m,
                       f"union({_short(self.desc)}, {_short(other.desc)})")
        # Coplanar-touch unions are degenerate: the pieces stay separated by
        # a zero-thickness seam (they look fused but are not). Volume being
        # exactly additive while the bboxes touch is the fingerprint.
        va, vb, vr = self.volume, other.volume, result.volume
        if (va > _EPS and vb > _EPS
                and abs(vr - (va + vb)) < 1e-9 * max(vr, 1.0)
                and not _bbox_disjoint(self.bbox, other.bbox)
                # additive volume + overlapping bboxes is not enough: the
                # pieces must actually TOUCH (interleaved cutter patterns
                # overlap in bbox while staying apart — no warning for those)
                and float(self._m.min_gap(other._m, 1e-3)) < 1e-6):
            _warn("union-touching",
                  f"union of '{self.desc}' and '{other.desc}' only TOUCHES — "
                  f"no shared volume, so the pieces will not truly fuse "
                  f"(zero-thickness seam)",
                  where=f"bboxes {fmt_bbox(self.bbox)} and {fmt_bbox(other.bbox)}",
                  suggestion="overlap the pieces by at least 0.1 mm (extend "
                             "one into the other) so the union merges them")
        return result

    __or__ = __add__

    def __sub__(self, other: "Solid") -> "Solid":
        _check_solid("difference", other)
        before = self.volume
        result = Solid(self._m - other._m,
                       f"difference({_short(self.desc)} minus {_short(other.desc)})")
        if result.is_empty:
            raise EmptyGeometryError(
                f"difference removed the entire solid: '{other.desc}' "
                f"completely contains '{self.desc}'",
                where=f"target bbox {fmt_bbox(self.bbox)}; "
                      f"cutter bbox {fmt_bbox(other.bbox)}",
                suggestion="shrink the cutter, or check the translate() offsets "
                           "— you may have the operands reversed")
        if before > _EPS and abs(result.volume - before) < 1e-6 * max(before, 1.0):
            if _bbox_disjoint(self.bbox, other.bbox):
                _warn("noop-difference",
                      f"difference had no effect: '{other.desc}' does not touch "
                      f"'{self.desc}' (their bounding boxes do not overlap)",
                      where=f"target bbox {fmt_bbox(self.bbox)}; "
                            f"cutter bbox {fmt_bbox(other.bbox)}",
                      suggestion="move the cutter so it intersects the target, "
                                 "or delete the subtraction if unneeded")
            else:
                _warn("noop-difference",
                      f"difference had no effect: '{other.desc}' overlaps the "
                      f"bounding box of '{self.desc}' but removed no material "
                      f"(it may sit entirely inside a cavity or outside the walls)",
                      where=f"cutter bbox {fmt_bbox(other.bbox)}",
                      suggestion="render a --slice through the cutter position "
                                 "to see where it actually is")
        return result

    def __and__(self, other: "Solid") -> "Solid":
        _check_solid("intersection", other)
        result = Solid(self._m ^ other._m,
                       f"intersection({_short(self.desc)}, {_short(other.desc)})")
        if result.is_empty:
            if _bbox_disjoint(self.bbox, other.bbox):
                where = (f"'{self.desc}' bbox {fmt_bbox(self.bbox)} vs "
                         f"'{other.desc}' bbox {fmt_bbox(other.bbox)} — "
                         "the bounding boxes do not even overlap")
            else:
                where = (f"bounding boxes overlap but the solids do not: "
                         f"{fmt_bbox(self.bbox)} vs {fmt_bbox(other.bbox)}")
            raise EmptyGeometryError(
                "intersection produced empty geometry — the two solids do not "
                "share any volume", where=where,
                suggestion="check translate() offsets; print each operand's "
                           ".bbox to see where they actually sit")
        return result

    def hull_with(self, *others: "Solid") -> "Solid":
        return hull(self, *others)

    # -- rounding (Minkowski-based, all edges at once) ------------------------

    def grow(self, r: float, segments: int | None = 16) -> "Solid":
        """Minkowski-dilate by a sphere of radius r: offsets every face
        outward by r and rounds every convex edge. The part gets bigger.
        The input is simplified to r/20 tolerance first — invisible at the
        rounding scale, but it keeps Minkowski cost sane on dense meshes."""
        _positive("grow", r=r)
        ball = Manifold.sphere(float(r), _segments(segments))
        src = self._m.simplify(float(r) / 20)
        return Solid(src.minkowski_sum(ball), f"grow({self.desc}, r={fmt_num(r)})")

    def shrink(self, r: float, segments: int | None = 16) -> "Solid":
        """Minkowski-erode by a sphere of radius r. The part gets smaller;
        walls thinner than 2*r vanish (raises if everything vanishes).
        Input simplified to r/20 tolerance first, like grow()."""
        _positive("shrink", r=r)
        ball = Manifold.sphere(float(r), _segments(segments))
        src = self._m.simplify(float(r) / 20)
        out = Solid(src.minkowski_difference(ball),
                    f"shrink({self.desc}, r={fmt_num(r)})")
        if out.is_empty:
            raise EmptyGeometryError(
                f"shrink(r={fmt_num(r)}) erased '{self.desc}' entirely — "
                f"no region of it is thicker than {fmt_num(2 * float(r))}",
                where=f"original bbox {fmt_bbox(self.bbox)}",
                suggestion="use a smaller r, or thicken the part first")
        return out

    def fillet(self, r: float, segments: int | None = 16) -> "Solid":
        """Round ALL edges (convex and concave) with radius ~r, preserving
        overall dimensions. Implemented as morphological closing then opening
        (4 Minkowski ops) — accurate but slow on high-poly parts, so apply it
        once, at the end, on the finished shape."""
        _positive("fillet", r=r)
        closed = self.grow(r, segments).shrink(r, segments)   # round concave
        opened = closed.shrink(r, segments).grow(r, segments)  # round convex
        opened.desc = f"fillet({self.desc}, r={fmt_num(r)})"
        return opened

    # -- directional edge breaks (rims) -----------------------------------------

    def chamfer_rim(self, c: float, z: float | None = None,
                    bottom: bool = False, segments: int | None = 24) -> "Solid":
        """Break ALL edges lying on the top (or bottom) rim with a 45-degree
        chamfer of size c — box tops, cylinder mouths, container lips (both
        sides of the wall at once). Works on any outline, holes included.
        Requires roughly vertical walls near the rim (true for boxes,
        cylinders, extrusions, containers). z overrides which plane is
        treated as the rim (default: the solid's top/bottom)."""
        return self._break_rim(c, z, bottom, "chamfer", segments)

    def round_rim(self, r: float, z: float | None = None,
                  bottom: bool = False, segments: int | None = 24) -> "Solid":
        """Like chamfer_rim() but with a quarter-round of radius r —
        the finger-friendly rim for cups, vases and handles."""
        return self._break_rim(r, z, bottom, "round", segments)

    def _break_rim(self, c: float, z: float | None, bottom: bool,
                   style: str, segments: int | None) -> "Solid":
        _positive("chamfer_rim" if style == "chamfer" else "round_rim", c=c)
        work = self.mirror("z") if bottom else self
        lo, hi = work.bbox
        z_top = float(z) if z is not None and not bottom else \
            (-float(z) if z is not None else hi[2])
        c = float(c)
        contour = work._m.slice(z_top - c)
        if contour.is_empty():
            raise EmptyGeometryError(
                f"no material at z={fmt_num(z_top - c)} to build the rim from",
                suggestion="the rim size is bigger than the part, or z is "
                           "outside the part")
        inner = contour.offset(-c, JoinType.Round, 2.0, _segments(segments))
        if inner.is_empty():
            raise EmptyGeometryError(
                f"rim break of {fmt_num(c)} consumed the whole outline — "
                "the top is thinner than 2x the break size",
                suggestion="use a smaller c/r")
        slab = Manifold.extrude(inner, 0.01).translate([0, 0, z_top - 0.01])
        seg = _segments(segments)
        if style == "chamfer":
            # cone: apex at origin, widening downward, 45 degrees
            tool = Manifold.cylinder(c, c, 0.001, seg, False).translate(
                [0, 0, -c])
        else:
            # quarter-round: sphere tangent at the origin from below
            tool = Manifold.sphere(c, seg).translate([0, 0, -c])
        roof = slab.minkowski_sum(tool)
        below = work._m.trim_by_plane([0, 0, -1], -(z_top - c))
        crown = work._m ^ roof
        out = Solid(below + crown,
                    f"{style}_rim({_short(self.desc)}, {fmt_num(c)})")
        if bottom:
            out = out.mirror("z")
        out.desc = f"{style}_rim({_short(self.desc)}, {fmt_num(c)})"
        return out

    # -- freeform ---------------------------------------------------------------

    def refine(self, edge_mm: float) -> "Solid":
        """Subdivide the mesh until no edge is longer than edge_mm. Do this
        BEFORE warp() so large flat faces actually bend instead of staying
        planar between far-apart vertices."""
        _positive("refine", edge_mm=edge_mm)
        return Solid(self._m.refine_to_length(float(edge_mm)), self.desc)

    def warp(self, fn) -> "Solid":
        """Freeform deformation: fn(x, y, z) -> (x, y, z) is applied to every
        vertex. MUST be a pure deterministic function (no randomness). Combine
        with refine() for smooth results:

            def bulge(x, y, z):
                s = 1 + 0.25 * math.sin(math.pi * z / H)
                return x * s, y * s, z
            vase = vase.refine(3).warp(bulge)

        Keep deformations gentle — extreme warps can self-intersect, which
        the report will surface as broken geometry."""
        if not callable(fn):
            raise BadArgumentError("warp() needs a function (x, y, z) -> "
                                   "(x, y, z)")

        def _wrapped(v):
            out = fn(float(v[0]), float(v[1]), float(v[2]))
            return (float(out[0]), float(out[1]), float(out[2]))

        try:
            m = self._m.warp(_wrapped)
        except Exception as e:
            raise BadArgumentError(
                f"warp() function failed while deforming '{self.desc}': {e}",
                suggestion="fn must accept three floats and return three "
                           "floats, with no randomness") from e
        out = Solid(m, f"warp({_short(self.desc)})")
        if out.is_empty:
            raise EmptyGeometryError(
                f"warp() collapsed '{self.desc}' into nothing",
                suggestion="the deformation inverted or flattened the solid; "
                           "reduce its strength")
        return out

    # -- export ----------------------------------------------------------------

    def to_trimesh(self):
        import trimesh
        mesh = self._m.to_mesh()
        verts = np.asarray(mesh.vert_properties, dtype=np.float64)[:, :3]
        faces = np.asarray(mesh.tri_verts, dtype=np.int64)
        return trimesh.Trimesh(vertices=verts, faces=faces, process=False)


def _check_solid(op: str, other) -> None:
    if not isinstance(other, Solid):
        got = type(other).__name__
        raise BadArgumentError(
            f"{op} needs two Solids, but the right-hand side is a {got}",
            suggestion="if it is a Sketch, call .extrude(height) on it first; "
                       "if it is a dict from the parts catalog, pick one entry "
                       'like parts["lid"]')


def _bbox_disjoint(a, b) -> bool:
    (alo, ahi), (blo, bhi) = a, b
    return any(ahi[i] < blo[i] or bhi[i] < alo[i] for i in range(3))


# --------------------------------------------------------------------------
# 3D primitives
# --------------------------------------------------------------------------

def box(x: float, y: float, z: float, center: bool = False) -> Solid:
    """Rectangular box, centered on XY, base on Z=0.
    center=True centers it on the origin in all three axes."""
    _positive("box", x=x, y=y, z=z)
    m = Manifold.cube([float(x), float(y), float(z)], True)
    if not center:
        m = m.translate([0, 0, float(z) / 2])
    return Solid(m, f"box({fmt_num(x)}x{fmt_num(y)}x{fmt_num(z)})")


def cylinder(h: float, r: float | None = None, d: float | None = None,
             segments: int | None = None) -> Solid:
    """Cylinder, centered on XY, base on Z=0."""
    _positive("cylinder", h=h)
    rr = _radius("cylinder", r, d)
    m = Manifold.cylinder(float(h), rr, rr, _segments(segments), False)
    return Solid(m, f"cylinder(d={fmt_num(2 * rr)}, h={fmt_num(h)})")


def cone(h: float, d1: float | None = None, d2: float | None = None,
         r1: float | None = None, r2: float | None = None,
         segments: int | None = None) -> Solid:
    """Truncated cone: d1/r1 at the base (Z=0), d2/r2 at the top.
    Either end may be 0 for a sharp point."""
    _positive("cone", h=h)
    rb = float(r1) if r1 is not None else (float(d1) / 2 if d1 is not None else None)
    rt = float(r2) if r2 is not None else (float(d2) / 2 if d2 is not None else None)
    if rb is None or rt is None:
        raise BadArgumentError(
            "cone() needs both end sizes",
            suggestion="e.g. cone(h=10, d1=8, d2=0) for a spike, "
                       "cone(h=5, d1=10, d2=6) for a truncated cone")
    if rb < 0 or rt < 0 or (rb == 0 and rt == 0):
        raise BadArgumentError(
            f"cone() radii must be >= 0 and not both 0 "
            f"(got r1={fmt_num(rb)}, r2={fmt_num(rt)})")
    m = Manifold.cylinder(float(h), rb, rt, _segments(segments), False)
    return Solid(m, f"cone(d1={fmt_num(2*rb)}, d2={fmt_num(2*rt)}, h={fmt_num(h)})")


def sphere(r: float | None = None, d: float | None = None,
           segments: int | None = None) -> Solid:
    """Sphere centered at the origin."""
    rr = _radius("sphere", r, d)
    return Solid(Manifold.sphere(rr, _segments(segments)),
                 f"sphere(d={fmt_num(2 * rr)})")


def prism(n: int, h: float, r: float | None = None, d: float | None = None,
          across_flats: float | None = None) -> Solid:
    """Regular n-sided prism, centered on XY, base on Z=0. Size by
    circumscribed r/d (corner to corner) or across_flats (face to face —
    what a wrench measures; use this for hex nuts)."""
    if n < 3:
        raise BadArgumentError(f"prism() needs n >= 3 sides, got {n}")
    _positive("prism", h=h)
    if across_flats is not None:
        rr = float(across_flats) / (2 * math.cos(math.pi / n))
    else:
        rr = _radius("prism", r, d)
    sk = ngon(n, r=rr)
    out = sk.extrude(h)
    out.desc = f"prism(n={n}, d={fmt_num(2 * rr)}, h={fmt_num(h)})"
    return out


def wedge(x: float, y: float, z: float) -> Solid:
    """Right-triangle prism: full box footprint at Z=0, sloping to a knife
    edge at the +Y side, height z. Centered on XY like box()."""
    _positive("wedge", x=x, y=y, z=z)
    profile = polygon([(-y / 2, 0), (y / 2, 0), (-y / 2, z)])
    out = profile.extrude(x)
    # extruded along Z of sketch; re-orient: sketch X was Y, sketch Y was Z
    s = Solid(out.manifold.rotate([90, 0, 0]).rotate([0, 0, 90]),
              f"wedge({fmt_num(x)}x{fmt_num(y)}x{fmt_num(z)})")
    return s.translate(-x / 2, 0, 0).on_ground()


def torus(r_ring: float, r_tube: float,
          segments: int | None = None) -> Solid:
    """Torus around the Z axis, centered at the origin. r_ring is the
    distance from the axis to the tube center; r_tube is the tube radius."""
    _positive("torus", r_ring=r_ring, r_tube=r_tube)
    if r_tube >= r_ring:
        raise BadArgumentError(
            f"torus() tube radius {fmt_num(r_tube)} must be smaller than ring "
            f"radius {fmt_num(r_ring)} (it would self-intersect at the axis)",
            suggestion="reduce r_tube or increase r_ring")
    profile = circle(r=r_tube).translate(r_ring, 0)
    out = profile.revolve(segments=segments)
    out.desc = f"torus(r_ring={fmt_num(r_ring)}, r_tube={fmt_num(r_tube)})"
    return out.translate(0, 0, 0)


def rounded_box(x: float, y: float, z: float, r: float,
                vertical_only: bool = False,
                segments: int | None = None) -> Solid:
    """Box with rounded edges (radius r), centered on XY, base on Z=0.
    vertical_only=True rounds just the 4 vertical edges (flat top/bottom,
    ideal for printed enclosures). Cheap and exact — prefer this over
    box().fillet() when a box is what you want."""
    _positive("rounded_box", x=x, y=y, z=z, r=r)
    if 2 * r >= min(x, y) or (not vertical_only and 2 * r >= z):
        raise BadArgumentError(
            f"rounded_box() radius {fmt_num(r)} is too big for a "
            f"{fmt_num(x)}x{fmt_num(y)}x{fmt_num(z)} box",
            suggestion=f"keep r below half the smallest dimension "
                       f"(max here: {fmt_num(min(x, y, z if not vertical_only else max(x, y)) / 2 - 0.001)})")
    seg = _segments(segments)
    if vertical_only:
        sk = rect(x, y).round_corners(r, segments=seg)
        out = sk.extrude(z)
    else:
        ball = sphere(r=r, segments=seg)
        dx, dy, dz = x / 2 - r, y / 2 - r, z / 2 - r
        corners = [ball.translate(sx * dx, sy * dy, sz * dz)
                   for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        out = hull(*corners).translate(0, 0, z / 2)
    out.desc = f"rounded_box({fmt_num(x)}x{fmt_num(y)}x{fmt_num(z)}, r={fmt_num(r)})"
    return out


# --------------------------------------------------------------------------
# combinators
# --------------------------------------------------------------------------

def union(*solids: Solid) -> Solid:
    items = _flatten(solids)
    if not items:
        raise BadArgumentError("union() got no solids")
    ms = [s._m for s in items]
    out = Solid(Manifold.batch_boolean(ms, OpType.Add),
                f"union of {len(items)} solids")
    return out


def difference(base: Solid, *cutters: Solid) -> Solid:
    for c in _flatten(cutters):
        base = base - c
    return base


def intersection(*solids: Solid) -> Solid:
    items = _flatten(solids)
    if len(items) < 2:
        raise BadArgumentError("intersection() needs at least two solids")
    out = items[0]
    for s in items[1:]:
        out = out & s
    return out


def hull(*solids: Solid) -> Solid:
    items = _flatten(solids)
    if not items:
        raise BadArgumentError("hull() got no solids")
    out = Solid(Manifold.batch_hull([s._m for s in items]),
                f"hull of {len(items)} solids")
    if out.is_empty:
        raise EmptyGeometryError("hull() produced empty geometry",
                                 suggestion="check that the inputs are non-empty")
    return out


def _flatten(items) -> list[Solid]:
    out: list[Solid] = []
    for it in items:
        if isinstance(it, Solid):
            out.append(it)
        elif isinstance(it, (list, tuple)):
            out.extend(_flatten(it))
        else:
            raise BadArgumentError(
                f"expected a Solid, got {type(it).__name__}",
                suggestion="Sketches must be extruded/revolved before 3D booleans")
    return out


# --------------------------------------------------------------------------
# Sketch (2D) — build profiles, then extrude() or revolve()
# --------------------------------------------------------------------------

class Sketch:
    """An immutable 2D region on the XY plane. Booleans use + - & like Solid.
    Turn into 3D with .extrude(height) or .revolve()."""

    def __init__(self, cs: CrossSection, desc: str = "sketch"):
        self._cs = cs
        self.desc = desc

    @property
    def cross_section(self) -> CrossSection:
        return self._cs

    @property
    def area(self) -> float:
        return float(self._cs.area())

    @property
    def is_empty(self) -> bool:
        return bool(self._cs.is_empty())

    def __repr__(self) -> str:
        b = self._cs.bounds()
        return (f"<Sketch {self.desc} bounds=({fmt_num(b[0])},{fmt_num(b[1])})..."
                f"({fmt_num(b[2])},{fmt_num(b[3])}) area={round(self.area, 3)}mm2>")

    # transforms
    def translate(self, x: float = 0, y: float = 0) -> "Sketch":
        return Sketch(self._cs.translate([float(x), float(y)]), self.desc)

    move = translate

    def rotate(self, degrees: float) -> "Sketch":
        return Sketch(self._cs.rotate(float(degrees)), self.desc)

    def scale(self, x: float = 1, y: float | None = None) -> "Sketch":
        y = x if y is None else y
        return Sketch(self._cs.scale([float(x), float(y)]), self.desc)

    def mirror(self, axis: str = "x") -> "Sketch":
        normals = {"x": [1, 0], "y": [0, 1]}
        if axis not in normals:
            raise BadArgumentError(f"Sketch.mirror() axis must be 'x' or 'y', got {axis!r}")
        return Sketch(self._cs.mirror(normals[axis]), self.desc)

    # booleans
    def __add__(self, other: "Sketch") -> "Sketch":
        _check_sketch("union", other)
        return Sketch(self._cs + other._cs,
                      f"union({_short(self.desc)}, {_short(other.desc)})")

    __or__ = __add__

    def __sub__(self, other: "Sketch") -> "Sketch":
        _check_sketch("difference", other)
        out = Sketch(self._cs - other._cs,
                     f"difference({_short(self.desc)} minus {_short(other.desc)})")
        if out.is_empty:
            raise EmptyGeometryError(
                f"2D difference removed the entire sketch '{self.desc}'",
                suggestion="the cutter covers the whole profile — shrink it")
        return out

    def __and__(self, other: "Sketch") -> "Sketch":
        _check_sketch("intersection", other)
        out = Sketch(self._cs ^ other._cs,
                     f"intersection({self.desc}, {other.desc})")
        if out.is_empty:
            raise EmptyGeometryError(
                "2D intersection is empty — the profiles do not overlap",
                suggestion="print each sketch to see its bounds")
        return out

    # offsets / corner rounding
    def offset(self, delta: float, join: str = "round",
               segments: int | None = None) -> "Sketch":
        """Grow (delta > 0) or shrink (delta < 0) the region by a distance.
        join: "round", "miter" or "square" (for outward corners)."""
        joins = {"round": JoinType.Round, "miter": JoinType.Miter,
                 "square": JoinType.Square}
        if join not in joins:
            raise BadArgumentError(f'offset() join must be "round", "miter" or '
                                   f'"square", got {join!r}')
        out = Sketch(self._cs.offset(float(delta), joins[join], 2.0,
                                     _segments(segments)),
                     f"offset({self.desc}, {fmt_num(delta)})")
        if out.is_empty and delta < 0:
            raise EmptyGeometryError(
                f"offset({fmt_num(delta)}) erased the sketch '{self.desc}' — "
                f"no region of it is wider than {fmt_num(-2 * float(delta))}",
                suggestion="use a smaller negative offset")
        return out

    def round_corners(self, r: float, segments: int | None = None) -> "Sketch":
        """Round every corner (convex and concave) with radius r while keeping
        the outer dimensions. Do this on the 2D profile BEFORE extruding —
        it is far cheaper than 3D fillets."""
        _positive("round_corners", r=r)
        seg = _segments(segments)
        out = (self.offset(r, "round", seg).offset(-2 * r, "round", seg)
                   .offset(r, "round", seg))
        out.desc = f"round_corners({self.desc}, r={fmt_num(r)})"
        return out

    # to 3D
    def extrude(self, height: float, twist: float = 0.0,
                scale_top: float | tuple[float, float] = 1.0,
                divisions: int | None = None) -> Solid:
        """Linear extrude in +Z from Z=0. twist (degrees, total) and scale_top
        turn it into a helical / tapered extrusion; divisions controls how
        many slices approximate the twist."""
        _positive("extrude", height=height)
        st = ((float(scale_top), float(scale_top))
              if isinstance(scale_top, (int, float)) else
              (float(scale_top[0]), float(scale_top[1])))
        ndiv = divisions if divisions is not None else (
            max(2, int(abs(twist) / 4)) if twist else 0)
        m = self._cs.extrude(float(height), ndiv, float(twist), st)
        out = Solid(m, f"extrude({self.desc}, h={fmt_num(height)})")
        if out.is_empty:
            raise EmptyGeometryError(
                f"extrude() of empty sketch '{self.desc}'",
                suggestion="the 2D profile has no area — check earlier 2D booleans")
        return out

    def revolve(self, angle: float = 360.0,
                segments: int | None = None) -> Solid:
        """Revolve around the Z axis. The sketch must lie at X >= 0:
        sketch X = distance from the axis, sketch Y = height (becomes Z)."""
        b = self._cs.bounds()
        if b[0] < -1e-6:
            raise BadArgumentError(
                f"revolve() needs the profile at X >= 0, but '{self.desc}' "
                f"starts at x={fmt_num(b[0])}",
                suggestion=f"translate the sketch right by at least "
                           f"{fmt_num(-b[0])} before revolving")
        m = self._cs.revolve(_segments(segments), float(angle))
        out = Solid(m, f"revolve({self.desc}, {fmt_num(angle)}deg)")
        if out.is_empty:
            raise EmptyGeometryError(f"revolve() of empty sketch '{self.desc}'")
        return out


def _check_sketch(op: str, other) -> None:
    if not isinstance(other, Sketch):
        got = type(other).__name__
        hint = ("Solids cannot be combined with Sketches — extrude the sketch "
                "first" if isinstance(other, Solid) else
                "wrap raw points with polygon([...])")
        raise BadArgumentError(f"2D {op} needs two Sketches, got a {got}",
                               suggestion=hint)


# 2D primitives ------------------------------------------------------------

def rect(x: float, y: float, center: bool = True) -> Sketch:
    """Rectangle. Centered on the origin by default; center=False puts the
    lower-left corner at the origin."""
    _positive("rect", x=x, y=y)
    return Sketch(CrossSection.square([float(x), float(y)], bool(center)),
                  f"rect({fmt_num(x)}x{fmt_num(y)})")


def circle(r: float | None = None, d: float | None = None,
           segments: int | None = None) -> Sketch:
    rr = _radius("circle", r, d)
    return Sketch(CrossSection.circle(rr, _segments(segments)),
                  f"circle(d={fmt_num(2 * rr)})")


def ngon(n: int, r: float | None = None, d: float | None = None) -> Sketch:
    """Regular polygon with a flat side facing -Y, circumscribed radius r."""
    if n < 3:
        raise BadArgumentError(f"ngon() needs n >= 3, got {n}")
    rr = _radius("ngon", r, d)
    start = -math.pi / 2 + math.pi / n  # flat side down
    pts = [(rr * math.cos(start + 2 * math.pi * i / n),
            rr * math.sin(start + 2 * math.pi * i / n)) for i in range(n)]
    return Sketch(CrossSection([pts], FillRule.Positive),
                  f"ngon(n={n}, d={fmt_num(2 * rr)})")


def polygon(points: Sequence[tuple[float, float]] | Sequence[Sequence[tuple[float, float]]]) -> Sketch:
    """Polygon from a list of (x, y) points, or a list of rings where the
    first is the outline and the rest are holes."""
    pts = list(points)
    if not pts:
        raise BadArgumentError("polygon() got an empty point list")
    rings = pts if isinstance(pts[0][0], (list, tuple)) else [pts]
    for ring in rings:
        if len(ring) < 3:
            raise BadArgumentError(
                f"polygon() ring has only {len(ring)} points, need >= 3")
    cs = CrossSection([[(float(x), float(y)) for x, y in ring] for ring in rings],
                      FillRule.EvenOdd)
    out = Sketch(cs, f"polygon({len(rings[0])} pts)")
    if out.is_empty:
        raise EmptyGeometryError(
            "polygon() produced an empty region",
            where=f"first points: {rings[0][:3]}...",
            suggestion="points may be collinear or the ring self-intersects; "
                       "list the outline counter-clockwise without repeating "
                       "the first point at the end")
    if len(rings) == 1 and out._cs.num_contour() > 1:
        _warn("self-intersecting-polygon",
              f"polygon() outline self-intersects and split into "
              f"{out._cs.num_contour()} separate regions — extrusions of it "
              f"will be disconnected pieces",
              where=f"outline of {len(rings[0])} points, "
                    f"bounds {tuple(round(v, 2) for v in out._cs.bounds())}",
              suggestion="re-order the points so the outline never crosses "
                         "itself, or build the shape from simpler sketches "
                         "with 2D booleans / stroke()")
    return out


def stroke(points: Sequence[tuple[float, float]], width: float,
           segments: int | None = None) -> Sketch:
    """A 2D ribbon of constant width along a polyline — round joints, round
    caps. The natural way to draw smooth curved profiles (hooks, handles,
    brackets): generate the centerline points with a bit of math, stroke it,
    then extrude. Sample curves every few degrees for smooth results."""
    pts = [(float(x), float(y)) for x, y in points]
    if len(pts) < 2:
        raise BadArgumentError(
            f"stroke() needs at least 2 centerline points, got {len(pts)}")
    _positive("stroke", width=width)
    r = width / 2.0
    seg = _segments(segments if segments is not None else 24)
    pieces = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 1e-9:
            continue
        nx, ny = -dy / length * r, dx / length * r
        # counter-clockwise winding (Positive fill drops clockwise rings)
        quad = CrossSection([[(x0 - nx, y0 - ny), (x1 - nx, y1 - ny),
                              (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)]],
                            FillRule.Positive)
        pieces.append(quad)
    if not pieces:
        raise BadArgumentError("stroke() centerline has zero length",
                               suggestion="points are all identical")
    caps = [CrossSection.circle(r, seg).translate([x, y]) for x, y in pts]
    cs = CrossSection.batch_boolean(pieces + caps, OpType.Add)
    return Sketch(cs, f"stroke({len(pts)} pts, w={fmt_num(width)})")


def text(string: str, size: float = 10.0, font: str | None = None,
         halign: str = "left", valign: str = "baseline") -> Sketch:
    """Text as a 2D sketch (then .extrude(depth) and union for embossing, or
    subtract for engraving). size is the font size in mm (capital letters come
    out roughly 0.7 * size tall). Uses the bundled DejaVu Sans font by default
    so results are identical on every machine; font may name any installed
    family or a .ttf path."""
    if not string:
        raise BadArgumentError("text() got an empty string")
    _positive("text", size=size)
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath
    prop = FontProperties(family=font) if font else FontProperties(family="DejaVu Sans")
    path = TextPath((0, 0), string, size=float(size), prop=prop)
    contours = [[(float(x), float(y)) for x, y in poly]
                for poly in path.to_polygons() if len(poly) >= 3]
    if not contours:
        raise BadArgumentError(
            f"text() produced no outlines for {string!r}",
            suggestion="the string may be all whitespace, or the font is "
                       "missing these glyphs — try the default font")
    cs = CrossSection(contours, FillRule.EvenOdd)
    sk = Sketch(cs, f"text({string!r})")
    b = cs.bounds()
    dx = {"left": 0.0, "center": -(b[0] + b[2]) / 2, "right": -b[2]}
    dy = {"baseline": 0.0, "bottom": -b[1], "center": -(b[1] + b[3]) / 2,
          "top": -b[3]}
    if halign not in dx or valign not in dy:
        raise BadArgumentError(
            f"text() halign must be left/center/right and valign "
            f"baseline/bottom/center/top (got {halign!r}, {valign!r})")
    return sk.translate(dx[halign], dy[valign])
