# Enclosures, brackets and jigs

Load for: project boxes, PCB housings, sensor cases, wall mounts,
brackets, adapters, drill guides, fixtures, machine jigs.

The most common request and the least forgiving: the part must fit real
hardware you did not model, and it fails as a physical object, not as a
picture. Everything here is `--print-safe` from build one.

## Fixed numbers you are allowed to assume

FDM, 0.4 mm nozzle, PLA/PETG. Quote these to the user when you use them.

| thing | value | why |
|---|---|---|
| wall thickness | 2.0 mm (3 perimeters), 2.4 mm if it takes load | 1.2 mm is the floor, not a design target |
| floor / ceiling | 1.2 mm min, 1.6 mm typical | 4-6 layers at 0.2 mm |
| screw boss OD | 2.5 x screw d | thinner splits along layer lines |
| self-tapping pilot hole | 0.8 x screw d (M3 -> 2.4) | into plastic, no insert |
| clearance hole | screw d + 0.4 (M3 -> 3.4) | printed holes come out undersized |
| heat-set insert hole | insert OD - 0.1, depth +0.5 | M3 insert: 4.0 dia x 5.5 |
| lid / part sliding fit | 0.2-0.3 mm per side | below 0.15 they weld together |
| press fit | 0.05-0.1 mm interference | |
| snap hook overlap | 1.0-1.2 mm on a 1.6 mm arm | see `mechanisms.md` for the math |
| PCB standoff height | 4-6 mm | clears through-hole solder joints |
| PCB edge clearance | 1.5 mm around the board | |
| USB-C cutout | 9.4 x 3.6 mm + 0.4 clearance | measure the actual connector when you can |
| corner radius | 2-3 mm outside, 1-2 mm inside | printed sharp corners chip |
| rib thickness | 0.6-0.8 x wall | thicker ribs sink-mark and warp |

Anything the user's real hardware decides — PCB size, connector
positions, mounting-hole pitch — is a QUESTION, not an assumption. Ask
once, up front, in the same message as the detail-level question.

## The build order that works

Build it in this order and the report catches mistakes while they are
still cheap to fix:

1. **Envelope first.** `parts.container(profile, height, wall, floor)`
   gives a uniform-wall open box from ANY 2D profile — do not hand-build
   inner/outer boxes and subtract, it is how you get 0.75 mm walls by
   accident. For a straight rectangular box with a lid,
   `parts.box_with_lid(inner_x, inner_y, inner_z, wall=2, lid_h=8,
   lip_h=4, fit_clearance=0.2)` returns `{"box", "lid"}` already fitted.
2. **Place the contents as GHOSTS before cutting anything.**
   ```python
   pcb = box(60, 40, 1.6)
   place(pcb, name="pcb", at=(0, 0, 6), ghost=True)   # keep-out, not printed
   place(parts.component("nema17", length=40), name="motor",
         at=(0, 0, 30), ghost=True)
   ```
   Ghosts are measured in `pairs[]` but never exported. Every clearance
   you care about becomes a declared spec instead of a hope:
   ```python
   expect("pcb", "case", clearance=(0.4, 1.2))   # build FAILS if it drifts
   ```
3. **Bosses and mounts**, then **cutouts**, then **vents**, then
   **fillets last** (fillet before boolean = the fillet gets cut in half
   and the build gets slow).
4. `--print-safe --slice z=<through the bosses>` and LOOK. Internal
   geometry is invisible from outside; the slice is not optional.

## The five ways enclosures actually fail

1. **Wall thinned by a cutout you did not think about.** A connector
   window 0.6 mm from a corner radius leaves a sliver. The report's
   `thin-wall` gives the exact point — go there with
   `--focus X,Y,Z,8 --slice`.
2. **Sealed cavity.** A boss buried under a floor, an inclined tapped
   hole that never breaks out. `internal-cavity` FAIL; fix with
   `through_margin=` on `parts.hole` so the cutter exits the surface.
3. **The lid does not come off / does not stay on.** Print clearance is
   real: `fit_clearance=0.2` is a starting point, and
   `expect("box", "lid", clearance=(0.15, 0.35))` pins it.
4. **Nothing to print on.** Bosses floating in mid-air over a cavity,
   overhang > 50 deg under every rim. Chamfer 45 deg under bosses; for
   holes in vertical walls use a teardrop (a hole + a small `wedge` on
   top) so it prints without support.
5. **It fits the model and not the world.** Screw goes in from the
   outside, but the screwdriver cannot reach; the cable has no bend
   radius; the board cannot be lowered in past the standoffs. Sweep the
   insertion path: `parts.swept(pcb, dz=-20)` and check it against the
   case.

## Recipes

**Vented lid** (hex is stronger and prints better than slots):
```python
lid = lid - parts.hex_grid(50, 30, t=5, cell=7, wall=2).translate(0, 0, -1)
```

**Wall mount with a keyhole** (screw head passes, then hangs):
```python
key = (cylinder(h=4, d=8).translate(0, 0, -1)
       + box(4.4, 12, 4).translate(0, -6, -1))     # slot down from the hole
back = back - key.translate(0, 0, 3)
```

**PCB standoffs from the board's real hole pattern:**
```python
for hx, hy in [(-25, -15), (25, -15), (-25, 15), (25, 15)]:   # ASK for these
    case = case + parts.standoff(h=5, od=6, id_=2.4).translate(hx, hy, 2)
```
`id_=2.4` is the pilot for an M3 self-tapper; for a heat-set insert use
`id_=4.0` and `h >= 6`.

**Connector window**, always in the wall the connector actually faces:
```python
usb = box(9.8, 12, 4.0)                     # 9.4 x 3.6 + 0.4 clearance
case = case - usb.translate(0, WALL_Y, 8)   # sunk through the wall
```
Then prove it: `solidsight query model.py ray 0 -50 8 0 1 0` must show
the window open all the way through, and nothing else.

## Done means

- `--print-safe` exit code 0, one shell per part, min wall >= 2.0 (or
  the number you told the user, with the reason).
- Every `expect()` MET, including ghost clearances.
- A `--slice` render through the bosses and one through the connectors,
  looked at.
- `solidsight cost model.py --process fdm` quoted if they will print it.
- Parts exported `--stl` in PRINT orientation (`.on_ground()`), not in
  assembly position.
