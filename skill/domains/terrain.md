# Terrain and procedural environments

Load for: landscapes, maps, heightmaps, game terrain, topographic
models, rock/cliff formations, procedural scatter.

Two entirely different starting points — a real heightmap image, or a
deterministic function. Both end as measured geometry.

## From an image (real data, DEMs, hand-painted maps)

```python
terrain = image_heightfield("dem.png", width=200, relief=40, base=2)
emit(terrain, name="terrain", color="sage")
```
Brightness -> height, on a solid base slab. See `from-image.md` for the
full contract. Key parameters:
- `width` = the real-world footprint you are representing (mm at model
  scale), `relief` = the vertical range, `base` = the slab under it
  (>= 1.5 mm if printed, it is what holds the model together).
- **Vertical exaggeration is the whole craft.** Real terrain at true
  scale looks flat: a 400 m range across 20 km is 2 % slope. Models use
  1.5x-3x exaggeration. Pick one, and TELL the user: "relief exaggerated
  2x for legibility" — silently exaggerating is lying about a map.
- `max_cells` caps resolution (240 default). Iterate at 120, finish at
  240-400. Cost is quadratic: 400 -> ~320k triangles.

## From a function (procedural, infinite variation, zero data)

```python
import math

SEED = 7                              # written down, not random

def ridged(x, y):
    """Sum of octaves; deterministic, pure, reproducible."""
    h = 0.0
    for o in range(4):
        f = 0.011 * (2 ** o)
        a = 14.0 / (2 ** o)
        h += a * abs(math.sin(x * f + SEED) * math.cos(y * f * 0.87 + SEED))
    return h

def displace(p):
    x, y, z = p
    return (x, y, z + ridged(x, y) if z > 0.1 else z)   # top surface only

slab = box(200, 200, 4).refine(2.5).warp(displace)
```
The three rules:
1. **`refine()` before `warp()`.** A 12-triangle box warps into a
   12-triangle joke. `refine(2.5)` on a 200 mm slab -> a workable grid;
   `refine(1.0)` -> ~160k triangles, slow but detailed. Iterate coarse.
2. **Displace the TOP only** (`if z > threshold`), or the base warps too
   and the model will not sit flat.
3. **Pure functions, fixed seed, no `random`.** Determinism is what makes
   the terrain reproducible and `diff`-able. A `SEED` constant gives you
   variation without giving up reproducibility.

## Contours, scatter and features

**Contour lines** (a real topographic deliverable) — intersect with
slabs:
```python
for z in range(5, 40, 5):
    ring = terrain & box(200, 200, 0.6).translate(0, 0, z)
    emit(ring, name=f"contour_{z}", color="dark")
```
Or just read them: `solidsight build model.py --slice z=20` renders the
20 mm contour as a filled section.

**Scatter** (rocks, trees) must also be deterministic — index the
placement, do not roll dice:
```python
for i in range(24):
    a = 2.399963 * i                    # golden angle: even, deterministic
    r = 8.0 * math.sqrt(i)
    x, y = r * math.cos(a), r * math.sin(a)
    scene_solid = scene_solid + rock.translate(x, y, ridged(x, y))
```
Note the trees sit ON the terrain because their z comes from the SAME
height function. Scattering at z=0 and hoping is how you get floating
forests.

**Rivers/roads**: `stroke(points, width)` gives a 2D ribbon; extrude it
as a cutter and subtract to carve, or add to raise.

## Measure it

| question | how |
|---|---|
| how tall is the highest point? | report `bbox` z max |
| is the base flat and printable? | `--slice z=1`, and `stability` |
| any sealed pockets? | `internal_voids` — warps love making them |
| is it one shell? | `shells` == 1 |
| what does the slope look like? | `overhangs`: > 50 deg = unprintable cliff |
| exact height at a point? | `query ray X Y 100 0 0 -1` -> first hit |

Terrain is `--free` normally. For printing: `--print-safe`, and expect
overhang findings on cliffs — a vertical cliff IS an overhang. Either
accept supports (say so) or soften the function.

## The five ways terrain fails

1. **Warped a coarse mesh** — polygonal "landscape". `refine()` first.
2. **The base warped too** — model rocks on the table. Displace top only.
3. **Non-deterministic noise** — different every build, unreproducible.
4. **Silent exaggeration** — the map lies. State the factor.
5. **Everything floats** — scatter placed at z=0 instead of on the
   surface. Use the height function for placement too.

## Done means

- `--views iso,top` + `--turntable 8` looked at; terrain reads wrong from
  exactly one angle otherwise.
- Exaggeration factor and footprint scale stated to the user.
- shells == 1, no internal voids, base flat.
- Every noise function pure, seed written in the file.
- If printed: `--print-safe`, base >= 1.5 mm, overhangs accepted
  explicitly or designed out.
