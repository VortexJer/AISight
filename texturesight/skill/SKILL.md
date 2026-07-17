---
name: texturesight
description: "Use whenever the user asks to review, debug or validate UVs and texture maps — texel density, stretch, seams, UV islands, packing, tiling, normal maps, roughness/AO data maps. You cannot squint at a checker texture; this tool turns the layout and the pixels into exact numbers plus evidence renders."
---

# /texturesight

UV and texture work is judged by putting a checker on the model and
looking, or by tiling a plane and squinting. You cannot do either. But
every one of those judgments is an exact property of the data: texel
density is UV area vs 3D area, stretch is the singular values of the UV
Jacobian, a seam is an edge whose faces land in different islands, and a
normal map is either unit-length vectors or it is broken.

The loop is: inspect -> read the checks -> LOOK at `uv_layout.png` and
`uv_density.png` -> fix in the DCC tool -> inspect again into a NEW out
dir -> `diff` the two to prove the fix did what you meant and nothing
else.

## Usage

```
texturesight inspect --mesh model.obj                     # UV audit
texturesight inspect --texture albedo.png                 # one map
texturesight inspect --mesh m.obj --texture t.png --texture n_normal.png
texturesight inspect --mesh m.obj --texture-px 2048       # density target (default 1024)
texturesight inspect --texture rough.png --kind roughness # declare the map type
texturesight inspect --mesh m.obj --out DIR --json
texturesight diff out_before out_after           # what the fix changed (proof)
texturesight version
```

Exit codes: 0 ok, 1 bad input, 2 a FAIL-level finding (flipped UVs, a
broken normal map).

## What You Must Do When Invoked

### Step 0 - Install

```bash
texturesight version || pip install "git+https://github.com/VortexJer/AISight#subdirectory=texturesight"
```

### Step 1 - The mesh must be unwrapped, and the map type must be right

`--mesh` needs an OBJ with `vt` coordinates. A mesh with no UVs is
rejected rather than audited — there is nothing to audit.

Map kinds are GUESSED from the filename (`*_normal.png` -> normal,
`*_rough*` -> roughness...) and `kind_source` says `filename` when they
were. A guess is fine for a report and wrong for a decision: if the
naming is not conventional, pass `--kind`. Auditing an albedo map as a
normal map produces confident nonsense.

### Step 2 - Texel density needs a texture size

`--texture-px` (default 1024) is what density is computed against.
Quote it whenever you quote a density: "327 px/unit at 1024" is a fact;
"327 px/unit" alone is not.

### Step 3 - Read the checks

| id | level | means |
|---|---|---|
| `uv-flipped-faces` | FAIL | UV winding opposite the mesh majority. Normal maps sample mirrored: lighting is wrong in a way no texture edit fixes. |
| `normal-not-unit-length` | FAIL | the vectors are not unit length — the map was resized/compressed/gamma'd as if it were a picture. |
| `normal-bad-z` | FAIL | blue channel wrong: an object-space map, or a height map mislabelled. |
| `uv-stretch` | warn | faces stretched >2:1. Stretch cannot be painted out. |
| `texel-density-uneven` | warn | parts of the model get fewer texels: they read as blurry next to the rest. |
| `uv-overlap` | warn | islands share texels. Deliberate for mirrored parts, a bug otherwise. |
| `uv-out-of-bounds` | warn | UVs outside 0..1. Deliberate for tiling/UDIM, a bug for an atlased asset. |
| `uv-packing-loose` | warn | <50 % of the square used: you are paying memory for empty pixels. |
| `tiling-seam` | warn | the wrap jump is much bigger than the texture's own pixel-to-pixel variation. |
| `map-quantised` / `map-range-wasted` / `map-is-constant` | warn | a data map that lost its information somewhere. |
| `compression-blocking` | warn | the image remembers a lossy codec's 8x8 grid, on both axes. |
| `data-map-not-grayscale` | warn | a roughness/AO map whose channels differ. |

### Step 4 - LOOK at the renders

- `uv_layout.png` — the islands, one colour each and **labelled #N**
  (the same ids as `islands.detail[]` in the report); **red = flipped
  winding, orange = stretched >2:1**. Findings are painted onto the
  layout, so the defect and its location are the same picture.
- `islands.detail[]` in report.json is the actionable unit: per island
  its id, uv bbox, face count and mean texel density. Density findings
  name the starved island and the scale factor it needs — quote those,
  not face numbers.
- `uv_density.png` — texel density painted per face: dark = starved,
  light = oversampled. Uneven density is invisible on a model and
  obvious here.

### Step 5 - Interpret honestly

- **Several findings are only defects in context.** Out-of-bounds UVs
  are correct for tiling and for UDIMs. Overlap is correct for mirrored
  geometry sharing texture. Repetition is correct for a brick pattern.
  Say which applies instead of reporting them as errors.
- **Repetition is reported, not warned about** (except a tight repeat
  inside one tile): a tiling texture is periodic by definition, so
  warning on it would fire on every correctly authored material. Read
  `repetition.peak_correlation` and `peak_offset_px` against the intent.
- **The green-channel convention is a GUESS** from the map's own
  statistics — no format records it. `green_convention.likely` says
  OpenGL or DirectX; confirm against what the engine expects rather than
  reporting it as fact.
- **Seam count is exact**, seam *quality* is not measured: this tool
  says where the seams are, not whether they are hidden well.

## Honesty Rules

- Never say UVs "look fine". Quote the density, the spread, the max
  anisotropy, the island count.
- Always state the texture size that density was computed against.
- If the map kind was guessed from a filename, say so.
- A UV audit is not done until you have LOOKED at `uv_layout.png`.
- Say plainly what is out of scope rather than implying it was checked.

## Scope

Reads: OBJ (with UVs), PNG/JPG/etc texture maps.
Measures: texel density, per-face stretch/flip via the UV Jacobian,
islands/seams/shells, packing and overlap, tiling, repetition,
normal-map validity, data-map statistics, codec blocking.

Does NOT do: unwrapping, packing, baking, painting, or fixing anything.
It audits; you fix it in Blender/Substance/whatever made it. It also
does not judge whether a texture is beautiful, only whether it is
correct.

Sibling tools, same philosophy: `solidsight` (3D geometry, parts,
assemblies), `animationsight` (motion clips).
