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
solidsight build model.py            # free mode (default): report all, enforce nothing
solidsight build model.py --print-safe   # enforce printability (thin wall, cavity, split shell -> exit 2)
solidsight build model.py --views iso,front,right,top,back,left,bottom,iso_back
solidsight build model.py --slice z=5 --slice x=0   # cross-section renders (repeatable)
solidsight build model.py --focus 70,43,24,25       # zoom every view onto a sphere (X,Y,Z,R)
solidsight build model.py --part lid                # build/validate one named part
solidsight build model.py --stl --exploded          # export STL; exploded view of an assembly
solidsight build model.py --out DIR --min-wall 0.8 --max-overhang 45 --allow-multiple-shells
solidsight build model.py --turntable 8 --json      # orbit frames; full report on stdout

solidsight query model.py point X Y Z            # INSIDE | OUTSIDE | ON_SURFACE + distance
solidsight query model.py ray OX OY OZ DX DY DZ  # every surface crossing along a ray
solidsight query model.py section z=4            # ASCII material grid at a cut plane
solidsight query model.py voxels [--layer 5]     # voxel grid + sealed-cavity detection
   (all query ops accept --part NAME and --json)

solidsight diff old_out/ new_out/     # what did my change actually change?
solidsight catalog [spur_gear]        # parametric parts: list all, or document one
solidsight explain thin-wall          # what a check id means + evidence + fix menu
solidsight profile side.png --length 4465   # MEASURE a silhouette -> exact mm envelope
solidsight watch model.py             # rebuild on every save (skips no-op edits)
solidsight view model.py              # live browser viewer, hot reload (Step 0.5)
```

Exit codes: 0 ok, 1 build error (bad model code), 2 print-safe validation
failed. Everything else the platform does — convert/3mf/obj/glb/dxf/svg,
components, fit, critique, cost, assembly, drawing, robot, motion, bench,
plugins, --progress/--events — is in `references/platform.md`.

## What You Must Do When Invoked

Follow these steps in order. Do not skip steps.

### Step 0 - Ensure solidsight is installed

```bash
solidsight version || pip install "git+https://github.com/VortexJer/AISight#subdirectory=solidsight"
```

If the user gave you a checkout of the repo instead: `pip install ./solidsight`.
The first run self-installs this skill into `~/.claude/skills/solidsight`
and keeps it updated; `solidsight uninstall` removes the skill and the
package together.

### Step 0.5 - Working for a human? Their screen comes up FIRST

Before the detail question, before any code, before the model file
exists: launch the live viewer in the background as the FIRST action
of the commission —

```bash
solidsight view model.py &        # opens their browser immediately
```

The page shows a loading spinner until the first successful build,
then hot-switches to the model and updates on every save. An edit
commission shows the existing model from second one. Not optional;
they should never have to ask. The viewer is theirs — you keep working
from renders and report.json.

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

**A SPECIFIC referent = ALWAYS ask the detail question.** The
detail-mode question below is not only for engines and gearboxes: if
the request names or implies a particular real thing you cannot
imagine on its own — "my car", "a Porsche 911", a specific phone, a
specific machine — you MUST ask it every time, whatever the object.
Only generic requests with sensible defaults ("a mug", "a phone
stand") skip the question. If they choose detailed and gave no specs,
first pin down the exact variant (which model / year / trim), then
research it and tag every spec `[researched]`/`[standard]`/`[assumed]`
— never silently substitute your invented average of the category.

**Detail mode is OPT-IN — always ask first, never assume.** If the
request is a real technical object (engine, gearbox, housing, pump...)
and the user did not already say how faithful it must be, ask ONE
question before modeling: *representative model, or detailed functional
model (every bolt pattern, port, gallery, rib — takes notably longer)?*
Enter detailed mode ONLY on an explicit yes (or words like "detailed",
"functional", "faithful", "replica"). Silence, an ambiguous answer or no
reply = **representative**; spending that time uninvited is a bug, not
diligence. On a yes, load `references/detail-mode.md` and follow it: it
carries the Feature Specification method, the research-and-tag rules and
the feature -> toolbox map.

**If the object is a STYLED BODY — a car, boat hull, fuselage, appliance
shell, helmet — load `references/car-bodies.md` BEFORE any geometry**,
and state the honest deal it opens with before you start: this tool has
no surface modelling, so the ceiling is a **well-proportioned massing,
not a class-A exterior**, and the report measures manufacturability, not
likeness. The user must hear that from you at the start, not discover it
after twenty builds.

**If the user supplied a photo or drawing**, load
`references/from-image.md` first and work from it: estimate real
dimensions with named anchors, trace with `image_outline()` /
`image_heightfield()`, and build with `--ref photo.png` for a
reference-vs-render sheet every build. For a straight-on side/front view,
`profile_read()` / `solidsight profile` MEASURES the silhouette into an
exact mm envelope instead of eyeballing it.

### Step 2 - Check the catalog before deriving geometry

Run `solidsight catalog`. Gears, threads, bolts, cap screws, washers, nuts,
bearings, shafts, timing pulleys, springs, NEMA motors, servos, T-slot
extrusions, lead screws, linear rails, hinges, snap clips, boxes with lids,
standoffs, honeycomb panels, and patterns already exist as tested parametric
parts. Composing catalog parts is always better than re-deriving an involute
or a helix from math. Full signatures and pairing rules: `references/parts-catalog.md`.

When the design uses a REAL purchased component, search the offline
database first: `solidsight components search "608 bearing"` returns the
standard's exact dimensions and the ready-made call
(`parts.component("bearing_608")`). Bought parts usually enter the scene as
ghost references: `place(parts.component("nema17", length=40), ghost=True)`.

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
- Attach SEMANTIC metadata to parts whose features matter downstream:
  `emit(p, name="plate", features=[{"type": "hole", "d": 5,
  "at": [10, 0, 6], "thru": True}])` — stored in report.json
  parts[].features, so consumers reason about meaning, not triangles.

**Iterating?** `solidsight watch model.py` rebuilds on every save (and
proves when an edit changed nothing), and `solidsight view model.py`
serves a live browser viewer — section planes, isolate, explode,
two-point measuring — that hot-reloads on each successful rebuild.

**Working for a human? ALWAYS give them the live preview — from the
very START.** Launch `solidsight view model.py` in the background
BEFORE the model file even exists: the browser opens immediately with
a loading spinner, switches to the model at the first successful
build, and updates on every save from then on. If a model already
exists (an edit commission), they see it from second one. This is not
optional and they should not have to ask. You keep working from
renders and report.json — the viewer is theirs.

**`view` never returns — that is not a crash.** It holds the terminal
until ctrl-c by design: do NOT restart it because "it hung", and do NOT
kill it to "check" — that steals the human's window. Read
`out/viewer/status.json` instead (`state`, `builds`, `last_error`).
`state: build-failed` means the server is fine and your code isn't; fix
the model and the page reloads itself. Closing the window stops the
server and frees the port, so never close theirs; `--keep-alive` if you
want it to outlive every window. `view` builds are **light** (geometry
only — a 138k-triangle model reloads in ~1.8 s instead of 42 s): it is a
window, not a report, so keep using `solidsight build` for checks.
Window, port and status details: `references/platform.md`.

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

Keep-out zones and insertion paths: place reference volumes with
`place(..., ghost=True)` (measured in pairs[]/expect(), X-ray rendered,
never printed) and test insertions with `parts.swept(rigid_body, dz=-30)`
— sweep the RIGID body only and stop just above seating; snap-fit hooks
interfere by design (judge overlap DEPTH, not contact). `--exploded`
renders mating faces, `--slice` through the joint shows engagement.
Worked loop: `examples/05-assembly/`.

BOM and fit chains (`solidsight assembly`), ISO 286 limits for printed-
to-machined mates (`solidsight fit 8 H7 g6`), and `joint()` -> URDF/SDF
+ swept collision maps (`solidsight robot` / `motion`): see
`references/platform.md`.

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

| load | for |
|---|---|
| `references/design-language.md` | the complete API: primitives, sketches, transforms, booleans, fillets, text, patterns, assembly helpers, recipes, the errors you will hit |
| `references/parts-catalog.md` | every parametric part: signatures, pairing math, worked examples |
| `references/report-guide.md` | every report.json field and check id — meaning, fix, query interpretation |
| `references/detail-mode.md` | modeling a real object faithfully: Feature Specification, research-and-tag, feature -> toolbox map. Whenever detailed mode applies |
| `references/car-bodies.md` | cars and styled shells: the honest deal to state up front, the one-piece rule, station templates, stance checklist. ANY vehicle/styled-body commission |
| `references/from-image.md` | a photo or drawing as input: anchors, `image_outline()`/`image_heightfield()`, the `--ref` loop |
| `references/platform.md` | everything past build/query: formats, components, drawing, robot, motion, assembly, fit, critique, cost, bench, plugins, viewer internals |

## Domain playbooks — load the ONE that matches (`domains/`)

Each is a full method for its domain: assumable numbers, build order,
recipes, failure modes, definition of done. Load the ONE that matches,
right after the bill of parts. Do not load the others.

| load | when the request is |
|---|---|
| `domains/enclosures.md` | a box, PCB housing, bracket, jig, wall mount, adapter |
| `domains/mechanisms.md` | gears, linkages, robot joints, anything that moves |
| `domains/product-design.md` | a handheld/consumer shell, grip, ergonomics |
| `domains/furniture.md` | tables, shelves, chairs, frames, joinery, T-slot |
| `domains/architecture.md` | buildings, rooms, plans, massing, interiors |
| `domains/vehicles.md` | cars, bikes, boats, hulls, aircraft, drones |
| `domains/organic.md` | vases, sculpture, characters, props, flowing forms |
| `domains/terrain.md` | landscapes, heightmaps, procedural environments |
| `domains/jewelry-miniatures.md` | rings, pendants, miniatures, scale models |
| `domains/game-ready.md` | assets for a game engine (GLB, budgets, LODs) |
| `domains/toys.md` | toys, puzzles, board-game inserts (safety standards) |
| `domains/scientific.md` | molecules, lab fixtures, data made physical |

A playbook says WHAT to build and what to check; it never overrides the
loop above or the honesty rules below.

Worked examples with real reports and renders (`examples/`):
`01-mounting-bracket` simple · `02-snap-box` booleans + snap fit ·
`03-gear-train` catalog · `04-vase` organic, --free · `05-assembly`
collision found -> fixed · `06-hidden-cavity` invisible in renders,
caught by report + queries · `07-engine-block` detail mode ·
`08-from-image` artwork traced with image_outline + --ref sheet.

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
- Never let a commission the tool cannot deliver start silently. For
  styled organic bodies (cars, hulls, characters, sculpted shells) say
  up front that the ceiling is a well-proportioned massing, not a
  class-A exterior — see the styled-body block in Step 1. A `0
  findings` report is never evidence that something *looks* right.
