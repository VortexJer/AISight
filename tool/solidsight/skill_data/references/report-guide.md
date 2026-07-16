# Reading report.json and query output

Every `solidsight build` writes `out/report.json`. It is deterministic (no
timestamps) and file references inside it are relative to the out dir.

## Top level

```jsonc
{
  "tool": "solidsight 0.1.0",
  "model": "model.py",
  "mode": "free" | "print-safe",
  "units": "mm",
  "status": "ok" | "warnings" | "failed",   // failed = at least one FAIL check
  "scene":  { "part_count", "bbox", "size", "total_volume_mm3" },
  "parts":  { "<name>": { ...per-part metrics... } },
  "pairs":  [ ...pairwise collision/clearance... ],
  "checks": [ ...findings, most important output of the tool... ],
  "files":  { "report", "renders": [...], "exports": [...] }
}
```

First things to read, in order: `status` -> `checks` -> `scene.size` (does it
match the spec?) -> per-part numbers.

## Per-part metrics

| field | meaning | act when |
|-------|---------|----------|
| `volume_mm3` | exact solid volume | ~0 for a part that should be chunky = a boolean went wrong |
| `surface_area_mm2` | exact area | — |
| `bbox.min/max/size` | axis-aligned bounds | compare `size` against the spec dimensions number by number |
| `center_of_mass` | exact COM | stability checks (should be over the footprint for standing parts) |
| `shells` | disconnected SOLID pieces | must be 1 per part; >1 means pieces did not fuse (see `multiple-shells`) |
| `watertight` | closed surface | always true from solidsight primitives |
| `genus` | number of through-holes (topological) | a handle you expected = 1; 0 means the hole did not go through |
| `wall_thickness.min_mm` + `.at` | thinnest PLATE-LIKE wall measured by inward rays. Knife wedges that thin to zero by construction (thread chamfer feathers, blade edges) are excluded — they are geometry, not defects; when only such tapers exist, `min_mm` is `null` with a `note` | below printer limits -> thicken at the given coordinates. `null` = no plate-like wall found (chunky convex part, or taper-only geometry — read the note) |
| `overhangs.max_deg`, `.area_mm2`, `.worst_at` | downward faces steeper than the threshold (90 = horizontal ceiling) | reorient, chamfer at 45 deg, or accept supports |
| `internal_voids` | sealed cavities (count, bbox, ~volume) | almost always a bug; add a drain hole or remove |
| `print_estimate` | grams (PLA/PETG at 100% infill) + rough minutes (+-50%) | sanity-check material cost; real values are slicer-dependent |
| `stability` | `standing` + `com_margin_mm`: does the COM project inside the base footprint, and by how much | negative margin = tips over; small margin = nudge-sensitive. `null` for stacked/floating parts |

## Check ids

| id | level | meaning | fix |
|----|-------|---------|-----|
| `thin-wall` | fail (print-safe) / warn | wall below --min-wall (or sub-0.4 sliver in free) | thicken at `where`; slivers usually mean a cutter grazed a face — --slice through the coordinates |
| `multiple-shells` | fail (print-safe) / warn | part is N disconnected pieces (piece bboxes listed) | overlap the pieces >= 0.1 mm; or emit separately; or --allow-multiple-shells |
| `internal-cavity` | fail (print-safe) / warn | sealed void no opening reaches; renders look solid | drain hole, or remove the void; verify with `query voxels` |
| `overhang` | warn | area steeper than --max-overhang | reorient / chamfer / accept supports |
| `parts-overlap` | fail (print-safe) / warn | two named parts intersect (exact bbox + mm3) | apply the move suggestion; separate parts must never intersect |
| `below-plate` / `floating` | warn (print-safe) | part under/over Z=0 | `.on_ground()` or intentional stacking |
| `not-watertight` | fail | open surface (should never happen) | rebuild step by step, report the breaking op |
| `union-touching` | warn | union pieces share faces but no volume | overlap >= 0.1 mm |
| `noop-difference` | warn | a subtraction removed nothing | cutter is misplaced; its bbox is in `where` |
| `expectation-violated` | fail (any mode) | an expect() declaration does not hold (wrong status, clearance out of band, or collision) | fix the geometry to meet the declared spec, or update the expect() if the intent changed |
| `expectation-unknown-part` | fail | expect() names a part that was never emitted/placed | match the names |
| `unstable` / `barely-stable` | warn | COM outside / marginally inside the base footprint | widen the base, add feet, lower the mass |

`status` mapping: any fail -> `failed` (exit 2 under --print-safe); any warn
-> `warnings`; else `ok`.

## pairs[] (assemblies)

```jsonc
{ "a": "lid", "b": "card",
  "status": "collision" | "touching" | "clear",
  "overlap_volume_mm3": 160.0,          // 0 when not colliding
  "overlap_bbox": { "min": [...], "max": [...] },  // null when clear
  "min_clearance_mm": 0.2,              // null when colliding
  "suggestion": "move 'card' 1.7 mm along y ..." }
```

- `collision` -> always fix (the suggestion picks the thinnest overlap axis).
- `touching` (< 0.05 mm) -> right only for faces meant to press together.
- `clear` -> check the number is an INTENDED clearance: 0.15-0.3 mm for
  fits that slide or snap; more for free space.

When the model declared `expect()` for a pair, the entry also carries
`"expected"` (the declared spec) and `"expectation": "met" | "violated"`;
violations surface as FAIL checks in any mode. Declare every fit that
matters — it removes the judgment call from the loop.

## Query output

- `point X Y Z` -> `INSIDE | OUTSIDE | ON_SURFACE` + exact distance to the
  surface. ON_SURFACE tolerance is --tol (default 0.001 mm).
- `ray OX OY OZ DX DY DZ` -> ordered crossings with `entering` flags and
  `material_segments` (from, to, thickness per wall the ray pierces).
  TWO material segments where you designed ONE wall = internal cavity,
  second shell, or re-entrant shape on that line. One segment whose
  thickness is the whole part = a hole that did not go through.
- `section AXIS=V` -> ASCII grid, `#` material / `.` empty, top row = max of
  the row axis. `cell_mm` converts band widths to mm (count the `#`s).
- `voxels [--res MM]` -> filled counts + SEALED CAVITY findings with bbox.
  `--layer N` prints one Z slice; `--layer all` the whole stack. Cavities
  smaller than ~2 voxels can hide — lower --res to hunt small ones.

Known limitation: shallow ribs BETWEEN engraved strokes (e.g. the material
between two letter grooves) are flagged by `thin-wall` even though they sit
on bulk material and usually print fine. Keep engraving strokes and gaps at
or above your minimum wall (size >= 7 mm text for the default 1.2 mm), or
consciously accept the finding.

## When to trust what

- Exact numbers (volume, bbox, clearance, overlap): kernel-exact — trust.
- Wall thickness: sampled (600 inward rays on face centers) — trustworthy
  for finding the thin spot, but confirm an exact wall with `ray` across it.
- Voxel cavity volume/bbox: resolution-limited approximation; existence is
  confirmed exactly (surface component analysis), size is approximate.
