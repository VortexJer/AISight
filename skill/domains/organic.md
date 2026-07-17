# Organic, stylized and artistic forms

Load for: vases, sculptures, characters and creatures, props, plants,
flowing/twisted forms, anything whose judge is the eye rather than a
caliper.

This is the domain where solidsight's rules bend the most — and exactly
two do not: **the geometry is still measured**, and **the model is still
deterministic**. "Organic" never means "unverified".

## The four generators

Everything organic here comes from one of four moves. Pick deliberately.

**1. Twisted extrusion** — the whole vase family:
```python
profile = polygon([...]).round_corners(6)
vase = profile.extrude(180, twist=140)     # degrees over the height
```
The killer gotcha: twist per division must stay BELOW the profile's
vertex angular spacing, or the surface folds through itself (you get
zero-thickness fins and a `thin-wall` at 0.0). If the profile has N
vertices and the extrusion has D divisions, keep
`twist/D < 360/N`. When in doubt raise the division count.

**2. Revolve** — bottles, bowls, turned forms:
```python
section = polygon([(0, 0), (40, 0), (52, 60), (30, 140), (34, 180),
                   (0, 180)])
body = section.revolve()                   # around the Y axis (the spine)
vase = parts.container(circle(52), 180, wall=2.5)   # or: uniform wall
```
Revolve gives you a SOLID; hollow it with `parts.container` from the
outline instead of subtracting a second revolve — that is how walls end
up 0.6 mm at the shoulder.

**3. Warp** — the sculptor's tool:
```python
def bulge(p):
    x, y, z = p
    k = 1.0 + 0.22 * math.sin(z / 18.0)     # pure function of position
    return (x * k, y * k, z)

form = cylinder(h=180, d=70).refine(2.0).warp(bulge)
```
`refine(edge_mm)` FIRST — warp moves vertices, so a coarse mesh warps
into facets. `refine(2.0)` before a warp is the difference between a
sculpture and a polyhedron. Cost: refine(1.0) on a big form makes
hundreds of thousands of triangles; start at 3.0 while iterating.

**4. Hull / loft** — blobby volumes from key sections:
```python
head = hull(sphere(d=60).translate(0, 0, 0),
            sphere(d=44).translate(0, 26, 8))
```
`hull()` is convex — for anything concave, build convex pieces and union
them. `parts.loft(profiles, heights)` hulls consecutive slabs, so it has
the same limit: a concave section quietly fills in.

## Determinism is not optional

```python
import math
def surface(p):
    x, y, z = p
    n = (math.sin(x * 0.31) * math.cos(y * 0.27) +
         0.5 * math.sin(z * 0.53))          # written down, reproducible
    return (x + n * 0.8, y + n * 0.8, z)
```
NEVER `random` without a fixed seed, never time, never dict iteration
order. The same model file must rebuild byte-identically — that is what
lets `solidsight diff` prove your last tweak changed only what you meant.
If you want variation, take a `SEED = 7` constant and say so.

## Measure what the eye cannot

The eye is the judge of the FORM. It is a terrible judge of everything
that makes the object exist:

| question | how |
|---|---|
| will the wall survive? | `report.json` min wall + its coordinates |
| does it stand up? | `stability`: COM vs footprint, `unstable`/`barely-stable` |
| did the twist fold? | min wall ~0 -> `--focus` on the point and `--slice` |
| is it one piece? | `shells` == 1 (organic unions love to leave crumbs) |
| hidden pockets? | `internal_voids` — a sealed cavity is invisible AND unprintable |
| does it read from every side? | `--turntable 8`, look at all 8 |

`--free` is the right mode here: everything is measured, nothing is
enforced. But when it gets printed, run `--print-safe --min-wall 0.8`
once and deal with what it says.

## Characters, creatures, props

- **Build from primitives that MEAN something** (torso, limb, joint),
  each emitted separately while you iterate. You get per-part reports
  and can `--part torso` to look at one thing. Union at the end.
- **Symmetry is free and exact**: model one side, `.mirror("x")`, union.
  Never hand-place a mirrored limb.
- **Accessories/props** attach at a declared point:
  `expect("sword", "hand", status="touching")` — the pose is then a
  spec, not a coincidence.
- Game-ready output (poly budget, GLB, LODs): see `game-ready.md`.

## The five ways organic models fail

1. **Twist folded the surface** — fins at 0 mm thickness. Raise
   divisions or lower the twist.
2. **Warped a coarse mesh** — faceted "sculpture". `refine()` first.
3. **Loft/hull filled a concave waist** — a potato. Decompose into
   convex pieces.
4. **Non-deterministic noise** — the model is different every build,
   `diff` is meaningless, the user cannot reproduce it. Pure functions.
5. **Pretty and 0.4 mm thick** — it exists on screen only. The report
   said so and nobody read it.

## Done means

- `--turntable 8` looked at, all frames. Form is a 360 deg claim.
- Min wall and stability quoted (even in `--free` — especially in free).
- `shells == 1`, no internal voids, or a stated reason.
- Every generator function is pure; the seed, if any, is written down.
