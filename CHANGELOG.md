# Changelog

## 2026-07-19 — the engine blind baseline, regenerated under a fully traced protocol

The same-prompt comparison's blind side was regenerated once more at
the owner's request, this time with the complete tool trace in the
methodology note: fresh-context agent, empty directory outside the
repo, numpy+trimesh only, four tool calls total, zero crash reruns.
The new audit found a different (and better) defect story: eight
sealed water-jacket pockets (two of ~37 cm³ — coolant can never reach
them), main-cap bolt drillings 1.881 mm from the crank tunnel, the
pressurized oil gallery 3.0 mm from the jacket for the block's full
length, and a 2 mm sliver below the cap face that the blind author
itself PREDICTED sight unseen — it could reason about its likely
failures, it just had no way to check them. docs/comparison and the
root README updated with verbatim query evidence.

## 2026-07-19 — every Sight can EDIT, and every Sight can SHOW

Two family-wide capabilities (animationsight 0.7.0, texturesight 0.5.0,
shadersight 0.6.0, pcbsight 0.5.0):

- **Edit, not just review** — solidsight could always take an existing
  artifact (`from_stl`) and modify it; now the whole family can:
  - animationsight: `save_bvh` — parse a clip someone hands you, modify
    joints/frames, write it back, re-inspect. Round-trip tested.
  - texturesight: `save_obj` — the Mesh arrays are the model; modify
    verts/UVs, write back (winding sign preserved — a writer that
    unflipped faces would hide the defect). Round-trip tested.
  - shadersight: `material --from-json FILE[:NAME]` — load an existing
    material (flat dict or a materials set), override with flags,
    re-verify. Windows drive letters survive the `:NAME` syntax (found
    by the test). The summary now prints the material's name.
  - pcbsight: s-expression writer (`load_sexpr`/`save_sexpr`/`dumps`) —
    edit the board tree, write it back (strings come back quoted; the
    tree round-trips exactly, tested against the example board).
- **A preview for the human** — the agent's interface is report.json;
  the person the agent works for now gets `--show` on inspect (and a
  `preview` subcommand): builds `out/index.html` with the verdict,
  every finding and every render (GIFs first), and opens it in the
  browser. The skills teach both: edit-without-re-inspect is a claim,
  and the preview is never for the agent itself.

## 2026-07-19 — texturesight 0.4.0: two renders that explain UVs to anyone

A UV layout is unreadable to anyone who has never unwrapped a mesh
(user feedback: "no entiendo qué son esos cuadrados"). Every mesh
inspect now also writes, via a new deterministic z-buffer rasterizer:

- **correspondence.png** — the 3D mesh with each island tinted its own
  colour, beside the UV square in the SAME colours: the flat shapes ARE
  the 3D faces peeled onto the texture.
- **checker_preview.png** — the mesh (front AND back view; one
  viewpoint hides half the surface) wearing a checker sampled through
  its own UVs, an asymmetric L mark in every cell: a MIRRORED L =
  flipped face, squashed cells = stretch, cell size = texel density.

All example outputs regenerated; 35 tests (3 new: existence,
byte-determinism, and that the checker actually reacts to defects).

## 2026-07-19 — the parkour blind baseline, regenerated with proven provenance

The animationsight hero study's blind side was challenged: could its
quality be contamination (an author who had seen the tool)? The pilot
baseline could not prove otherwise, so it was discarded and regenerated
end-to-end by a fresh cold-context agent in an empty directory —
stdlib+numpy only, forbidden from invoking any tool. The new audit is
its own provenance proof: it ships a 0.47x-g stride, a root-on-rails
turn step and a landing knee pop (findings a hidden tool user would
have removed), while its hand-solved vault measures 1.03x g. The after
side re-fixed each measured finding in 3 iterations (including one
honest wrong guess, settled by a numeric probe) to `OK — 0 findings`.

- **animationsight 0.6.1**: `diff` said `-> Nonex gravity` when a
  flight exists on only one side — which is what a good fix produces
  (a phantom flight disappearing). Now `no flight`, regression-tested.
- Example 03-parkour: new blind/after clips, audits, GIFs and README
  (with a Provenance section); hero sections and study table updated.

## 2026-07-17 — repo renamed to AISight; family v0.2.0 (dogfooding round)

The repo is now **AISight**: five independent tools, install only what
you need. Each Sight was then USED on a realistic commission by a fresh
agent, and every point of friction fixed at the root — the same process
that hardened solidsight in its Phase 2.

- **all four Sights**: a `diff` command (the proof step of the loop —
  solidsight had it, the others did not; "a fix without a diff is a
  claim").
- **animationsight 0.2.0** (commission: review a jump):
  - ballistics: parabola fit per airborne span -> effective gravity.
    The dogfood jump measured 0.683x g — authored floaty without
    noticing, invisible to any still frame. Also a free unit sanity
    check (~0.1x/~10x = wrong --unit, one metric prefix).
  - pop clustering: a blocking-pass jump reported "154 pops" that were
    really 8 pose snaps; spikes now cluster by frame into "pose snap"
    (many joints) vs "joint pop" (one bad key), with the MAD floored at
    the clip's own scale so static joints cannot inflate z-scores.
  - `--kind oneshot|loop|auto`: a jump is not supposed to loop; declare
    the intent instead of ignoring a warning.
  - report.json slimmed: the COM trajectory moved to com_trajectory.csv.
- **texturesight 0.2.0** (commission: fix a crate's starved lid island):
  - `islands.detail[]`: per island id, uv bbox, face count, mean
    density — the actionable unit. The density finding now names the
    island and the scale factor ("scale island #4 up ~2.7x"), and
    islands are labelled #N in uv_layout.png. "Lowest at face 8" told
    nobody what to grab in the UV editor.
- **shadersight 0.2.0** (commission: author a physical gold):
  - `--preset gold|silver|copper|...|skin|snow`: measured F0/base
    values. The dogfood gold authored "from memory" was visibly too
    pale next to the measured (1.000, 0.766, 0.336).
- **pcbsight 0.2.0**: `pcbsight diff before.kicad_pcb after.kicad_pcb`
  tells the whole story of a repair (islands per net, clearance count,
  current at the narrowest width, pair skew, findings NEW/GONE).

Skills updated for all four (the loop now ends in diff; new features
documented). 13 new tests (174 in the repo).


## v0.7.0 — 2026-07-17 "the Sight family"

**The four sibling tools** — the solidsight philosophy applied to four
more domains built for human eyes. Each is its own pip package with its
own CLI, self-installing Claude Code skill, synthetic known-ground-truth
examples (defects injected at exact magnitudes; tests assert the right
answer AND that the clean reference stays clean), and honest scope
statements. All deterministic.

- **animationsight**: BVH + own FK -> per-joint velocity/accel/jerk,
  geodesic angular rates, contact events, foot sliding, balance vs
  support (Dempster segment masses), floor penetration, pops (robust
  z-score), convention-aware loop seams; evidence frame renders + time
  tracks; `diff` between takes. Found in itself: the sinusoid walk that
  never planted a foot; the floor estimate a penetration could hide
  under.
- **texturesight**: texel density (area-weighted), UV-Jacobian
  stretch/flip, islands + seams counted from topology, packing/overlap,
  tiling judged against the texture's own statistics, normal-map
  validity + green convention, data-map range/quantisation, codec
  blocking (both axes). Found in itself: a transposed Jacobian calling
  conformal UVs 2.6:1 stretched; two more false-positive classes.
- **shadersight**: energy conservation by multiple importance sampling
  swept over view angles, Helmholtz reciprocity, positivity, the known
  single-scatter loss labelled as such; node-graph cycles/dead
  nodes/dangling refs/ALU cost over live nodes. Found in itself: the
  uniform-grid integrator that read a mirror as 0.02 or 1.19; the naive
  diffuse coupling measuring ITSELF at 1.478x the ceiling (now
  Ashikhmin-Shirley coupled).
- **pcbsight**: .kicad_pcb reader (footprint rotation composed), net
  connectivity by union-find over touching copper, exact clearances
  with coordinates, IPC-2221 current at the narrowest track, diff-pair
  skew/width, IPC-2141 microstrip estimate; board render with findings
  circled. Found in itself: the "clean" board routed through two pads;
  pairs double-reported per suffix rule.

**solidsight core**
- Images as input: `image_outline()` (marching-squares trace + RDP,
  holes preserved, real size required), `image_heightfield()`
  (lithophanes/terrain), `build --ref photo.png` -> reference-vs-render
  comparison sheet. Example 08. Renderer fix found by it: sliver
  triangles from complex booleans faked crease/silhouette edges
  (phantom stripes) — edges are now gated on triangle soundness.
- 12 deep domain playbooks (`skill/domains/`) replace the 44-line
  domains table: real numbers (insert holes, centre distances, NACA,
  stair rules, ring sizes, 16 CFR 1501, triangle budgets), build
  orders, failure modes, per-domain definitions of done. Loaded one at
  a time. Installer wipes stale subdirs; drift guard covers them.
- `joint(..., name=)`: real robotics names in URDF/SDF and
  `motion --joint`; duplicates rejected.
- `_say()` flushes: `watch`/`view` logs no longer sit empty in the
  redirected-output case agents actually use.
- BOM rows are name + size + catalog provenance instead of a 300-char
  construction tree (tree kept in JSON as `desc`).

17 new regression tests in the core (70 total); 91 across the family
(161 in the repo). CI runs all five packages on 3 OS x py3.10/13.


## v0.6.0 — 2026-07-16 "the platform release"

**Live development**
- `solidsight watch`: rebuild on save with PROVABLE skips (exact scene
  fingerprints: cosmetic edits touch nothing, unchanged parts reuse
  exports).
- `solidsight view`: self-contained browser viewer (vendored three.js,
  no CDN) — isolate, x-ray, wireframe, normals, section planes, explode
  slider, bboxes, COM, finding markers with fly-to, two-point measuring,
  hover HUD; hot-reloads after every successful rebuild.
- Progress streaming everywhere: `--progress` (live stage lines with %
  and ETA) and `--events file.ndjson` (structured machine stream).
  Telemetry only — artifacts stay byte-deterministic (tested).

**Formats**
- `--obj`, `--glb` (combined GLB keeps part names + colors), `--dxf`/
  `--svg` slice outlines, `solidsight convert`, `from_mesh()`.

**Components & catalog**
- 13 new parts: cap_screw, washer, bearing, shaft, timing_pulley,
  spring, nema_motor, micro_servo, extrusion_profile (2020/2040),
  lead_screw, linear_rail, linear_carriage, cable_chain_link.
- Offline component database (~70 real parts, ISO exact dims):
  `solidsight components search/show`, `parts.component(id, ...)`.

**Engineering outputs**
- `solidsight drawing`: third-angle dimensioned PDF with true hidden
  lines and a hole table from detected circular rims. Deterministic.
- `solidsight robot`: joint() declarations -> URDF/SDF with exact
  masses/inertia (verified analytically) + collision meshes.
- `solidsight motion`: sweep joints through limits -> exact collision
  map per sampled position.

**Reasoning & review**
- `query distance A B`, `solidsight fit 8 H7 g6` (real ISO 286 values),
  `solidsight explain <check-id>`, `solidsight critique` (findings with
  fix menus + verified-good list), `solidsight cost` (fdm/petg/sla/cnc),
  `solidsight assembly` (BOM + axis play + assembly sequence; BOM also
  in every report.json).
- Semantic features: emit(..., features=[{type, ...}]) recorded in
  report.json parts[].features.

**Platform**
- Plugin system (entry-point group `solidsight.plugins`): exporters,
  validators, parts packs; crashes isolate to warnings. Example package
  in docs/plugins/example.
- Benchmark suite (benchmarks/): six graded commissions with
  machine-checkable expectations; `solidsight bench run [--solution]`.
  Honest note: three of the first reference solutions failed their own
  audits and were fixed guided by the findings.
- Parallel view rendering (byte-identical, verified); `--skip-pairs`.
- Comparison baseline regenerated by a cold-context agent after the
  pilot was found contaminated (methodology note in docs/comparison).

24 new regression tests (53 total).


## v0.5.0 — 2026-07-16

Rim breaks, ghost volumes, visual diffs.

- `Solid.chamfer_rim(c)` / `Solid.round_rim(r)` — break ALL edges on a
  top/bottom rim (any outline, holes included: a container mouth gets both
  wall edges at once). Exact construction (slice + Minkowski roof), no BREP
  needed. The most-requested "CSG can't do that" finally scoped and solved
  for prismatic rims.
- Ghost parts (`place(..., ghost=True)`): keep-out zones, connector
  envelopes, swept insertion paths — fully measured in `pairs[]`/`expect()`,
  rendered as X-ray outlines, excluded from print checks, exports and
  material totals.
- `parts.swept(solid, dx=, dy=, dz=)` — insertion-path volumes. Docs teach
  the snap-fit semantics: sweep the RIGID body only and stop just above
  seating; flexible hooks interfere by design — judge their overlap DEPTH
  against allowed deflection.
- `solidsight diff` now also compares renders: % of pixels changed per
  matching view.
- 4 new regression tests (29 total).

## v0.4.0 — 2026-07-16

Spec-driven assemblies, freeform shapes, manufacturing sanity.

- `expect(a, b, clearance=|status=)` — declare the INTENDED relationship
  between parts (touching / clear / clearance band, e.g. gear backlash
  0.15..0.35). The report becomes a pass/fail spec test: violations FAIL in
  any mode; met expectations silence generic advice. `pairs[]` gains
  `expected` / `expectation` fields.
- Every thin-wall / overhang / overlap finding now ends with a ready-to-run
  close-up command (`--focus` + `--slice` at the exact coordinates).
- Freeform: `Solid.warp(fn)` + `Solid.refine(edge_mm)` (deterministic
  vertex deformation), `parts.loft(profiles, heights)` (convex sections:
  funnels, ducts, adapters), `parts.wrapped_text(...)` (engrave/emboss text
  around cylinders).
- Report: `print_estimate` (PLA/PETG grams, rough minutes) and `stability`
  (COM vs base-footprint margin) per part, with `unstable`/`barely-stable`
  warnings for parts that would tip over.
- Model files can now import sibling modules — share assembly dimensions in
  a `params.py` instead of duplicating constants that drift.
- `--3mf` export alongside `--stl`.
- 7 new regression tests (25 total).

## v0.3.0 — 2026-07-16

Close the last inspection gaps.

- Detail mode now RESEARCHES: when the user picks detailed mode without
  giving specifications, the skill instructs the agent to research the
  object on the web first (anatomy, dimensions, feature counts, standards)
  and tag every spec line `[researched]` / `[standard]` / `[assumed]` —
  assumptions are never presented as research.
- `--focus X,Y,Z,R`: zoom every view onto a sphere around one feature —
  inspect a single hole/boss/clip up close on a large part (pick a view
  facing the feature).
- `solidsight diff old_out new_out`: exact change accounting between two
  builds — per-part volume/size/min-wall/shell/cavity deltas plus checks
  that appeared or disappeared. Confirms an edit did what was meant and
  nothing else.

## v0.2.1 — 2026-07-16

Self-hosting skill.

- The Claude Code skill (SKILL.md + references) now ships inside the pip
  package. On any CLI run on a machine with Claude Code (`~/.claude`
  exists), the skill installs itself into `~/.claude/skills/solidsight`
  and silently refreshes on version changes.
- `solidsight install-skill [--dir]` for explicit/custom installs;
  `solidsight uninstall` removes the skill AND the package in one command.
- CI-enforced drift guard: `/skill` and the packaged copy must be identical.

## v0.2.0 — 2026-07-16

Detail mode: faithful functional models of real technical objects.

- Skill: when the request is a technical object and the fidelity was not
  stated, the agent asks ONE question (representative vs detailed
  functional). Detailed mode follows `references/detail-mode.md`: a
  per-region Feature Specification before code, named datums, region-by-
  region build + verify, and a feature -> toolbox mapping table.
- `parts.hole()` — the workhorse of mechanical detail: plain, counterbored,
  countersunk, chamfered, drill-point blind holes as one cutter.
- `Solid.aim(direction)` — orient any downward-built tool to drill/pocket
  into any axis-aligned face (kills the double-rotate dance).
- `parts.bolt_circle()` — hole patterns on a circle.
- Composed operation descriptions are now capped, keeping warning/error
  texts readable on deeply built models.
- New worked proof: `examples/07-engine-block`, a detailed inline-4 block
  (deep skirt, pan rail + gussets, bores + liner steps, head-bolt matrix,
  siamese water jacket, cam tunnel, oil galleries, coolant ports, filter
  pad, inclined engine mounts) built with the method. While building it,
  the validator caught two sealed cavities (buried mount drillings) and a
  0.75 mm jacket-to-bore wall — the loop works at this density.

## v0.1.0 — 2026-07-16

First public release.

### Engine (`tool/`, pip package `solidsight`)
- Design language over the manifold3d kernel: parametric primitives,
  2D sketches (`stroke`, `round_corners`, offsets, text), booleans,
  transforms, Minkowski-based fillets, named parts via `emit()`.
- Deterministic software renderer (no GPU): multi-view PNGs with part
  legend, crease-aware Gouraud shading, silhouette/sharp-edge overlay,
  10 mm grid, axis triad, dimensions and scale bar; cross-section
  (`--slice`), turntable and exploded views. Byte-identical output for
  identical input.
- Validation report (`report.json`): volume, surface area, bbox, center of
  mass, shells, genus, watertightness, plate-aware minimum wall thickness
  (taper/fold-proof), overhang analysis, sealed internal cavity detection;
  `--print-safe` / `--free` modes, actionable checks with locations.
- Exact spatial query API (`solidsight query`): point classification,
  raycast with per-wall material segments, ASCII cross-section grids,
  voxelization with flood-fill cavity search.
- Assemblies: `place()`, `from_model()`, `from_stl()`; pairwise
  collision analysis (overlap bbox + volume + patch decomposition +
  move/shrink suggestions) and minimum clearances (`pairs[]`), exploded
  renders.
- Parametric catalog: involute spur gears, ISO threads/bolts/nuts,
  print-in-place hinge, snap clip + slot, box with lid, uniform-wall
  container, standoff, hex vent cutter + honeycomb panel, linear/grid/
  circular patterns, 3D tube sweeps, text.
- Errors written for LLM agents: what failed, where (file:line,
  coordinates, bboxes), what to try.

### Skill (`skill/`)
- `SKILL.md` workflow for coding agents + reference docs
  (design language, parts catalog, report guide).
- Six worked examples with committed real renders, reports and STLs,
  including an assembly collision->fixed pair and a hidden-cavity trap.

### Hardened by blind dogfooding (16 findings)
- Fixed: silent Gouraud fallback averaging normals across creases;
  union-touching false positive on interleaved cutters; polygon
  self-intersection silently splitting regions; stroke winding; thread
  twist-fold fins; wall-thickness false zeros on folds and taper wedges;
  misleading collision advice for oversized parts.
- Added: `hex_grid`, `stroke`, `tube_path`; bridge-aware overhang wording;
  patch-decomposed collision reports; regression test suite (14 tests).
