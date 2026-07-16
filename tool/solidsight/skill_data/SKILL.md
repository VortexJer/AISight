---
name: solidsight
description: "Use whenever the user asks to design, model, CAD, or 3D-print a physical part, enclosure, mechanism, or assembly — or to inspect/fix an existing solidsight model. Parametric Python in; deterministic geometry, PNG renders, and a machine-readable validation report out. Built exclusively for AI agents: you are blind until you render, and this tool is how you see."
---

# /solidsight

Design 3D parts with code, then SEE and MEASURE what you made: every build
produces PNG renders from several angles plus a `report.json` with volume,
bounding box, shells, wall thickness, overhangs, sealed cavities and
part-to-part collisions/clearances. The loop is: write code -> build ->
inspect renders + report -> adjust -> repeat. Never trust geometry you have
not rendered and validated.

## Usage

```
solidsight build model.py                        # free mode (default): report everything, enforce nothing
solidsight build model.py --print-safe           # enforce 3D-printability (fails on thin walls, cavities, split shells)
solidsight build model.py --out DIR              # output dir (default: <model dir>/out)
solidsight build model.py --views iso,front,right,top,back,left,bottom,iso_back
solidsight build model.py --turntable 8          # 8 orbit frames
solidsight build model.py --slice z=5 --slice x=0   # cross-section renders (repeatable)
solidsight build model.py --part lid             # build/validate only one named part
solidsight build model.py --stl                  # export binary STL per part + combined
solidsight build model.py --3mf                  # export 3MF per part + combined
solidsight build model.py --exploded             # exploded view render of multi-part scenes
solidsight build model.py --focus 70,43,24,25    # zoom all views onto a sphere (X,Y,Z,R) — inspect one feature up close
solidsight build model.py --min-wall 0.8 --max-overhang 45 --allow-multiple-shells
solidsight build model.py --json                 # full report JSON on stdout

solidsight query model.py point X Y Z            # INSIDE | OUTSIDE | ON_SURFACE + distance
solidsight query model.py ray OX OY OZ DX DY DZ  # every surface crossing along a ray
solidsight query model.py section z=4            # ASCII material grid at a cut plane
solidsight query model.py voxels --res 1         # voxel grid + sealed-cavity detection
solidsight query model.py voxels --layer 5       # one Z layer as ASCII
   (all query ops accept --part NAME and --json)

solidsight diff old_out/ new_out/                # what did my change actually change? (volumes, walls, checks)

solidsight catalog                               # list parametric parts (gears, threads, hinges, clips...)
solidsight catalog spur_gear                     # full docs for one part
solidsight version
```

Exit codes: 0 ok, 1 build error (bad model code), 2 print-safe validation
failed.

## What You Must Do When Invoked

Follow these steps in order. Do not skip steps.

### Step 0 - Ensure solidsight is installed

```bash
solidsight version || pip install "git+https://github.com/VortexJer/SolidSight#subdirectory=tool"
```

If the user gave you a checkout of the repo instead: `pip install ./tool`.
The first run self-installs this skill into `~/.claude/skills/solidsight`
and keeps it updated; `solidsight uninstall` removes the skill and the
package together.

### Step 1 - Write the bill of parts BEFORE any geometry code

Decompose the request into a short list of named functional parts and key
dimensions. Put it at the top of the model file as a comment:

```python
# bill of parts (mm):
#   base_plate  60 x 40 x 5, four M4 holes
#   wall        upright at back, 35 tall, two M4 holes
#   rib         triangular gusset tying wall to plate
```

Every part name here becomes an `emit(solid, name="...")` at the end of the
file. If you cannot write this list, you do not understand the request yet —
ask the user, do not guess geometry.

**Technical objects — ask the detail level.** If the request is a real
technical object (engine, gearbox, housing, pump...) and the user did not
say how faithful it must be, ask ONE question: *representative model, or
detailed functional model (every bolt pattern, port, gallery, rib)?*
For detailed mode, load `references/detail-mode.md` and replace the short
bill of parts with a per-region **Feature Specification**, then build and
verify region by region. If the user gives no further specifications,
**research the object on the web yourself first** (anatomy, dimensions,
feature counts, standards) and tag every spec line `[researched]`,
`[standard]` or `[assumed]` — detail-mode.md defines the research step. Detail lives in features (holes, bosses, flanges,
tunnels, pockets), and the catalog has first-class tools for them:
`parts.hole` (counterbore/countersink/chamfer/drill-point), `.aim()` for
drilling into any face, `parts.bolt_circle`, patterns.

### Step 2 - Check the catalog before deriving geometry

Run `solidsight catalog`. Gears, threads, bolts, nuts, hinges, snap clips,
boxes with lids, standoffs, honeycomb panels, and patterns already exist as
tested parametric parts (`parts.spur_gear(...)`, `parts.iso_thread(...)`, ...).
Composing catalog parts is always better than re-deriving an involute or a
helix from math. Full signatures and pairing rules (gear meshing distance,
thread clearances, clip/slot matching): `references/parts-catalog.md`.

### Step 3 - Build the model incrementally, in this order

1. Base forms first (`box`, `cylinder`, extruded/revolved sketches).
2. Features and cuts (holes, pockets, windows) via booleans.
3. Assembly positioning.
4. Rounding LAST (`round_corners` on 2D profiles is cheap; 3D `.fillet()` is
   expensive — apply once, at the end, if at all).

Core rules (full language reference: `references/design-language.md`):
- Units are mm, angles degrees. Same code always produces identical geometry.
- Primitives sit centered on XY with their base on Z=0 (the build plate).
- Booleans: `a + b`, `a - b`, `a & b`. Sketches extrude with `.extrude(h)`.
- **Overlap, never touch**: pieces that must fuse need >= 0.1 mm of shared
  volume; cutters must pierce >= 1 mm past the faces they cut. Coincident
  faces create zero-thickness seams and blind holes — solidsight warns when
  it detects them; take those warnings seriously.
- End the file with `emit(solid, name="snake_case_name")` per part.

### Step 4 - Build and LOOK after every geometric change

```bash
solidsight build model.py            # or --print-safe, see Step 6
```

Then, non-negotiable:
1. **Open the renders with the Read tool and actually look at them** (if you
   have vision): shape, proportions, holes where they belong, parts where
   they belong. The legend maps colors to part names; the footer gives exact
   bbox dimensions; the grid squares are 10 mm.
2. **Read the checks in report.json** (always, vision or not). Each check
   carries `where` (coordinates) and a `try:` suggestion.
3. If anything is off, fix the code and rebuild. Never declare a design
   finished without having built and inspected the LAST version of the code.

`--slice z=H` renders a filled cross-section — use it whenever inner walls,
pockets or fits are involved; outside views cannot show them.
`--focus X,Y,Z,R` zooms every view onto one feature — use it when a detail
(a hole, a clip, a boss) is too small to judge in the full-part frame.
Pick a view that FACES the feature (a +Y feature needs iso_back/back/left,
not the default iso) or you will zoom onto the part's far side.
After changing a model, `solidsight diff old_out new_out` lists exactly
what moved: per-part volume/size/wall deltas and checks that appeared or
disappeared — confirm your change did what you meant and nothing else.

### Step 5 - Use exact queries when looking is not enough

Renders answer "does it look right?". The query API answers "is it
geometrically right, with mathematical certainty" — and it works without
vision:

- A render looks solid but you must prove there is no sealed pocket inside:
  `solidsight query model.py voxels` (flood-fill cavity detection), or cast
  `ray` through the suspect line and count crossings (2 material segments
  where you expected 1 = cavity or second shell on that line).
- Verify a wall thickness at an exact plane: `section z=4` and read the `#`
  band widths (cell size is printed), or `ray` across the wall and read
  `material_segments[].thickness_mm`.
- Confirm a point is inside/outside a part: `point X Y Z` (e.g. checking a
  screw hole really pierces a boss).
- Layer-by-layer shape/symmetry check: `voxels --layer N`.

Interpretation guide for every field: `references/report-guide.md`.

### Step 6 - Choose the validation mode deliberately

- `--print-safe` — the part will be physically manufactured (FDM/resin).
  Enforces: watertight, one shell per part, min wall (default 1.2 mm), warns
  on overhangs past 50 deg and parts floating off the plate; FAILS on sealed
  internal cavities. Exit code 2 on failure.
- `--free` (default) — visual/artistic exploration. Same metrics reported,
  nothing enforced.

If the user says "print", "printable", "PLA", "resin", "manufacture" — use
`--print-safe` from the first build, not as a final afterthought.

### Step 7 - Assemblies: position, collide, measure, repeat

For multiple interacting parts (or checking fits between separately designed
parts):

```python
from solidsight import *
body  = from_model("../box/model.py", "box")   # reuse another model's part
motor = from_stl("nema17.stl")                 # import external mesh
place(body,  name="body")
place(motor, name="motor", at=(0, 0, 8), rotate=(0, 0, 90))
expect("motor", "body", status="touching")     # declare the INTENT
expect("motor", "lid", clearance=1.0)          # build FAILS if violated
```

Every multi-part build writes `pairs[]` into report.json: for each pair of
parts either the exact collision (overlap bbox + volume + a concrete move
suggestion) or the minimum clearance between their surfaces. **Declare every
fit that matters with `expect()`** (touching / clear / clearance range —
e.g. gear backlash `clearance=(0.15, 0.35)`): the report then answers
pass/fail against your intent instead of numbers you must re-judge each
iteration. Share dimensions between the assembly's model files through a
`params.py` next to them (`from params import *`). Iterate until:
- zero collisions, and
- every declared expectation is met (clearances 0.15-0.3 mm for printed
  sliding/snapping fits; "touching" only for parts meant to press together).

Use `--exploded` to render mating faces, and `--slice` through the joint to
see engagement. Example of the full loop: `examples/05-assembly/`.

### Step 8 - Definition of done (checklist)

Do not report the task complete until ALL of these hold for the final code:

1. Renders from at least 4 angles reviewed (`iso,front,right,top`), plus a
   `--slice` through any internal feature.
2. `report.json` status is `ok`, or every remaining `warn` is explained to
   the user and accepted (e.g. supported overhangs).
3. Dimensions in the report's `scene.size` / part bboxes match the user's
   spec numbers — check them one by one against the bill of parts.
4. Assemblies: `pairs[]` shows zero collisions and sensible clearances.
5. One aesthetics pass on the renders: proportions, symmetry, consistent
   wall thicknesses, aligned features. Ugly-but-valid is not done.
6. If printing was requested: built with `--print-safe`, exit code 0, STL
   exported with `--stl`.

## Reference documents (load on demand)

- `references/design-language.md` — complete API: primitives, sketches,
  transforms, booleans, fillets, text, patterns, assembly helpers, common
  recipes and the errors you will hit.
- `references/parts-catalog.md` — every parametric part with signatures,
  pairing math and worked examples.
- `references/report-guide.md` — every report.json field and check id, what
  it means, how to fix it; query output interpretation.
- `references/detail-mode.md` — modeling real technical objects faithfully:
  the detail-level question, the Feature Specification method, and the
  feature -> toolbox mapping table. Load it whenever detailed mode applies.

Worked examples with real reports and renders: `examples/01-mounting-bracket`
(simple), `02-snap-box` (booleans + snap fit), `03-gear-train` (catalog),
`04-vase` (organic, --free), `05-assembly` (collision found -> fixed),
`06-hidden-cavity` (cavity invisible in renders, caught by report + queries),
`07-engine-block` (detail mode: inline-4 from a feature specification).

## Honesty Rules

- Never present a design as done without building the final version of the
  code and looking at its renders/report.
- Never invent or estimate metrics — quote them from report.json.
- Never silence a FAIL by switching to --free; free mode is for exploration,
  not for making errors disappear. Surface every warn/fail to the user with
  its suggestion, even when you disagree with it.
- Never hand-edit STL/PNG/report outputs; they must be reproducible from the
  model file (same input -> byte-identical output).
- If the tool errors, show the user the real error text — it contains the
  location and a suggestion by design.
