---
name: shadersight
description: "Use whenever the user asks to review, debug or validate a shader, material or BRDF — energy conservation, reciprocity, negative lobes, node-graph cycles/dead nodes/cost. You cannot render-and-squint; this tool turns the material into physics checks and the graph into graph theory, with exact numbers."
---

# /shadersight

A shader is judged by rendering a sphere and looking at it. What is
actually WRONG with a material, though, is physics — laws, not
opinions: a passive surface must not reflect more energy than it
receives, f(wi,wo) must equal f(wo,wi), and a BRDF is never negative.
All three are integrals and identities, so compute them. A node graph's
problems are graph theory: cycles, dead nodes, per-pixel cost.

## Usage

```
shadersight material --preset gold --roughness 0.35   # MEASURED F0, not memory
shadersight material --base-color 0.8,0.2,0.1 --roughness 0.4 --metallic 1
shadersight material ... --quality fast|normal|high   # integration effort
shadersight material ... --out DIR --json
shadersight diff out_v1 out_v2               # what the tweak changed (proof)

shadersight graph shader_graph.json          # cycles, dead nodes, cost
shadersight version
```

Graph format (the lowest common denominator any DCC can export):
```json
{"nodes": [{"id": "n1", "type": "multiply",
            "inputs": {"a": "n0.out", "b": 2.0}}],
 "output": "n1"}
```

Exit codes: 0 ok, 1 bad input, 2 a FAIL-level finding.

## What You Must Do When Invoked

### Step 0 - Install

```bash
shadersight version || pip install "git+https://github.com/VortexJer/AISight#subdirectory=shadersight"
```

### Start metals from a preset, never from memory

`--preset gold|silver|copper|aluminum|iron|titanium|chromium|plastic|
rubber|wood|skin|snow` loads MEASURED F0/base values (from spectral
n/k data). "Gold-ish yellow from memory" is how every wrong metal
ships: real gold F0 is (1.000, 0.766, 0.336) linear — most people's
guess is too pale. Explicit flags override the preset. Iterate
roughness on top, and `diff` the runs to see what moved.

### Materials: read the physics, not the sphere

`shadersight material` evaluates a standard metallic-roughness PBR
material (Lambert-coupled diffuse + GGX/Smith specular) and reports:

| check | level | law |
|---|---|---|
| `energy-not-conserved` | FAIL | directional albedo > 1 somewhere: the surface emits energy it never received. Most often a non-normalised D term. |
| `not-reciprocal` | FAIL | f(wi,wo) != f(wo,wi): a term treats view and light asymmetrically (the classic "fake fresnel" bug). Wrong from half of all angles. |
| `negative-brdf` | FAIL | a negative lobe subtracts light: sign slip or over-eager compensation term. |
| `high-energy-loss` | warn | >15 % lost at this roughness. EXPECTED single-scatter GGX behaviour, not a bug — say so instead of "fixing" it. |

Interpretation rules:
- **Albedo slightly under 1 at grazing is correct**; over 1 anywhere is
  not, and the report names the angle.
- **The energy-loss warning is a known model limitation** (no multiple
  scattering between microfacets). Rough metals look dark because of
  it. The fix is a multi-scatter term, not brighter base colour.
- The integration grid/sample count is in the report — quote it. A
  physics claim without its resolution is not a claim.
- `albedo_curve.png` plots directional albedo against the red 1.0
  ceiling; `preview.png` is the human-facing sphere. LOOK at the curve
  first: it carries the verdict.

### Graphs: cycles, dead weight, cost

| check | level | means |
|---|---|---|
| `graph-cycle` | FAIL | a value depends on itself within one pixel: cannot evaluate. The nodes are listed. |
| `dangling-input` | FAIL | an input reads from a node that does not exist. |
| `no-output` | FAIL | nothing is declared as the result. |
| `dead-nodes` | warn | nodes that never reach the output: computed for nothing. |
| `shader-cost-high` | warn | the live graph exceeds ~400 ALU-equivalents/pixel. |
| `unknown-node-type` | warn | types missing from the cost model: the estimate is a LOWER bound. |

Cost honesty: the numbers are orders of magnitude (a texture fetch
~100x an add, noise ~50x), counted over LIVE nodes only. Use them to
compare two graphs or find the dominant cost — never as a frame-time
budget, which depends on hardware this tool has never seen.

## Honesty Rules

- Never say a material "looks right". Say it conserves energy up to X,
  is reciprocal to Y, at grid Z.
- Distinguish law violations (FAIL: wrong in any renderer) from model
  limitations (warn: single-scatter loss) — conflating them sends the
  user to fix the wrong thing.
- The cost model is comparative, not predictive. Say so when quoting it.
- What this tool does NOT check, say plainly: it does not compile GLSL/
  HLSL, does not know your engine's lighting, and does not measure GPU
  time.

## Scope

Analyses: metallic-roughness PBR materials (the model ~90 % of real
shaders are), JSON node graphs.
Does NOT do: GLSL/HLSL parsing, engine integration, GPU profiling,
artistic judgment.

Siblings, same philosophy: `solidsight` (geometry), `animationsight`
(motion), `texturesight` (UVs/textures).
