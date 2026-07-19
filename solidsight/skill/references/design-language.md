# solidsight design language — complete reference

A model file is plain Python that starts with `from solidsight import *`.
Units are millimeters, angles are degrees. Everything is deterministic: the
same file always produces byte-identical geometry, renders and reports.

## Coordinate conventions

- Z is up; Z=0 is the build plate. The renderer's ground grid is 10 mm.
- `box`, `cylinder`, `cone`, `prism`, `wedge` and extrusions are centered on
  the XY plane with their BASE resting on Z=0.
- `sphere` and `torus` are centered at the origin.
- Sketches (2D) live on the XY plane; `.extrude(h)` goes up in +Z.

## 3D primitives

```python
box(x, y, z)                     # center=True to center on origin in Z too
cylinder(h, d=None, r=None, segments=None)
cone(h, d1=, d2=)                # base d1 at Z=0, top d2 (0 = sharp)
sphere(d=None, r=None)
prism(n, h, d=| r=| across_flats=)   # across_flats for hex nut pockets
wedge(x, y, z)                   # right-triangle prism, slope facing +Y
torus(r_ring, r_tube)
rounded_box(x, y, z, r, vertical_only=False)   # cheap exact rounded box
```

Circle smoothness: `segments` (default 64) — fixed, never random.

## 2D sketches -> 3D

```python
rect(x, y)                       # center=False -> corner at origin
circle(d=| r=)
ngon(n, d=| r=)                  # regular polygon, flat side down
polygon([(x, y), ...])           # or [outline, hole1, hole2] rings
text("LABEL", size=10, halign="left|center|right",
     valign="baseline|bottom|center|top")     # returns a Sketch

sk.offset(+2)                    # grow/shrink; join="round|miter|square"
sk.round_corners(r)              # round ALL 2D corners — do this BEFORE extrude
sk + sk2, sk - sk2, sk & sk2     # 2D booleans
sk.translate(x, y) .rotate(deg) .scale(s) .mirror("x")

stroke(points, width)            # 2D ribbon along a polyline: round joints
                                 # and caps — THE way to draw smooth curved
                                 # profiles (hooks, arms); generate the
                                 # centerline points with a little math

sk.extrude(h, twist=0, scale_top=1.0)   # twist deg over the height; scale_top flares
sk.revolve(angle=360)            # around Z; sketch x = radius, sketch y = height
```

Twist warning: when extruding with `twist`, the default division count is
safe; if you pass `divisions` yourself, keep the twist per division BELOW
the profile's angular vertex spacing or the swept quads fold into
zero-thickness fins.

Vertical-profile recipe (side profiles: brackets, arms, clip shapes): draw
the profile in sketch coordinates (x = outward, y = up), then

```python
solid = profile.extrude(width).rotate(x=90).rotate(z=90).translate(-width/2, 0, 0)
```

maps sketch-x to world +Y (outward), sketch-y to world +Z (up), and the
extrusion width along world X, centered.

Text is real geometry (bundled DejaVu Sans — identical on every machine):
emboss with `body + text("A", 8).extrude(1.5).translate(...)`, engrave with
`body - text(...).extrude(depth).translate(..., z_surface - depth + 0.01)`.

## Transforms (every call returns a NEW solid)

```python
s.translate(x, y, z)   s.move(x=, y=, z=)      # same thing
s.rotate(x=0, y=0, z=0)                        # applied X then Y then Z
s.scale(2)  s.scale(1, 2, 1)
s.mirror("x")                                  # across plane through origin
s.centered()                                   # bbox center -> origin
s.on_ground()                                  # drop so min Z = 0
```

Inspection properties (use them while debugging): `s.volume`, `s.area`,
`s.bbox`, `s.size`, `s.bbox_center`, `repr(s)` prints size + volume.

## Booleans and combinators

```python
a + b        # union         (also union(a, b, c, ...))
a - b        # difference    (also difference(base, c1, c2, ...))
a & b        # intersection  (also intersection(a, b, ...))
hull(a, b, ...)                # convex hull
```

Hard-won rules:
- **Overlap, never touch.** A union of pieces whose faces merely coincide
  leaves a zero-thickness seam (warned as `union-touching`); sink one piece
  >= 0.1 mm into the other.
- **Cutters pierce through.** Start holes 1 mm below the face and end 1 mm
  past it, or you get a blind hole with a 0.x mm skin (shows up as a
  `thin-wall` finding).
- An empty difference/intersection RAISES with both operands' bboxes — read
  the error, it tells you which translate went wrong.
- A difference that removes nothing records a `noop-difference` warning in
  the report with the cutter's bbox.

## Rounding / fillets

Cheapest first:
1. `rect(...).round_corners(r).extrude(h)` — 2D fillets, use whenever the
   edges you want rounded are vertical.
2. `rounded_box(x, y, z, r)` / `(..., vertical_only=True)` — exact.
3. `solid.chamfer_rim(c)` / `solid.round_rim(r)` — break ALL edges on the
   top rim (`bottom=True` for the base, `z=` for another plane). Works on
   any outline, holes included — a container mouth gets both sides of its
   wall broken at once. Needs roughly vertical walls at that rim (boxes,
   cylinders, extrusions). Exact and fast.
4. `solid.fillet(r)` — rounds ALL edges everywhere via Minkowski
   morphology. Accurate but slow; apply once on the finished shape.
5. `solid.grow(r)` / `solid.shrink(r)` — Minkowski dilate/erode when you
   need an offset shell.

## Freeform deformation

```python
s.refine(edge_mm)      # subdivide long edges (do it BEFORE warp)
s.warp(fn)             # fn(x, y, z) -> (x, y, z), pure and deterministic
```

```python
def bulge(x, y, z):
    s = 1 + 0.25 * math.sin(math.pi * z / H)
    return x * s, y * s, z
vase = vase.refine(3).warp(bulge)
```

Keep deformations gentle — extreme warps self-intersect. For transitions
between sections use `parts.loft`; for text on cylinders,
`parts.wrapped_text` (both in the catalog).

## Named parts

```python
emit(solid, name="base_plate")            # snake_case, unique
emit(other, name="lid", color="amber")    # optional color (steel, amber,
                                          # sage, clay, slate, olive, teal,
                                          # mauve, gray, dark, light, #hex)
emit(body, name="shell", color="#b01020",
     material="glossy")                   # visual FINISH for the live
                                          # viewer + GLB: "steel",
                                          # "aluminum", "chrome", "brass",
                                          # "metal", "plastic", "glossy",
                                          # "matte", "rubber", "glass" or
                                          # {"metallic":0..1,
                                          #  "roughness":0..1,
                                          #  "opacity":0..1}. Measurements
                                          # and evidence renders ignore it.
```

Only emitted parts exist in the output. `--part lid` builds one of them;
the report analyses each part separately plus every pair.

## Assemblies

```python
part = from_model("path/to/model.py", "part_name")   # reuse a built part
mesh = from_stl("motor.stl")                         # STL/OBJ/PLY/3MF import
place(part, name="bracket", at=(0, 0, 8), rotate=(0, 0, 90))
```

`place()` rotates around the origin FIRST, then translates. Positions are in
one shared coordinate space; report.json `pairs[]` then gives collisions
(exact overlap bbox + volume + move suggestion) or min clearance per pair.

## Images as input (photos, drawings, logos, heightmaps)

```python
logo = image_outline("logo.png", width=60)        # dark shapes -> Sketch,
                                                  # holes kept; give the REAL
                                                  # size via width= OR height=
relief = image_heightfield("map.png", width=90,   # brightness -> solid relief
                           relief=6, base=1)      # (invert=True: lithophane)
```

`image_outline` is for faithful FLAT shapes only (logos, gaskets,
stencils); never trace a photo of a 3D object and call it the object.
Build with `--ref photo.png` to get `renders/00_reference_vs_render.png`
(reference beside render) after every build. Full workflow, size-anchor
estimation rules and honesty rules: `references/from-image.md`.

**Declare the intent** with `expect()` so the build FAILS when a fit drifts,
instead of you re-judging numbers every iteration:

```python
expect("lid", "box", status="touching")            # meant to rest on it
expect("gear_a", "gear_b", clearance=(0.15, 0.35)) # backlash band
expect("card", "lid", clearance=0.5)               # at least 0.5 mm
```

**Shared dimensions** across the files of an assembly: put them in a
`params.py` next to the models and `from params import *` in each one.
Duplicate constants that drift between box.py and lid.py are how printed
fits die silently.

**Ghost parts** (`place(..., ghost=True)` / `emit(..., ghost=True)`) are
reference volumes: keep-out zones, connector envelopes, swept insertion
paths. They are fully measured in `pairs[]` and `expect()`, drawn as X-ray
outlines, and excluded from print checks, exports and material totals.

**Insertion checks** with `parts.swept(solid, dx=, dy=, dz=)`: place the
swept volume of the moving part as a ghost and declare its clearance.
Two rules learned the hard way:
- Sweep the RIGID body only. Snap-fit hooks interfere BY DESIGN while
  flexing past a wall — judge their interference DEPTH (the overlap patch
  thickness in `pairs[]`) against the hook's allowed deflection, never
  "zero contact".
- Stop the sweep just above the seated position (0.2 mm), or the final
  resting contact reads as a violation of a `clear` expectation.

## Parametric style

Write dimensions as named constants at the top and derive everything:

```python
WALL = 2.5
CLEAR = 0.2
inner_x = card_x + 2 * CLEAR
outer_x = inner_x + 2 * WALL
```

This is what makes iteration cheap: change one number, rebuild, re-inspect.

## Common errors (verbatim ids you will see)

| id / code          | what happened                              | fix |
|--------------------|--------------------------------------------|-----|
| `empty-geometry`   | boolean produced nothing                   | read the bboxes in the error; a cutter swallowed the part or operands do not overlap |
| `bad-argument`     | impossible parameter (r too big, n < 3...) | the message names the argument and the valid range |
| `scene-error`      | emit() misuse (dup name, empty solid, dict)| emit each dict entry separately; unique snake_case names |
| `model-error`      | plain Python error in your file            | the failing line is quoted; fix and rebuild |
| `union-touching`   | union pieces only touch, no shared volume  | overlap them >= 0.1 mm |
| `noop-difference`  | cutter removed no material                 | move the cutter; render a --slice to see where it is |
