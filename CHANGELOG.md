# Changelog

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
