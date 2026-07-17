# Game-ready and real-time assets

Load for: assets destined for a game engine, real-time renderer, WebGL,
AR/VR — anything where the deliverable is a GLB/OBJ that a GPU draws at
60 fps, not an object that gets manufactured.

The constraints invert. Nothing here gets printed, so walls and cavities
stop mattering — and two things nobody else worries about become the
whole job: **triangle budget** and **what the mesh means downstream**.

## Triangle budgets (real, current-generation)

| asset | triangles |
|---|---|
| hero character | 40k-100k |
| NPC / secondary character | 8k-25k |
| weapon / hero prop | 5k-15k |
| environment prop (crate, barrel) | 300-2000 |
| architectural module | 1k-5k |
| vehicle, playable | 30k-80k |
| mobile / VR: halve everything above | |
| LOD chain | LOD0 100 %, LOD1 ~50 %, LOD2 ~25 %, LOD3 ~10 % |

Read your actual count before claiming anything:
```bash
solidsight build model.py --glb --json | grep -i triangle
```
or in the report: `parts.<name>.triangles`. CSG output is NOT frugal —
a `refine(1.0)` organic form will be 200k triangles and blow every
budget above. Iterate coarse; the segment count is yours to control:

```python
cylinder(h=20, d=10, segments=16)      # 16 sides, not the 64 default
sphere(d=30, segments=24)
circle(12, segments=20)
```
`DEFAULT_SEGMENTS` is tuned for manufacturing accuracy, not for frame
budget. On a 300-triangle barrel, `segments=12` is invisible and free.

## Export: GLB is the format

```bash
solidsight build model.py --glb          # combined: keeps part names + colors
solidsight build model.py --obj          # when the pipeline wants OBJ
solidsight convert thing.stl thing.glb   # standalone conversion
```
The combined GLB preserves **part names and colors** — that is your
material assignment and your object hierarchy on the other side. So:
one `emit()` per thing that must be separately selectable, moveable or
shaded in the engine. Name them the way the engine should show them
(`wheel_fl`, not `part3`).

**Watertightness is not a goal here** — and `solidsight convert` will
tell you `watertight: False` on a GLB because the exporter splits
vertices for normals. That is correct and expected for a render mesh; do
not "fix" it.

## What solidsight does and does not do here

Be honest about the boundary:

| need | solidsight | not solidsight |
|---|---|---|
| exact base mesh, deterministic | yes | |
| part names + colors into GLB | yes | |
| triangle count, per part | yes (report) | |
| segment/LOD control | yes (manual: rebuild coarser) | automatic decimation |
| UV unwrapping | NO | Blender/xatlas |
| texture baking, normal maps | NO | Blender/Substance |
| rigging, skinning | NO (see AnimationSight for motion ANALYSIS) | Blender |
| PBR material graphs | NO | the engine |

Say this plainly to the user rather than pretending. The right pipeline
is: solidsight builds the exact geometry -> export GLB -> unwrap/bake/rig
elsewhere. What you give them is a clean, named, budget-checked base
mesh with real dimensions — which is exactly the part that hand-modeling
gets wrong.

## LODs, deterministically

There is no auto-decimator, and that is fine — you have something better,
the parametric source:
```python
# params.py
LOD = 0
SEG = {0: 64, 1: 32, 2: 16, 3: 8}[LOD]
```
```bash
solidsight build model.py --glb --out lod0     # with LOD=0
# edit LOD, rebuild -> lod1/, lod2/ ...
solidsight diff lod0/ lod1/                    # exactly what changed
```
Each LOD is a real build from the same source: identical proportions,
lower budget, reproducible. That beats decimating a mesh and hoping.

## Scale and orientation for engines

- **Unity/Unreal/glTF work in metres**; solidsight works in mm. A 2 m
  crate is `2000`. On import: scale 0.001. State this.
- **Y-up vs Z-up**: glTF is Y-up, solidsight is Z-up. Most importers
  handle it; if the asset lands on its face, that is why. Say it rather
  than pre-rotating and confusing everything downstream.
- **Origin matters**: a door should have its origin at the hinge, a
  wheel at its axle. Model it in place, then translate so the origin is
  the pivot the engine needs.

## The five ways game assets fail

1. **200k triangles for a barrel.** Nobody checked the count. It is in
   the report, per part.
2. **One giant unnamed mesh** — nothing selectable, one material.
   `emit()` per meaningful object, named for the engine.
3. **"Fixed" the non-watertight GLB** — wasted effort on a non-problem.
4. **Millimetres imported as metres** — a 2 km crate. State the unit.
5. **Promised UVs/textures/rigging.** Out of scope; say so up front.

## Done means

- Triangle count per part quoted against the budget table.
- `--glb` exported; parts named as the engine should show them; origins
  at real pivots.
- `--turntable 8` looked at (this asset is judged from every angle).
- Units and up-axis stated for the import.
- Mode `--free`. Walls/cavities/overhangs are noise here — say that you
  are ignoring them and why, rather than silently ignoring them.
