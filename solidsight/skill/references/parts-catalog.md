# solidsight parametric parts catalog

Everything here is available in model files as `parts.<name>(...)`. Compose
these instead of re-deriving mechanical geometry. `solidsight catalog <name>`
prints the same signatures at the terminal.

## Holes (the workhorse of mechanical detail)

```python
parts.hole(d, depth, counterbore=(D, h), countersink=D | (D, angle),
           chamfer=0.0, drill_point=False, through_margin=1.0)
    # drilling CUTTER: entry at the origin, drilling -Z; subtract it.
parts.bolt_circle(cutter, count, d)
    # n copies on a circle of diameter d around Z (first on +X)
```

Orient onto any face with `.aim(direction)` (the direction the tool
travels), then translate the entry point onto the surface:

```python
block -= parts.hole(5.5, 12, counterbore=(9.5, 5.5)).translate(10, 0, TOP_Z)
block -= parts.hole(4.2, 10, chamfer=0.4).aim("-y").translate(0, WALL_Y, 8)
flange -= parts.bolt_circle(parts.hole(6.6, 99), 6, 72).translate(0, 0, T)
```

Tapped holes: model the tap drill (`hole(d=4.2)` for M5) with `chamfer` +
`drill_point=True`; only use `parts.iso_thread(internal=True)` when the
thread must actually work.

## Gears

```python
parts.spur_gear(module, teeth, thickness, bore=0.0,
                pressure_angle=20.0, backlash=0.0)
```

Standard involute spur gear, centered, base on Z=0.

Meshing rules (the report's pair clearance will confirm them):
- Both gears MUST share `module` and `pressure_angle`.
- Center distance = `module * (teeth_a + teeth_b) / 2`.
- Rotate one gear by `180 / teeth` degrees so teeth interleave.
- Use `backlash=0.15..0.25` for printed gears; expect the pair analysis to
  report roughly that clearance when meshed correctly.

```python
g = parts.spur_gear(module=2, teeth=20, thickness=8, bore=5, backlash=0.2)
p = parts.spur_gear(module=2, teeth=12, thickness=8, bore=5, backlash=0.2)
emit(g, name="gear")
emit(p.rotate(z=180/12).translate(2*(20+12)/2, 0, 0), name="pinion")
```

## Threads, bolts, nuts

```python
parts.iso_thread(d, length, pitch=None, internal=False, clearance=0.15,
                 chamfer=True, segments=32, left_hand=False)
parts.bolt(d, length, pitch=None, head_af=None, head_h=None)
parts.nut(d, pitch=None, af=None, h=None)
```

- `pitch` defaults to ISO coarse for standard sizes (M2..M20); pass it
  explicitly otherwise.
- External thread (default): a ready threaded rod, ends chamfered.
- `internal=True` returns an OVERSIZED cutter — SUBTRACT it from a body to
  make a working tapped hole/nut. Keep the same `clearance` on both sides of
  a printed pair (default 0.15 per side).

```python
block = box(20, 20, 12)
tap = parts.iso_thread(8, 14, internal=True).translate(0, 0, -1)
emit(block - tap, name="tapped_block")
```

## Hinge (print-in-place)

```python
parts.hinge(length=40, leaf=15, t=3, knuckles=5, pin_d=3, clearance=0.4)
# -> {"leaf_a": Solid, "leaf_b": Solid}   (emit each separately)
```

Assembled and interleaved as returned; leaf_a carries the fused pin,
leaf_b's knuckles are bored with `clearance`. Odd knuckle counts only.
Printed flat as returned, it rotates after printing.

## Snap fit

```python
parts.snap_clip(length=12, width=6, t=1.6, hook=1.2, hook_len=3)
parts.snap_slot(width=6, t=1.6, hook=1.2, hook_len=3, wall=2.0,
                clearance=0.25, height=None)
```

- Clip: base on Z=0, arm up, hook pointing +Y. Rotate/attach as needed.
- Slot: a cutter for the window the hook latches into; subtract from a wall
  lying in the XZ plane (thickness in +Y, window bottom at Z=0). Move it
  into position, `.rotate(z=90)` for X-facing walls, `.mirror()` for the
  opposite side.
- Match width/t/hook/hook_len between clip and slot, same clearance both.
- Clip mounted upside-down (hanging from a lid): pass
  `height=hook_len*0.6 + 2*clearance` to snap_slot so the insertion ramp
  clears the window; the retention edge sits `length - 0.6*hook_len` from
  the clip base. Worked example: `examples/02-snap-box`.

## Enclosures

```python
parts.box_with_lid(inner_x, inner_y, inner_z, wall=2.0, lid_h=8.0,
                   lip_h=4.0, fit_clearance=0.2, r=2.0,
                   position="beside")        # or "assembled"
# -> {"box": Solid, "lid": Solid}

parts.container(profile_sketch, height, wall=2.0, floor=None)
    # uniform-wall open vessel from ANY 2D profile

parts.standoff(h, od=6.0, id_=2.5, base_od=0.0, base_h=0.0)
    # screw boss; add base_od/base_h for a conical strength flare

parts.hex_grid(x, y, t, cell=8.0, wall=1.6)
    # CUTTER: honeycomb field of hex prisms — subtract from any wall/floor
    # to add vents; make t = wall + 2 and sink it 1 mm so it pierces

parts.honeycomb_panel(x, y, t, cell=8.0, wall=1.6, border=4.0)
    # ready-made SOLID vented panel (use hex_grid to vent an existing wall)
```

Venting an enclosure floor:

```python
tray = tray - parts.hex_grid(70, 45, FLOOR + 2, cell=8, wall=2).translate(0, 0, -1)
```

## Patterns

```python
parts.linear_pattern(solid, count, dx=0, dy=0, dz=0)
parts.grid_pattern(solid, nx, ny, dx, dy)
parts.circular_pattern(solid, count, angle=360)   # around Z; move the seed
                                                  # off-axis first
```

Patterns union their copies — pattern CUTTERS then subtract once:

```python
hole = cylinder(h=plate_t + 2, d=4.5).translate(0, 0, -1)
plate = plate - parts.grid_pattern(hole, 2, 2, 44, 28).translate(-22, -14, 0)
```

## Sweeps, lofts, curved text

```python
parts.tube_path(points_3d, d, segments=24)
    # round tube along a 3D polyline (chained capsule hulls): hooks,
    # handles, wire guides, curved feet. Sample curves every few degrees.

parts.loft(profiles, heights)
    # smooth transition through CONVEX sections stacked in Z: funnels,
    # ducts, adapters. loft([circle(d=40), ngon(6, d=28)], [0, 30])

parts.wrapped_text(string, d, size=10, depth=1, outward=0.5)
    # text wrapped around a d-cylinder, centered on +X. Subtract to
    # engrave; emboss with depth=0.3, outward=1.5 and union.

parts.swept(solid, dx=, dy=, dz=, steps=None)
    # the volume a part passes through while translating: place as a
    # GHOST + expect() to test insertion paths (rigid bodies only —
    # snap hooks interfere by design; judge their depth, not contact)
```

For flat/ribbon curved shapes prefer the 2D `stroke()` + extrude (see
design-language.md).

## Sizing cheat sheet for printed parts

| feature                    | value |
|----------------------------|-------|
| min structural wall (FDM)  | 1.6 mm (2+ perimeters) |
| min decorative wall        | 1.2 mm (print-safe default floor) |
| sliding fit clearance      | 0.2-0.3 mm per side |
| press/friction fit         | 0.10-0.15 mm per side |
| snap-fit working clearance | 0.25 mm |
| M3/M4 clearance holes      | 3.4 / 4.5 mm |
| unsupported overhang limit | ~50 deg from vertical |
| emboss/engrave depth       | 0.8-1.5 mm, stroke >= 1.2 mm |### loft_sections(sections, stations, axis="x") — styled bodies

Ruled loft through closed 2D polylines with the SAME point count —
non-convex sections welcome (a car section is concave at the shoulder).
Corresponding points weld station to station, like boat-buck stations;
generate every section from ONE parametric template so they line up.
End caps are triangulated exactly. This is the tool `references/
car-bodies.md` is built on; `loft()` below is for CONVEX funnels only.


