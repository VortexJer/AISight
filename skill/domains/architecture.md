# Architecture, interiors and massing

Load for: buildings, rooms, floor plans in 3D, site massing, interior
layouts, architectural models (printed or visual).

Scale changes the method. At 1:1 a building is millions of mm; do not
model a brick. Model the ENVELOPE and the SPACES, and let features
appear only where they carry meaning.

## Work in real millimetres, print at a scale

Model at 1:1 in mm, always. Scale only at export:
```python
SCALE = 1 / 100                     # 1:100 architectural model
place(building.scale(SCALE, SCALE, SCALE), name="massing_1_100")
```
A 12 m facade is `12000`. Never model "12" and call it metres — every
tool, every report and every wall check speaks mm.

At 1:100, a 100 mm wall becomes 1 mm: below the printable floor. So for
printed models, walls get a MINIMUM MODEL thickness (1.5-2 mm at model
scale) regardless of the real wall — say this to the user explicitly,
it is a deliberate distortion.

## Dimensions that are effectively standards

| thing | mm |
|---|---|
| ceiling height, residential | 2400-2700 |
| door, interior | 800-900 w x 2000-2100 h |
| door, main entrance | 900-1000 x 2100 |
| window sill height | 900 (1100+ in bathrooms) |
| corridor width | >= 1200 (public), >= 900 (private) |
| stair riser | 170-190 |
| stair tread (going) | 260-300 |
| stair rule | 2*riser + tread = 600-640 |
| stair headroom | >= 2000 |
| wall, interior partition | 100-125 |
| wall, exterior | 250-400 |
| floor slab | 200-300 |
| wheelchair turning circle | 1500 |
| kitchen counter depth | 600 |
| parking bay | 2500 x 5000 |

## Method: plan -> massing -> openings

1. **The plan is a Sketch.** Draw the footprint once, in mm:
   ```python
   footprint = polygon([(0, 0), (12000, 0), (12000, 8000), (0, 8000)])
   ```
2. **Walls from the plan** with `offset` — this is why the plan is a
   sketch and not four boxes:
   ```python
   WALL = 250.0
   shell = (footprint.offset(0) - footprint.offset(-WALL)).extrude(2700)
   ```
   `parts.container(footprint, height=2700, wall=250, floor=200)` does
   the same in one call when you want a floor too.
3. **Storeys are a pattern**, not copy-paste:
   ```python
   tower = parts.linear_pattern(storey, count=6, dz=3000)
   ```
4. **Openings last**, as cutters through the wall:
   ```python
   door = box(900, WALL + 20, 2100)
   shell = shell - door.translate(3000, 0, 0)
   window = box(1400, WALL + 20, 1200)
   shell = shell - window.translate(7000, 0, 900)   # sill at 900
   ```
5. **Semantic features — this is where they matter most:**
   ```python
   emit(shell, name="ground_floor", features=[
       {"type": "door", "at": [3000, 0, 0], "size_mm": [900, 2100]},
       {"type": "window", "at": [7000, 0, 900], "size_mm": [1400, 1200]},
   ])
   ```
   report.json then says what the holes MEAN. A downstream agent reads
   doors and windows, not triangles.

## Plans and sections are the deliverable

Architecture is read in section, not in iso:
```bash
solidsight build model.py --slice z=1500   # the floor plan (cut at 1.5 m)
solidsight build model.py --slice y=4000   # the long section
solidsight build model.py --views iso,top,front,iso_back
solidsight drawing model.py                # dimensioned PDF
```
`--slice z=1500` IS the floor plan — 1.5 m is the conventional cut
height (above sills, below lintels). Look at it: rooms that do not
connect, walls that do not meet, a stair that lands in a wall are all
obvious there and invisible in iso.

## The five ways architectural models fail

1. **Unit chaos.** Metres, centimetres and mm in the same file. mm.
   Always. Everywhere.
2. **Rooms that do not close** — walls modeled as separate boxes that
   touch exactly. Coplanar touching = zero-thickness seams (the engine
   warns `union-touching`). Build walls from ONE offset plan, or overlap
   0.1 mm.
3. **Printed at scale, walls vanish.** 100 mm at 1:100 = 1 mm. Check
   `--print-safe` AFTER scaling, not before.
4. **Stairs that break the rule.** 2R + T outside 600-640 = a stair
   nobody can climb. It is arithmetic; do it.
5. **No section was ever looked at.** Then nothing about the interior
   was ever verified.

## Done means

- `--slice z=1500` (plan) and at least one vertical section, LOOKED at.
- Every dimension in the table above that applies, quoted and checked.
- Doors/windows/stairs recorded as `features=[...]`, not just voids.
- If printed: scaled first, then `--print-safe`, with the model-scale
  wall distortion stated to the user.
- Volumes/areas quoted from the report when the user asks "how big" —
  they are exact and free.
